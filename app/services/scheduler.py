"""后台定时任务调度器。"""
import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Feed
from app.services.fetcher import fetch_feeds_concurrent

logger = logging.getLogger(__name__)

# 全局调度器实例
scheduler = AsyncIOScheduler()

# 防并发锁：防止定时任务和手动触发的 API 同时抓取，导致 SQLite 锁死
_fetch_lock = asyncio.Lock()

async def scheduled_fetch_all():
    """
    被调度器或 API 调用的实际执行函数。
    """
    if _fetch_lock.locked():
        logger.warning("⏳ 上一次抓取任务还在进行中，跳过本次执行。")
        return

    async with _fetch_lock:
        logger.info("🚀 后台任务：开始抓取所有 RSS 源...")
        db = SessionLocal()
        try:
            feeds = db.execute(select(Feed)).scalars().all()
            if not feeds:
                logger.info("没有订阅源，抓取结束。")
                return

            results = await fetch_feeds_concurrent(db, feeds)

            success = sum(1 for r in results if r["ok"])
            created = sum(r["created"] for r in results)
            logger.info(f"✅ 后台抓取完成：{success}/{len(results)} 个源成功，新增 {created} 篇文章。")

        except Exception as e:
            logger.error(f"❌ 后台抓取异常：{e}", exc_info=True)
        finally:
            db.close()


def start_scheduler():
    """应用启动时调用。"""
    # 添加定时任务：每 30 分钟执行一次
    scheduler.add_job(
        scheduled_fetch_all,
        trigger=IntervalTrigger(minutes=30),
        id="fetch_all_feeds",
        name="定时全量抓取",
        replace_existing=True, # 防止热重载时重复添加
    )
    scheduler.start()
    logger.info("⏰ 调度器已启动，任务：每 30 分钟抓取一次")


def stop_scheduler():
    """应用关闭时调用。"""
    scheduler.shutdown(wait=False)
    logger.info("🛑 调度器已关闭")