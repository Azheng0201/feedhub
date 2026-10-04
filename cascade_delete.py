from app.db import SessionLocal
from app.models import Feed, Article

db = SessionLocal()
f = Feed(url="https://test/rss", title="T")
db.add(f)
db.commit()
aid = Article(feed_id=f.id, title="a1", link="https://test/1")
db.add(aid)
db.commit()
print("创建 feed", f.id, "和 article", aid.id)

db.delete(f)
db.commit()
print("feed 已删")

from sqlalchemy import select
left = db.execute(select(Article).where(Article.id == aid.id)).scalar_one_or_none()
print("article 还在吗？", left is not None)
db.close()