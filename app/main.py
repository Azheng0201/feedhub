"""FastAPI 应用入口。"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.db import init_db
from app.routers import articles, feeds
from app.services.scheduler import start_scheduler, stop_scheduler

# 配置日志，方便查看调度器的输出
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - $(levelname)s - %(message)s")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭时的钩子。"""
    init_db()
    print(f"✅ 数据库已初始化")

    # === 修复双开 ===
    # 判断是不是 uvicorn 的 reload 监听主进程
    is_reloader = os.environ.get("UVICORN_RELOAD") == "true"

    if not is_reloader:
        start_scheduler() # 启动定时器
    else:
        print("⏭️ 在 reload 主进程中，跳过调度器启动")

    yield
    if not is_reloader:
        stop_scheduler()  # 关闭定时器
        
    print(f"👋 应用关闭")


app = FastAPI(
    title="FeedHub",
    description="RSS 聚合阅读器 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(feeds.router)
app.include_router(articles.router)

@app.get("/health", tags=["system"])
def health():
    """健康检查。"""
    return {
        "status": "ok",
        "service": "FeedHub",
        "version": app.version,
    }


@app.get("/", tags=["system"])
def root():
    """根路由。"""
    return {"message": "FeedHub API. 文档见 /docs"}