"""Feed 的 CRUD 路由。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Feed
from app.schemas import FeedCreate, FeedRead, FeedUpdate
from app.services.fetcher import FetchError, fetch_feed, fetch_feeds_concurrent
from pydantic import BaseModel

router = APIRouter(prefix="/feeds", tags=["feeds"])


class FetchResult(BaseModel):
    """抓取结果。"""
    feed_id: int
    fetched: int
    created: int
    skipped: int
    message: str = ""


class FeedFetchResult(BaseModel):
    """单个源的抓取结果。"""
    feed_id: int
    ok: bool
    fetched: int
    created: int
    skipped: int
    error: str | None = None


class FetchAllResult(BaseModel):
    """批量抓取汇总。"""
    total: int
    successed: int
    failed: int
    elapsed_ms: int
    results: list[FeedFetchResult]


@router.post("/fetch-all", response_model=FetchAllResult)
async def fetch_all(db: Session = Depends(get_db)):
    """
    并发抓取所有源。
    """
    import time
    t0 = time.perf_counter()

    feeds = db.execute(select(Feed)).scalars().all()
    if not feeds:
        return {
            "total": 0, "successed": 0, "failed": 0,
            "elapsed_ms": 0, "results": [],
        }

    results = await fetch_feeds_concurrent(db, feeds)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    successed = sum(1 for r in results if r["ok"])
    return {
        "total": len(results),
        "successed": successed,
        "failed": len(results) - successed,
        "elapsed_ms": elapsed_ms,
        "results": results,
    }


@router.post("/{feed_id}/fetch", response_model=FetchResult)
def fetch_one_feed(feed_id: int, db: Session = Depends(get_db)):
    """
    抓取指定源的最新文章。
    """
    feed = _get_feed_or_404(db, feed_id)
    try:
        stats = fetch_feed(db, feed)
    except FetchError as e:
        # 抓取失败用 502 Bad GateWay, 表示"上游有问题"
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "feed_id": feed_id,
        "message": f"✅ 抓取完成",
        **stats,
    }

def _get_feed_or_404(db: Session, feed_id: int) -> Feed:
    """获取 Feed 或抛出 404"""
    feed = db.get(Feed, feed_id)
    if feed is None:
        raise HTTPException(status_code=404, detail=f"Feed {feed_id} 不存在")
    return feed


@router.post("", response_model=FeedRead, status_code=status.HTTP_201_CREATED)
def create_feed(payload: FeedCreate, db: Session = Depends(get_db)):
    """新增一个订阅源。URL 重复返回 409。"""
    # HttpUrl 是个 Url 对象， 转成 str 再存
    url_str = str(payload.url)

    # 先检查一遍更友好地报 409（DB 层也有唯一约束兜底）
    existing = db.execute(
        select(Feed).where(Feed.url == url_str)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"URL 已存在(feed_id={existing.id}) ")

    feed = Feed(
        url=url_str,
        title=payload.title,
        site_url=payload.site_url,
        description=payload.description,
    )
    db.add(feed)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="URL 已存在")
    db.refresh(feed)
    return feed


@router.get("", response_model=list[FeedRead])
def list_feeds(db: Session = Depends(get_db)):
    """获取所有订阅源。按创建时间倒序。"""
    feeds = db.execute(
        select(Feed).order_by(Feed.created_at.desc(), Feed.id.desc())
    ).scalars().all()
    return feeds


@router.get("/{feed_id}", response_model=FeedRead)
def get_feed(feed_id: int, db: Session = Depends(get_db)):
    """获取指定订阅源。不存在返回 404。"""
    feed = _get_feed_or_404(db, feed_id)
    return feed


@router.patch("/{feed_id}", response_model=FeedRead)
def update_feed(feed_id: int, payload: FeedUpdate, db: Session = Depends(get_db)):
    """更新指定订阅源。只改传过来的字段。"""
    feed = _get_feed_or_404(db, feed_id)

    # exclude_unset=True 只拿用户实际传了的字段，没传的不动
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(feed, key, value)

    db.commit()
    db.refresh(feed)
    return feed


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feed(feed_id: int, db: Session = Depends(get_db)):
    """删除指定订阅源, 级联删除其所有文章。成功返回 204, 无 body。"""
    feed = _get_feed_or_404(db, feed_id)
    db.delete(feed)
    db.commit()
    return None