"""数据库连接与会话管理"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'data' / 'feedhub.db'}",
)

# SQLite 需要 check_same_thread=False 才能在多线程环境下使用
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


def get_db():
    """FastAPI 依赖注入用: 每个请求一个 session, 用完自动关。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表(幂等)。"""
    from app import models  # noqa: F401 确保模型已注册到 Base.metadata

    Base.metadata.create_all(bind=engine)

    # 创建 FTS5 虚拟表与触发器
    with engine.begin() as conn:
        # 1. 创建 FTS 虚拟表（使用 trigram 分词器支持中文）
        conn.execute(
            text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS article_fts USING fts5(
                title,
                content,
                summary,
                content='articles',
                content_rowid='id',
                tokenize='trigram'
            );
        """)
        )

        # 2. 创建触发器，保持 FTS 表与主表同步
        # 插入触发器
        conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
                INSERT INTO article_fts(rowid, title, content, summary)
                VALUES (new.id, new.title, new.content, new.summary);
            END;
        """)
        )
        # 删除触发器
        conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
                INSERT INTO article_fts(article_fts, rowid, title, content, summary)
                VALUES ('delete', old.id, old.title, old.content, old.summary);
            END;
        """)
        )
        # 更新触发器
        conn.execute(
            text("""
            CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
                INSERT INTO article_fts(article_fts, rowid, title, content, summary)
                VALUES ('delete', old.id, old.title, old.content, old.summary);
                INSERT INTO article_fts(rowid, title, content, summary)
                VALUES (new.id, new.title, new.content, new.summary);
            END;
        """)
        )
