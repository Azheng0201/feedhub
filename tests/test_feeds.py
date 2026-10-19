"""Feed CRUD 接口测试。"""


def test_create_feed(client):
    r = client.post("/feeds", json={
        "url": "https://example.com/rss",
        "title": "示例源",
    })
    if r.status_code == 422:
        print("\n[422 详情]：", r.json())
    assert r.status_code == 201
    data = r.json()
    assert data["url"] == "https://example.com/rss"
    assert data["title"] == "示例源"
    assert "id" in data


def test_create_feed_duplicate_url(client):
    client.post("/feeds", json={"url": "https://example.com/rss"})
    r = client.post("/feeds", json={"url": "https://example.com/rss"})
    assert r.status_code == 409
    assert "已存在" in r.json()["detail"]


def test_create_feed_invalid_url(client):
    r = client.post("/feeds", json={"url": "not-a-url"})
    assert r.status_code == 422  # Pydantic HttpUrl 校验失败


def test_list_feeds_empty(client):
    r = client.get("/feeds")
    assert r.status_code == 200
    assert r.json() == []


def test_list_feeds_order(client, make_feed):
    make_feed(url="https://a.com/rss", title="A")
    make_feed(url="https://b.com/rss", title="B")
    r = client.get("/feeds")
    titles = [f["title"] for f in r.json()]
    assert titles == ["B", "A"] # 倒序


def test_get_feed(client, make_feed):
    f = make_feed(url="https://a.com/rss", title="A")
    r = client.patch(f"/feeds/{f.id}", json={"title": "新标题"})
    assert r.status_code == 200
    assert r.json()["title"] == "新标题"


def test_get_feed_not_found(client):
    r = client.get("/feeds/99999")
    assert r.status_code == 404
    assert "不存在" in r.json()["detail"]


def test_update_feed(client, make_feed):
    f = make_feed(title="旧标题")
    r = client.patch(f"/feeds/{f.id}", json={"title": "新标题"})
    assert r.status_code == 200
    assert r.json()["title"] == "新标题"


def test_update_feed_partial(client, make_feed):
    f = make_feed(title="旧", description="保留我")
    client.patch(f"/feeds/{f.id}", json={"title": "新"})
    r = client.get(f"/feeds/{f.id}")
    assert r.json()["description"] == "保留我"


def test_update_feed_not_found(client):
    r = client.patch("/feeds/9999", json={"title": "x"})
    assert r.status_code == 404


def test_delete_feed(client, make_feed):
    f = make_feed()
    r = client.delete(f"/feeds/{f.id}")
    assert r.status_code == 204
    assert client.get(f"/feeds/{f.id}").status_code == 404


def test_delete_feed_not_found(client):
    r = client.delete("/feeds/99999")
    assert r.status_code == 404


def test_delete_feed_cascades_articles(client, make_feed, make_article):
    f = make_feed()
    make_article(f, title="a1")
    make_article(f, title="a2")
    assert len(client.get("/articles").json()["items"]) == 2

    client.delete(f"/feeds/{f.id}")
    assert client.get("/articles").json()["items"] == []