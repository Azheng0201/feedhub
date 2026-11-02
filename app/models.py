"""ORM 模型。"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Feed(Base):
    """一个 RSS 订阅源"""

    __tablename__ = "feeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    site_url: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    # 上次抓取时间; None 表示从未抓取
    last_fetched_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))

    articles: Mapped[list["Article"]] = relationship(
        back_populates="feed", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Feed(id={self.id}, url={self.url!r}>"


class Article(Base):
    """一篇抓取到的文章。"""

    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    feed_id: Mapped[int] = mapped_column(
        ForeignKey("feeds.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    link: Mapped[str] = mapped_column(String(1024), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    # AI 摘要
    ai_summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(128), default="")
    # 发布时间
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    fetched_at: Mapped[datetime] = mapped_column(default=datetime.now(timezone.utc))

    is_read: Mapped[bool] = mapped_column(default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(default=None)
    is_starred: Mapped[bool] = mapped_column(default=False, index=True)

    feed: Mapped["Feed"] = relationship(back_populates="articles")

    __table_args__ = (UniqueConstraint("feed_id", "link", name="uq_feed_link"),)

    def __repr__(self) -> str:
        return f"<Article id={self.id}, title={self.title[:30]!r}>"
