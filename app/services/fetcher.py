"""RSS 抓取服务。"""
import time
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
    import re
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


# ---------- 主流程 ----------

def fetch_feed(db: Session, feed: Feed) -> dict:
    """
    抓取一个 feed 的所有文章，去重入库。
    返回 {"fetched": 抓到多少条, "created": 新增多少条, "skipped": 重复多少条}
    """
    # 1. 抓 HTTP
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT,
                          headers={"User-Agent": USER_AGENT},
                          follow_redirects=True) as client:
            resp = client.get(feed.url)
            resp.raise_for_status()
            raw = resp.content
    except httpx.HTTPStatusError as e:
        raise FetchError(f"HTTP {e.response.status_code}: {feed.url}")
    except httpx.RequestError as e:
        raise FetchError(f"网络错误：{e}")

    # 2. 解析
    parsed = feedparser.parse(raw)
    if parsed.bozo and not parsed.entries:
        raise FetchError(f"RSS 解析失败：{parsed.bozo_exception}")

    # 3. 更新源信息
    if parsed.feed:
        title = getattr(parsed.feed, "title", "") or feed.title
        site_url = getattr(parsed.feed, "link", "") or feed.site_url
        desc = (getattr(parsed.feed, "subtitle", "")
                or getattr(parsed.feed, "description", "")
                or feed.description)
        feed.title = title
        feed.site_url = site_url
        feed.description = _strip_html(desc, limit=500)

    # 4. 遍历 entry 入库
    created = 0
    skipped = 0
    for entry in parsed.entries:
        link = _pick_link(entry)
        title = (getattr(entry, "title", "") or "").strip()
        if not link or not title:
            continue

        # 先查去重
        exists = db.execute(
            select(Article).where(
                Article.feed_id == feed.id,
                Article.link == link,
            )
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue

        article = Article(
            feed_id=feed.id,
            title=title[:512],
            link=link[:1024],
            summary=_strip_html(getattr(entry, "summary", "") or "", limit=2000),
            content=_pick_content(entry)[:50000],
            author=(getattr(entry, "author", "") or "")[:128],
            published_at=_pick_published(entry),
        )
        db.add(article)
        created += 1

    feed.last_fetched_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise FetchError("抓取时遇到并发冲突，请重试")

    return {
        "fetched": len(parsed.entries),
        "created": created,
        "skipped": skipped,
    }