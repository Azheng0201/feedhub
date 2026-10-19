"""Pytest 公共 fixture：每个测试独立的数据库 + TestClient。"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 让测试能 import 项目
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def db_session(monkeypatch):
    """
    每个测试一个独立的内存 SQLite。
    用 StaticPool 让所有连接共享同一个内存库。
    """
    from app import db as db_module
    from app.db import Base

    # 注意：必须用 StaticPool，否则内存 SQLite 会随连接关闭而清空
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False,
    )

    # 用测试 session 替换模块里的 engine / SessionLocal
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)

    # 建表
    import app.models
    Base.metadata.create_all(bind=test_engine)

    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session):
    """
    FastAPI TestClient, 所有请求用测试 session。
    """
    from app.db import get_db
    from app.main import app

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------- 数据工厂 ----------

@pytest.fixture
def make_feed(db_session):
    """快速创建一个 Feed，返回 ORM 对象。"""
    from app.models import Feed

    def _make(url="https://example.com/rss", title="测试源", **kw):
        f = Feed(url=url, title=title, **kw)
        db_session.add(f)
        db_session.commit()
        db_session.refresh(f)
        return f
    return _make


@pytest.fixture
def make_article(db_session):
    """快速创建一个 Article。"""
    from app.models import Article

    def _make(feed, title="测试文章", link=None, **kw):
        link = link or f"https://example.com/{title}"
        a = Article(feed_id=feed.id, title=title, link=link, **kw)
        db_session.add(a)
        db_session.commit()
        db_session.refresh(a)
        return a
    return _make