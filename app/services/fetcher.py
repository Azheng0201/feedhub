"""RSS 抓取服务。支持单源和批量。"""
import asyncio
import re
from datetime import datetime, timezone
from html import unescape

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Article, Feed

# 抓取超时（秒）
FETCH_TIMEOUT = 15
# 给 RSS 服务器的 UA，有些站点会拒绝默认 UA
USER_AGENT = "FeedHub/0.1 (+https://github.com/example/feedhub)"


class FetchError(Exception):
    """抓取失败"""


# ---------- 工具函数 ----------

def _struct_to_dt(s) -> datetime | None:
    """feedparser 的 published_parsed (struct_time) → datetime (UTC)。"""
    if not s:
        return None
    try:
        return datetime(*s[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _strip_html(text: str, limit: int = 2000) -> str:
    """去掉 HTML 标签"""
    if not text:
        return ""
    # 先 unescape，再简单正则去标签
    text = unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _pick_link(entry) -> str:
    """从 entry 里拿 link，Atom 的 link 字段可能是 list。"""
    link = getattr(entry, "link", "") or ""
    if isinstance(link, list):
        link = link[0] if link else ""
        if isinstance(link, dict):
            link = link.get("href", "")
    return str(link).strip()


def _pick_content(entry) -> str:
    """取正文：优先 content 其次 summary。"""
    content = getattr(entry, "content", None)
    if content and isinstance(content, list):
        # Atom 的 content 是 list[dict]
        return content[0].get("value", "") if isinstance(content[0], dict) else str(content[0])
    return getattr(entry, "summary", "") or ""


def _pick_published(entry) -> datetime | None:
    """发布时间：优先 published，回退 updated。"""
    for attr in ("published_parsed", "updated_parsed"):
        dt = _struct_to_dt(getattr(entry, attr, None))
        if dt:
            return dt
    return None


# ---------- 同步：单源抓取 ----------

def _http_client() -> httpx.Client:
    """同步 httpx 客户端。"""
    return httpx.Client(
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def _fetch_raw_sync(url: str) -> bytes:
    """同步抓一个 URL, 返回 bytes。失败抛 FetchError。"""
    try:
        with _http_client() as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code}: {url}")
    except httpx.RequestError as e:
        raise FetchError(f"网络错误：{e}")


def _parse_and_store(db: Session, feed: Feed, raw: bytes) -> dict:
    """
    解析 RSS bytes，入库去重。
    返回 {"fetched": N, "created": N, "skipped": N}
    """
    parsed = feedparser.parse(raw)
    if parsed.bozo and not parsed.entries:
        raise FetchError(f"RSS 解析失败：{parsed.bozo_exception}")

    # 更新源信息
    if parsed.feed:
        feed.title = getattr(parsed.feed, "title", "") or feed.title
        site_url = getattr(parsed.feed, "link", "")
        if not site_url:
            links = getattr(parsed.feed, "links", [])
            if links and isinstance(links, list) and isinstance(links[0], dict):
                site_url = links[0].get("href", "")
        feed.site_url = site_url or feed.site_url
        desc = (getattr(parsed.feed, "subtitle", "")
                or getattr(parsed.feed, "description", "")
                or feed.description)
        feed.description = _strip_html(desc, limit=500)

    created = 0
    skipped = 0
    for entry in parsed.entries:
        link = _pick_link(entry)
        title = (getattr(entry, "title", "") or "").strip()
        if not link or not title:
            continue

        exists = db.execute(
            select(Article).where(
                Article.feed_id == feed.id,
                Article.link == link,
            )
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue

        db.add(Article(
            feed_id=feed.id,
            title=title[:512],
            link=link[:1024],
            summary=_strip_html(getattr(entry, "summary", "") or "", limit=2000),
            content=_pick_content(entry)[:50000],
            author=(getattr(entry, "author", "") or "")[:128],
            published_at=_pick_published(entry),
        ))
        created += 1

    feed.last_fetched_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise FetchError("入库时遇到并发冲突，请重试")

    return {
        "fetched": len(parsed.entries),
        "created": created,
        "skipped": skipped,
    }



def fetch_feed(db: Session, feed: Feed) -> dict:
    """单源同步抓取。"""
    raw = _fetch_raw_sync(feed.url)
    return _parse_and_store(db, feed, raw)


# ---------- 异步：批量并发抓 HTTP ----------

async def _fetch_raw_async(client: httpx.AsyncClient, url: str) -> bytes:
    """异步抓一个 URL, 返回 bytes。"""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code}: {url}")
    except httpx.RequestError as e:
        raise FetchError(f"网络错误：{e}")


async def _fetch_all_raw(feeds: list[Feed]) -> list[bytes]:
    """
    并发抓所有 feed 的 HTTP, 返回和 feeds 等长的列表。
    """
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        tasks = [_fetch_raw_async(client, f.url) for f in feeds]
        return await asyncio.gather(*tasks, return_exceptions=True)


async def fetch_feeds_concurrent(db: Session, feeds: list[Feed]) -> list[dict]:
    """
    批量并发抓取。HTTP 并发，DB 串行。
    """
    if not feeds:
        return []

    raw_results = await _fetch_all_raw(feeds)

    output: list[dict] = []
    for feed, result in zip(feeds, raw_results):
        if isinstance(result, BaseException):
            err = str(result) if not isinstance(result, FetchError) else str(result)
            output.append({
                "feed_id": feed.id, "ok": False,
                "fetched": 0, "created": 0, "skipped": 0,
                "error": err,
            })
            continue

        try:
            stats = _parse_and_store(db, feed, result)
            output.append({
                "feed_id": feed.id, "ok": True,
                "error": None, **stats,
            })
        except FetchError as e:
            output.append({
                "feed_id": feed.id, "ok": False,
                "fetched": 0, "created": 0, "skipped": 0,
                "error": str(e),
            })

    return output