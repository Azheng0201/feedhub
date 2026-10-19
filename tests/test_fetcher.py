"""fetcher 测试。"""
import httpx
import pytest
import respx

from app.services.fetcher import FetchError, fetch_feed

# 一个最小可用的 RSS 2.0 样本
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>测试源</title>
        <link>https://example.com</link>
        <description>源的描述</description>
        <item>
            <title>第一篇文章</title>
            <link>https://example.com/post/1</link>
            <description>摘要1</description>
            <pubDate>Mon, 06 Oct 2026 12:00:00 GMT</pubDate>
        </item>
        <item>
            <title>第二篇文章</title>
            <link>https://example.com/post/2</link>
            <description>摘要2</description>
            <pubDate>Tue, 07 Oct 2026 12:00:00 GMT</pubDate>
        </item>
    </channel>
</rss>
""".encode("utf-8")

# ---------- 正常路径 ----------

@respx.mock
def test_fetch_feed_success(db_session, make_feed):
    respx.get("https://example.com/rss").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS)
    )
    f = make_feed(url="https://example.com/rss", title="旧标题")

    stats = fetch_feed(db_session, f)
    assert stats["fetched"] == 2
    assert stats["created"] == 2
    assert stats["skipped"] == 0

    # 源信息被更新
    db_session.refresh(f)
    assert f.title == "测试源"
    assert f.site_url == "https://example.com"
    assert f.last_fetched_at is not None


@respx.mock
def test_fetch_feed_dedup(db_session, make_feed):
    respx.get("https://example.com/rss").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS)
    )
    f = make_feed(url="https://example.com/rss")

    fetch_feed(db_session, f)
    stats = fetch_feed(db_session, f)

    assert stats["fetched"] == 2
    assert stats["created"] == 0
    assert stats["skipped"] == 2


# ---------- 错误路径 ----------

@respx.mock
def test_fetch_feed_http_404(db_session, make_feed):
    respx.get("https://example.com/rss").mock(
        return_value=httpx.Response(404)
    )
    f = make_feed(url="https://example.com/rss")

    with pytest.raises(FetchError, match="HTTP 404"):
        fetch_feed(db_session, f)


@respx.mock
def test_fetch_feed_network_error(db_session, make_feed):
    respx.get("https://example.com/rss").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    f = make_feed(url="https://example.com/rss")

    with pytest.raises(FetchError, match="网络错误"):
        fetch_feed(db_session, f)


@respx.mock
def test_fetch_feed_bad_rss(db_session, make_feed):
    respx.get("https://example.com/rss").mock(
        return_value=httpx.Response(200, content=b"this is not xml at all")
    )
    f = make_feed(url="https://example.com/rss")

    with pytest.raises(FetchError):
        fetch_feed(db_session, f)


@respx.mock
def test_fetch_feed_empty_rss(db_session, make_feed):
    empty = b'<?xml version="1.0"?><rss version="2.0"><channel><title>X</title></channel></rss>'
    respx.get("https://example.com/rss").mock(
        return_value=httpx.Response(200, content=empty)
    )
    f = make_feed(url="https://example.com/rss")

    stats = fetch_feed(db_session, f)
    assert stats["fetched"] == 0
    assert stats["created"] == 0


# ---------- 脏数据处理 ----------

@respx.mock
def test_fetch_feed_strips_html(db_session, make_feed):
    rss = """<?xml version="1.0"?>
    <rss version="2.0"><channel><title>X</title>
        <item>
            <title>HTML 测试</title>
            <link>https://ex.com/1</link>
            <description>&lt;p&gt;这是&lt;strong&gt;粗体&lt;/strong&gt;摘要&lt;/p&gt;</description>
        </item>
    </channel></rss>"""

    respx.get("https://example.com/rss").mock(
        return_value=httpx.Response(200, content=rss)
    )
    f = make_feed(url="https://example.com/rss")
    fetch_feed(db_session, f)

    from sqlalchemy import select
    from app.models import Article
    a = db_session.execute(select(Article)).scalar_one()
    assert "<" not in a.summary
    assert "粗体" in a.summary


# ---------- 批量并发 ----------

@pytest.mark.asyncio
@respx.mock
async def test_fetch_feeds_concurrent_partial_failure(db_session, make_feed):
    respx.get("https://good1.com/rss").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS)
    )
    respx.get("https://bad.com/rss").mock(
        return_value=httpx.Response(500)
    )
    respx.get("https://good2.com/rss").mock(
        return_value=httpx.Response(200, content=SAMPLE_RSS)
    )

    f1 = make_feed(url="https://good1.com/rss", title="G1")
    f2 = make_feed(url="https://bad.com/rss", title="B")
    f3 = make_feed(url="https://good2.com/rss", title="G2")

    from app.services.fetcher import fetch_feeds_concurrent
    results = await fetch_feeds_concurrent(db_session, [f1, f2, f3])

    assert len(results) == 3
    assert results[0]["ok"] is True
    assert results[0]["created"] == 2
    assert results[1]["ok"] is False
    assert "HTTP 500" in results[1]["error"]
    assert results[2]["ok"] is True
    assert results[2]["created"] == 2