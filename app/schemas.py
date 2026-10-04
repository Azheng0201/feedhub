"""Pydantic Schema: 定义 API 的输入输出结构。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


# ---------- Feed ----------

class FeedBase(BaseModel):
    """Feed 的公共字段。"""
    url: HttpUrl = Field(..., description="RSS 源地址")
    title: str = Field("", max_length=256)
    site_url: str = Field("", max_length=512)
    description: str = Field("", max_length=2000)


class FeedCreate(FeedBase):
    """Post /feeds 的请求体。"""
    pass


class FeedUpdate(BaseModel):
    """Patch /feeds/{id} 的请求体。所有字段可选。"""
    title: str | None = Field(None, max_length=256)
    site_url: str | None = Field(None, max_length=512)
    description: str | None = Field(None, max_length=2000)


class FeedRead(FeedBase):
    """GET 返回的 Feed 结构。"""
    id: int
    last_fetched_at: datetime | None = None
    created_at: datetime

    # Pydantic v2 里从 ORM 对象构造的开关
    model_config = ConfigDict(from_attributes=True)


# ---------- Article ----------

class ArticleBase(BaseModel):
    """Article 的公共字段。"""
    title: str = Field(..., max_length=512)
    link: str = Field(..., max_length=1024)
    summary: str = ""
    author: str = Field("", max_length=128)
    published_at: datetime | None = None


class ArticleRead(ArticleBase):
    """GET 返回的 Article 结构。"""
    id: int
    feed_id: int
    fetched_at: datetime
    is_read: bool
    is_starred: bool

    model_config = ConfigDict(from_attributes=True)