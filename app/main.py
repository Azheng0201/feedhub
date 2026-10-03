"""FastAPI 应用入口。"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动/关闭时的钩子。"""
    init_db()
    print(f"✅ 数据库已初始化")
    yield
    print(f"👋 应用关闭")


app = FastAPI(
    title="FeedHub",
    description="RSS 聚合阅读器 API",
    version="0.1.0",
    lifespan=lifespan,
)

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