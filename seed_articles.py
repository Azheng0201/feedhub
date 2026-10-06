"""临时脚本，造 50 篇文章用于测试。用完可删。"""
import random
from datetime import datetime, timedelta

from app.db import SessionLocal, init_db
from app.models import Article, Feed

init_db()
db = SessionLocal()

# 保证至少有两个 Feed
feeds = db.query(Feed).all()
if len(feeds) < 2:
    for i, url in enumerate([
        "https://www.ruanyifeng.com/blog/atom.xml",
        "https://hnrss.org/frontpage",
    ]):
        if not db.query(Feed).filter_by(url=url).first():
            db.add(Feed(url=url, title=f"源{i+1}"))
    db.commit()
    feeds = db.query(Feed).all()

print(f"用 {len(feeds)} 个 feed 造数据")

random.seed(42)
base = datetime(2026, 9, 1)
for i in range(50):
    feed = random.choice(feeds)
    pub = base + timedelta(days=random.randint(0, 30),
                           hours=random.randint(0, 23))
    a = Article(
        feed_id=feed.id,
        title=f"测试文章 {i}",
        link=f"https://example.com/article/{i}",
        summary=f"这是第 {i} 篇文章的摘要",
        content=f"<p>正文 {i}</p>",
        author="tester",
        published_at=pub,
        is_read=(i % 3 == 0),
        is_starred=(i % 7 == 0)
    )
    db.add(a)

db.commit()
print("已造 50 篇")
print("文章总数:", db.query(Article).count())
db.close()