"""RSS 2.0 / Atom headlines. Feeds are untrusted: size/time capped, text only."""
import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from . import fsutil, net

MAX_SUMMARY = 300
MAX_FEED_BYTES = 2 * 1024 * 1024


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el, *names) -> str:
    c = _child(el, *names)
    return "".join(c.itertext()) if c is not None else ""


def clean(s: str, limit: int) -> str:
    s = re.sub(r"<[^>]*>", " ", s or "")
    s = re.sub(r"\s+", " ", html.unescape(s)).strip()
    if len(s) > limit:
        s = s[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return s


def _ts(s: str) -> float:
    s = (s or "").strip()
    if not s:
        return 0.0
    try:
        return parsedate_to_datetime(s).timestamp()
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def parse_feed(xml: bytes, source_url: str) -> list:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ValueError(f"Not a valid feed: {e}") from None
    kind = _local(root.tag)
    if kind == "rss" or kind == "RDF":
        channel = _child(root, "channel")
        if channel is None:
            raise ValueError("RSS feed has no channel")
        source = clean(_text(channel, "title"), 80)
        entries = [c for c in (channel if kind == "rss" else root) if _local(c.tag) == "item"]
        fields = (("title",), ("description", "encoded", "summary"), ("pubDate", "date", "updated"))
    elif kind == "feed":
        source = clean(_text(root, "title"), 80)
        entries = [c for c in root if _local(c.tag) == "entry"]
        fields = (("title",), ("summary", "content"), ("updated", "published"))
    else:
        raise ValueError("Not an RSS or Atom feed")
    items = []
    for e in entries[:100]:
        title = clean(_text(e, *fields[0]), 200)
        if title:
            items.append({"title": title, "summary": clean(_text(e, *fields[1]), MAX_SUMMARY),
                          "source": source or source_url, "ts": _ts(_text(e, *fields[2]))})
    return items


class FeedCache:
    def __init__(self, data_dir, http=None):
        self.path = Path(data_dir) / "cache" / "feeds.json"
        self.http = http
        self.data = fsutil.read_json(self.path, {}) or {}
        self.errors = {}

    def refresh(self, urls) -> None:
        for url in dict.fromkeys(urls):
            try:
                items = parse_feed(net.get_bytes(url, self.http, cap=MAX_FEED_BYTES, timeout=10), url)
            except Exception as e:
                self.errors[url] = str(e)
                continue
            self.data[url] = {"items": items, "fetched": time.time()}
            self.errors.pop(url, None)
        fsutil.atomic_write_json(self.path, self.data)

    def items(self, urls, limit=30) -> list:
        merged = [i for u in dict.fromkeys(urls) for i in self.data.get(u, {}).get("items", [])]
        merged.sort(key=lambda i: i["ts"], reverse=True)
        seen, out = set(), []
        for i in merged:
            if i["title"] not in seen:
                seen.add(i["title"])
                out.append(i)
        return out[:limit]
