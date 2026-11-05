"""Article 的浏览与状态管理路由。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Article, Feed
from app.schemas import (
    ArticleDetailRead,
    ArticlePage,
    ArticleRead,
    ArticleUpdate,
    PageMeta,
)
from app.services.cache import clear_pattern, get_cache, set_cache
from app.services.extractor import ExtractError, extract_full_text, html_to_markdown


class StatsResponse(BaseModel):
    total: int
    unread: int
    starred: int
    feeds_count: int
    per_feed: list[dict]


class CleanResponse(BaseModel):
    deleted_count: int
    message: str


router = APIRouter(prefix="/articles", tags=["articles"])


def _get_article_or_404(db: Session, article_id: int) -> Article:
    """获取 Article 或抛出 404"""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"Article {article_id} 不存在")
    return article


@router.get("/search", response_model=ArticlePage)
def search_articles(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """F全文搜索(兼容版)。"""
    like_q = f"%{q}%"

    stmt = select(Article).where(
        (Article.title.ilike(like_q))
        | (Article.content.ilike(like_q))
        | (Article.summary.ilike(like_q))
    )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    offset = (page - 1) * size
    articles = (
        db.execute(
            stmt.order_by(Article.published_at.desc()).limit(size).offset(offset)
        )
        .scalars()
        .all()
    )

    article_ids = [a.id for a in articles]

    if not article_ids:
        items = []
    else:
        # 关联加载 feed
        stmt2 = (
            select(Article)
            .where(Article.id.in_(article_ids))
            .options(joinedload(Article.feed))
        )
        articles_map = {a.id: a for a in db.execute(stmt2).scalars().all()}
        items = [articles_map[aid] for aid in article_ids if aid in articles_map]

    pages = max(1, (total + size - 1) // size)
    meta = PageMeta(
        page=page,
        size=size,
        total=total,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )
    return {"items": items, "meta": meta}


@router.post("/{article_id}/extract", response_model=ArticleRead)
async def extract_article_content(article_id: int, db: Session = Depends(get_db)):
    """针对只提供摘要的 RSS，去原网页抓取完整正文。"""
    article = _get_article_or_404(db, article_id)

    try:
        full_text = await extract_full_text(article.link)

        article.content = full_text[:100000]

        db.commit()
        db.refresh(article)
        return article

    except ExtractError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """
    文章统计聚合。带 Redis 缓存，有效期 5 分钟。
    """
    cache_key = "stats:dashboard"

    # 1. 尝试从缓存读取
    cache_data = await get_cache(cache_key)
    if cache_data:
        return cache_data  # 命中缓存，直接返回

    # 2. 缓存未命中，查询数据库
    total = db.execute(select(func.count(Article.id))).scalar_one()
    unread = db.execute(
        select(func.count(Article.id)).where(Article.is_read.is_(False))
    ).scalar_one()
    starred = db.execute(
        select(func.count(Article.id)).where(Article.is_starred.is_(True))
    ).scalar_one()
    feeds_count = db.execute(select(func.count(Feed.id))).scalar_one()

    # 按源分组统计文章数
    feeds_stats_stmt = (
        select(Feed.title, func.count(Article.id).label("count"))
        .outerjoin(Article)
        .group_by(Feed.id)
        .order_by(func.count(Article.id).desc())
    )
    per_feed_rows = db.execute(feeds_stats_stmt).all()

    per_feed = [{"feed_title": row[0], "count": row[1]} for row in per_feed_rows]

    result = {
        "total": total,
        "unread": unread,
        "starred": starred,
        "feeds_count": feeds_count,
        "per_feed": per_feed,
    }

    # 3. 写入缓存
    await set_cache(cache_key, result, expire=300)
    return result


@router.delete("/clean", response_model=CleanResponse)
def clean_old_articles(
    days: int = Query(30, ge=1, description="清理多少天前的已读文章"),
    db: Session = Depends(get_db),
):
    """
    清理超过 N 天的文章。
    """
    # 使用 replace(tzinfo=None) 去掉时区，变成Naive datetime
    # 因为SQLite 存入的时间格式默认是不带时区的字符串Naive datetime

    cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

    stmt = select(Article).where(
        Article.published_at < cutoff_date,
        Article.is_read.is_(True),
        Article.is_starred.is_(False),
    )
    articles_to_delete = db.execute(stmt).scalars().all()
    count = len(articles_to_delete)

    if count == 0:
        return {"deleted_count": 0, "message": f"没有发现 {days} 天前的已读文章"}

    for a in articles_to_delete:
        db.delete(a)
    db.commit()

    return {"deleted_count": count, "message": f"成功清理了 {count} 篇旧文章"}


@router.get("", response_model=ArticlePage)
def list_articles(
    page: int = Query(1, ge=1, description="页码, 从 1 开始"),
    size: int = Query(20, ge=1, le=100, description="每页条数, 1~100"),
    feed_id: int | None = Query(None, description="只看某个源"),
    is_read: bool | None = Query(None, description="按已读/未读筛选"),
    is_starred: bool | None = Query(None, description="只看收藏"),
    keyword: str | None = Query(None, max_length=100, description="标题关键词模糊匹配"),
    db: Session = Depends(get_db),
):
    """
    文章列表，按发布时间倒序。
    支持分页 + 多条件筛选。
    """
    # 1. 构造基础 WHERE
    conditions = []
    if feed_id is not None:
        conditions.append(Article.feed_id == feed_id)
    if is_read is not None:
        conditions.append(Article.is_read == is_read)
    if is_starred is not None:
        conditions.append(Article.is_starred == is_starred)
    if keyword:
        conditions.append(Article.title.ilike(f"%{keyword}%"))

    # 2. 总数（用同一套条件）
    count_stmt = select(func.count()).select_from(Article)
    if conditions:
        count_stmt = count_stmt.where(*conditions)
    total = db.execute(count_stmt).scalar_one()

    # 3. 分页查询
    stmt = select(Article).options(joinedload(Article.feed))
    if conditions:
        stmt = stmt.where(*conditions)
    # 优先按发布时间倒序, 没有发布时间的排在后面
    stmt = (
        stmt.order_by(
            Article.published_at.desc().nullslast(),
            Article.fetched_at.desc(),
            Article.id.desc(),
        )
        .offset((page - 1) * size)
        .limit(size)
    )

    rows = db.execute(stmt).scalars().all()

    items = []
    for a in rows:
        item_dict = {
            k: getattr(a, k)
            for k in [
                "id",
                "feed_id",
                "title",
                "link",
                "summary",
                "author",
                "published_at",
                "fetched_at",
                "is_read",
                "is_starred",
            ]
        }
        item_dict["feed_title"] = a.feed.title if a.feed else ""
        items.append(item_dict)

    # 4. 组装 meta
    pages = max(1, (total + size - 1) // size)
    meta = PageMeta(
        page=page,
        size=size,
        total=total,
        pages=pages,
        has_next=page < pages,
        has_prev=page > 1,
    )

    return {"items": items, "meta": meta}


@router.get("/{article_id}", response_model=ArticleDetailRead)
def get_article(article_id: int, db: Session = Depends(get_db)):
    """文章详情。包含正文和源标题。"""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"Article {article_id} 不存在")

    # 手动取 feed 标题
    feed = db.get(Feed, article.feed_id)
    feed_title = feed.title if feed else ""

    # 用 Pydantic 从 ORM 构造，再补上 feed_title
    detail = ArticleDetailRead.model_validate(article)
    detail.feed_title = feed_title
    return detail


@router.patch("/{article_id}", response_model=ArticleRead)
async def update_article(
    article_id: int, payload: ArticleUpdate, db: Session = Depends(get_db)
):
    """标记已读/收藏。只改传过来的字段。"""
    article = _get_article_or_404(db, article_id)

    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请求体为空，至少传 is_read 或 is_starred",
        )

    for key, value in data.items():
        setattr(article, key, value)

    if "is_read" in data:
        if data["is_read"]:
            article.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            article.read_at = None

    db.commit()

    # 清理统计缓存
    await clear_pattern("stats:*")

    db.refresh(article)
    return article


# ---------- 批量标记 ----------


@router.post("/mark-all-read", status_code=status.HTTP_200_OK)
def mark_all_read(
    feed_id: int | None = Query(None, description="只标记某个源，不传标记全部"),
    db: Session = Depends(get_db),
):
    """
    一键全部已读。返回受影响的行数。
    """
    stmt = select(Article).where(Article.is_read.is_(False))
    if feed_id is not None:
        stmt = stmt.where(Article.feed_id == feed_id)

    articles = db.execute(stmt).scalars().all()
    for a in articles:
        a.is_read = True

    db.commit()
    return {"updated": len(articles)}


@router.get("/{article_id}/export")
def export_article(article_id: int, db: Session = Depends(get_db)):
    """导出文章为 Markdown 文件。"""
    article = _get_article_or_404(db, article_id)

    # 1. 组装 Markdown 内容
    md_content = f"# {article.title}\n\n"
    if article.author:
        md_content += f"**作者**: {article.author}  \n"
    if article.published_at:
        md_content += (
            f"**发布时间**: {article.published_at.strftime('%Y-%m-%d %H:%M')}  \n"
        )
    md_content += f"**原文链接**: [{article.link}]({article.link})\n\n"

    md_content += "---\n\n"

    # 2. 将正文 HTML 转为 Markdown
    # 如果没有正文，就用摘要
    content_source = article.content or article.summary or ""
    if "<" in content_source and ">" in content_source:
        md_content += html_to_markdown(content_source)
    else:
        md_content += content_source

    if article.ai_summary:
        md_content += f"\n\n> **AI 摘要**: {article.ai_summary}"

    # 3. 构造安全的文件名
    # 移除文件名中的非法字符
    safe_title = "".join(c for c in article.title if c not in r'\/:*?"<>|')
    # 防止文件名过长
    safe_title = safe_title[:50]
    filename_utf8 = f"{safe_title}.md"
    # 按照 RFC 5987 对文件名进行 URL 编码，确保中文和特殊字符在浏览器中正确显示
    disposition = f"attachment; filename*=UTF-8''{quote(filename_utf8)}"

    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )
