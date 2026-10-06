"""Article 的浏览与状态管理路由。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Article, Feed
from app.schemas import (
    ArticleDetailRead, ArticlePage, ArticleRead, ArticleUpdate, PageMeta,
)

router = APIRouter(prefix="/articles", tags=["articles"])


def _get_article_or_404(db: Session, article_id: int) -> Article:
    """获取 Article 或抛出 404"""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail=f"Article {article_id} 不存在")
    return article


@router.get("", response_model=ArticlePage)
def list_articles(
    page:       int = Query(1, ge=1, description="页码, 从 1 开始"),
    size:       int = Query(20, ge=1, le=100, description="每页条数, 1~100"),
    feed_id:    int | None = Query(None, description="只看某个源"),
    is_read:    bool | None = Query(None, description="按已读/未读筛选"),
    is_starred: bool | None = Query(None, description="只看收藏"),
    keyword:    str | None = Query(None, max_length=100,
                                description="标题关键词模糊匹配"),
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
    stmt = select(Article)
    if conditions:
        stmt = stmt.where(*conditions)
    # 优先按发布时间倒序, 没有发布时间的排在后面
    stmt = stmt.order_by(
        Article.published_at.desc().nullslast(),
        Article.fetched_at.desc(),
        Article.id.desc(),
    ).offset((page - 1) * size).limit(size)

    rows = db.execute(stmt).scalars().all()

    # 4. 组装 meta
    pages = max(1, (total + size - 1) // size)
    meta = PageMeta(
        page=page, size=size, total=total, pages=pages,
        has_next = page < pages,
        has_prev = page > 1,
    )

    return {"items": rows, "meta": meta}


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
def update_article(article_id: int, payload: ArticleUpdate,
                   db: Session = Depends(get_db)):
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

    db.commit()
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
    stmt = select(Article).where(Article.is_read == False)  # noqa:E712
    if feed_id is not None:
        stmt = stmt.where(Article.feed_id == feed_id)

    articles = db.execute(stmt).scalars().all()
    for a in articles:
        a.is_read = True

    db.commit()
    return {"uppdated": len(articles)}