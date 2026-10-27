""" Article 接口测试。"""


def test_list_articles_empty(client):
    r = client.get("/articles")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["meta"]["total"] == 0


def test_list_articles_pagination(client, make_feed, make_article):
    f = make_feed()
    for i in range(25):
        make_article(f, title=f"文章{i}", link=f"https://ex.com/{i}")

    r1 = client.get("/articles?page=1&size=10").json()
    r2 = client.get("/articles?page=2&size=10").json()
    r3 = client.get("/articles?page=3&size=10").json()

    assert len(r1["items"]) == 10
    assert len(r2["items"]) == 10
    assert len(r3["items"]) == 5
    assert r1["meta"]["total"] == 25
    assert r1["meta"]["pages"] == 3
    assert r1["meta"]["has_next"] is True
    assert r3["meta"]["has_next"] is False


def test_list_articles_invalid_page(client):
    assert client.get("articles?page=0").status_code == 422
    assert client.get("articles?size=999").status_code == 422
    assert client.get("articles?page=abc").status_code == 422


def test_filter_by_feed_id(client, make_feed, make_article):
    f1 = make_feed(url="https://a.com/rss", title="A")
    f2 = make_feed(url="https://b.com/rss", title="B")
    make_article(f1, title="A1", link="https://ex.com/a1")
    make_article(f2, title="B1", link="https://ex.com/b1")

    r = client.get(f"/articles?feed_id={f1.id}").json()
    assert r["meta"]["total"] == 1
    assert r["items"][0]["title"] == "A1"


def test_filter_by_is_read(client, make_feed, make_article):
    f = make_feed()
    make_article(f, title="已读", link="https://ex.com/1", is_read=True)
    make_article(f, title="未读", link="https://ex.com/2", is_read=False)

    r = client.get("/articles?is_read=false").json()
    assert r["meta"]["total"] == 1
    assert r["items"][0]["title"] == "未读"


def test_filter_by_keyword(client, make_feed, make_article):
    f = make_feed()
    make_article(f, title="Python 教程", link="https://ex.com/1")
    make_article(f, title="Rust 教程", link="https://ex.com/2")
    make_article(f, title="杂谈", link="https://ex.com/3")

    r = client.get("/articles?keyword=教程").json()
    assert r["meta"]["total"] == 2


def test_get_article_detail(client, make_feed, make_article):
    f = make_feed(title="源标题")
    a = make_article(f, title="文章标题", content="<p>正文</p>")
    r = client.get(f"/articles/{a.id}")
    assert r.status_code == 200
    data = r.json()
    assert data["title"] == "文章标题"
    assert data["content"] == "<p>正文</p>"
    assert data["feed_title"] == "源标题"


def test_get_article_not_found(client):
    assert client.get("/articles/99999").status_code == 404


def test_patch_article_mark_read(client, make_feed, make_article):
    a = make_article(feed=make_feed(), is_read=False)
    r = client.patch(f"/articles/{a.id}", json={"is_read": True})
    assert r.status_code == 200
    assert r.json()["is_read"] is True


def test_patch_article_empty_body(client, make_feed, make_article):
    a = make_article(feed=make_feed())
    r = client.patch(f"/articles/{a.id}", json={})
    assert r.status_code == 400

def test_patch_article_not_found(client):
    r = client.patch("/articles/99999", json={"is_read": True})
    assert r.status_code == 404


def test_mark_all_read(client, make_feed, make_article):
    f = make_feed()
    for i in range(5):
        make_article(f, title=f"a{i}", link=f"https://ex.com/{i}", is_read=False)

    r = client.post("/articles/mark-all-read").json()
    assert r["updated"] == 5
    assert client.get("/articles?is_read=false").json()["meta"]["total"] == 0


def test_mark_all_read_for_feed(client, make_feed, make_article):
    f1 = make_feed(url="https://a.com/rss", title="A")
    f2 = make_feed(url="https://b.com/rss", title="B")
    make_article(f1, title="a1", link="https://ex.com/a1", is_read=False)
    make_article(f2, title="b1", link="https://ex.com/b1", is_read=False)

    r = client.post(f"/articles/mark-all-read?feed_id={f1.id}").json()
    assert r["updated"] == 1
    r2 = client.get("/articles?is_read=false").json()
    assert r2["meta"]["total"] == 1


def test_list_articles_includes_feed_title(client, make_feed, make_article):
    f = make_feed(title = "测试源标题")
    make_article(f, title="文章A", link="http://ex.com/a")

    r = client.get("/articles").json()
    assert r["items"][0]["feed_title"] == "测试源标题"


def test_get_stats(client, make_feed, make_article):
    f = make_feed()
    make_article(f, title="文章1", is_read=False) 
    make_article(f, title="文章2", is_read=True, is_starred=True)
    r = client.get("/articles/stats").json()
    assert r["total"] == 2
    assert r["unread"] == 1
    assert r["starred"] == 1
    assert r["feeds_count"] == 1
    assert r["per_feed"][0]["count"] == 2


def test_clean_old_articles(client, make_feed, make_article, db_session):
    from datetime import datetime, timezone, timedelta
    f = make_feed()

    old_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=40)
    old_a = make_article(f, title="旧文章", link="https://ex.com/old", is_read=True)
    old_a.published_at = old_date
    db_session.commit()

    star_a = make_article(f, title="收藏旧文章", link="https://ex.com/star", is_read=True, is_starred=True)
    star_a.published_at = old_date
    db_session.commit()

    make_article(f, title="新文章", link="https://ex.com/new", is_read=True)

    r = client.delete("/articles/clean?days=30").json()
    assert r["deleted_count"] == 1

    assert client.get("/articles/stats").json()["total"] == 2