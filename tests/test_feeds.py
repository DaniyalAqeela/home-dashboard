import io

import pytest

from dashboard import feeds

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>World News</title>
<item><title>First story</title><description>&lt;p&gt;Hi &lt;b&gt;there&lt;/b&gt; &amp;amp; you&lt;/p&gt;</description>
<pubDate>Tue, 24 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Second story</title><description>Plain text</description>
<pubDate>Tue, 24 Nov 2026 12:00:00 GMT</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Source</title>
<entry><title>Atom entry</title><summary type="html">Short &lt;i&gt;summary&lt;/i&gt;</summary>
<updated>2026-11-24T11:00:00Z</updated></entry>
</feed>"""


def test_parse_rss():
    items = feeds.parse_feed(RSS, "https://x/rss")
    assert [i["title"] for i in items] == ["First story", "Second story"]
    assert items[0]["source"] == "World News"
    assert items[1]["ts"] > items[0]["ts"] > 0


def test_parse_atom():
    items = feeds.parse_feed(ATOM, "https://y/atom")
    assert items == [{"title": "Atom entry", "summary": "Short summary", "source": "Atom Source",
                      "ts": items[0]["ts"]}]
    assert items[0]["ts"] > 0


def test_summary_html_stripped():
    assert feeds.parse_feed(RSS, "u")[0]["summary"] == "Hi there & you"


def test_summary_truncated():
    long = b"<rss><channel><title>t</title><item><title>a</title><description>" + b"word " * 200 + \
           b"</description></item></channel></rss>"
    assert len(feeds.parse_feed(long, "u")[0]["summary"]) <= 300


def test_malformed_raises():
    with pytest.raises(ValueError):
        feeds.parse_feed(b"<rss><channel><item>", "u")
    with pytest.raises(ValueError):
        feeds.parse_feed(b"<html><body>not a feed</body></html>", "u")


def test_refresh_keeps_cache_on_error(tmp_path):
    good = {"https://a": RSS}
    c = feeds.FeedCache(tmp_path, http=lambda url, timeout=None: io.BytesIO(good[url]))
    c.refresh(["https://a"])
    assert len(c.items(["https://a"])) == 2

    def broken(url, timeout=None):
        raise OSError("offline")
    c2 = feeds.FeedCache(tmp_path, http=broken)  # new process: cache read from disk
    c2.refresh(["https://a"])
    assert len(c2.items(["https://a"])) == 2
    assert "offline" in c2.errors["https://a"]


def test_items_sorted_and_deduped(tmp_path):
    data = {"https://a": RSS, "https://b": RSS.replace(b"First story", b"Third story"), "https://c": ATOM}
    c = feeds.FeedCache(tmp_path, http=lambda url, timeout=None: io.BytesIO(data[url]))
    c.refresh(list(data))
    titles = [i["title"] for i in c.items(list(data))]
    assert titles[0] == "Second story" and titles.count("Second story") == 1
    assert set(titles) == {"First story", "Second story", "Third story", "Atom entry"}
    assert [i["title"] for i in c.items(["https://c"])] == ["Atom entry"]
    assert len(c.items(list(data), limit=2)) == 2


def test_news_widget_rotates(rt, monkeypatch):
    rt.feeds.http = lambda url, timeout=None: io.BytesIO(RSS)
    rt.refresh_feeds()
    news = next(w for w in rt.config["widgets"] if w["type"] == "news")
    st = rt.build_display_state()["widgets"][news["id"]]
    assert [i["title"] for i in st["items"]] == ["Second story", "First story"]
    assert st["index"] == 0
    now = [1000.0]
    monkeypatch.setattr("dashboard.features.time.time", lambda: now[0])
    rt.rotate_tick()
    now[0] += news["options"]["interval"] + 1
    rev = rt.state.rev
    rt.rotate_tick()
    assert rt.build_display_state()["widgets"][news["id"]]["index"] == 1 and rt.state.rev == rev + 1


def test_news_description_length(rt):
    rt.feeds.http = lambda url, timeout=None: io.BytesIO(RSS)
    rt.refresh_feeds()
    cfg = rt.config
    for w in cfg["widgets"]:
        if w["type"] == "news":
            w["options"]["descLength"] = 5
    rt.update_config(cfg)
    news = next(w for w in rt.config["widgets"] if w["type"] == "news")
    assert all(len(i["summary"]) <= 5 for i in rt.build_display_state()["widgets"][news["id"]]["items"])
