"""
Social trend collection helpers.

The collector reads public web pages/RSS feeds and the official X API.
It does not bypass login walls, paywalls, captchas, or access controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import unescape
import os
import re
import xml.etree.ElementTree as ET

import requests

from utils.news_fetcher import fetch_trending_news


X_RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
DEFAULT_X_QUERY = "속보, 논란, 실시간, 난리, 근황, 이슈"
DCINSIDE_BEST_URLS = [
    "https://gall.dcinside.com/board/lists/?id=dcbest",
    "https://gall.dcinside.com/board/lists/?id=hit",
]
ILBE_BEST_URLS = [
    "https://www.ilbe.com/list/ilbe?listStyle=list",
    "https://www.ilbe.com/list/ilbe?listStyle=list&sub=best",
]


@dataclass
class TrendItem:
    title: str
    summary: str
    source: str
    source_label: str = ""
    url: str = ""
    time: str = "방금"
    traffic: str = ""
    platform: str = "web"
    relevance_score: int = 0
    relevance_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "summary": self.summary,
            "source": self.source,
            "source_label": self.source_label or self.source,
            "url": self.url,
            "time": self.time,
            "traffic": self.traffic,
            "platform": self.platform,
            "relevance_score": self.relevance_score,
            "relevance_reason": self.relevance_reason,
        }


def fetch_social_trends(
    keywords: str = "",
    dcinside_rss_urls: str = "",
    include_google_trends: bool = True,
    include_dcinside: bool = True,
    include_ilbe: bool = True,
    include_x: bool = True,
    max_items: int = 30,
) -> list[dict]:
    """Collect recent issue items without requiring a search keyword."""
    items: list[dict] = []

    if include_google_trends:
        items.extend(_mark_platform(fetch_trending_news(), "google", "Google Trends"))

    if include_dcinside:
        items.extend(fetch_dcinside_recent())

    if include_ilbe:
        items.extend(fetch_ilbe_recent())

    for rss_url in _split_lines(dcinside_rss_urls):
        items.extend(fetch_rss_items(rss_url, platform="dcinside"))

    if include_x:
        items.extend(fetch_x_recent_search(keywords or DEFAULT_X_QUERY))

    return _dedupe_items(items)[:max_items]


def fetch_dcinside_recent() -> list[dict]:
    """Fetch DCInside public best/hit gallery lists."""
    items: list[dict] = []
    for url in DCINSIDE_BEST_URLS:
        try:
            items.extend(_fetch_dcinside_list(url))
        except Exception:
            continue
    return items


def fetch_ilbe_recent() -> list[dict]:
    """Fetch Ilbe public best lists."""
    items: list[dict] = []
    for url in ILBE_BEST_URLS:
        try:
            items.extend(_fetch_ilbe_list(url))
        except Exception:
            continue
    return items


def fetch_rss_items(feed_url: str, platform: str = "rss") -> list[dict]:
    """Fetch public RSS/Atom items from a feed URL."""
    try:
        response = requests.get(feed_url, headers=_headers(), timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        raise RuntimeError(f"RSS 수집 실패: {feed_url} ({exc})") from exc

    channel_items = root.findall(".//item")
    atom_items = root.findall("{http://www.w3.org/2005/Atom}entry")

    items: list[dict] = []
    for node in channel_items:
        title = _node_text(node, "title")
        summary = _clean_html(_node_text(node, "description"))
        url = _node_text(node, "link")
        pub_date = _node_text(node, "pubDate")
        if title:
            items.append(
                TrendItem(
                    title=title,
                    summary=summary or title,
                    source=feed_url,
                    source_label="공개 RSS",
                    url=url,
                    time=_short_time(pub_date),
                    platform=platform,
                ).to_dict()
            )

    for node in atom_items:
        title = _node_text(node, "{http://www.w3.org/2005/Atom}title")
        summary = _clean_html(_node_text(node, "{http://www.w3.org/2005/Atom}summary"))
        link = node.find("{http://www.w3.org/2005/Atom}link")
        url = link.attrib.get("href", "") if link is not None else ""
        updated = _node_text(node, "{http://www.w3.org/2005/Atom}updated")
        if title:
            items.append(
                TrendItem(
                    title=title,
                    summary=summary or title,
                    source=feed_url,
                    source_label="공개 RSS",
                    url=url,
                    time=_short_time(updated),
                    platform=platform,
                ).to_dict()
            )

    return items


def fetch_x_recent_search(keywords: str, max_results: int = 20) -> list[dict]:
    """Fetch recent public tweets through the official X API."""
    bearer_token = os.environ.get("TWITTER_BEARER_TOKEN", "")
    if not bearer_token:
        return [
            TrendItem(
                title="X API 토큰이 필요합니다",
                summary="TWITTER_BEARER_TOKEN을 .env에 설정하면 X/Twitter 최근 이슈도 자동 수집합니다.",
                source="X API",
                source_label="X/Twitter",
                platform="x",
            ).to_dict()
        ]

    query = " OR ".join([f'"{word}"' for word in _split_keywords(keywords)])
    if not query:
        return []

    params = {
        "query": f"({query}) lang:ko -is:retweet",
        "max_results": min(max(max_results, 10), 100),
        "tweet.fields": "created_at,public_metrics",
    }
    response = requests.get(
        X_RECENT_SEARCH_URL,
        headers={**_headers(), "Authorization": f"Bearer {bearer_token}"},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()

    items: list[dict] = []
    for tweet in payload.get("data", []):
        text = _clean_html(tweet.get("text", ""))
        metrics = tweet.get("public_metrics", {})
        engagement = sum(
            metrics.get(key, 0)
            for key in ["like_count", "retweet_count", "reply_count", "quote_count"]
        )
        tweet_id = tweet.get("id", "")
        items.append(
            TrendItem(
                title=text[:80],
                summary=text,
                source="X",
                source_label="X/Twitter",
                url=f"https://twitter.com/i/web/status/{tweet_id}" if tweet_id else "",
                time=_short_time(tweet.get("created_at", "")),
                traffic=f"engagement {engagement}",
                platform="x",
            ).to_dict()
        )
    return items


def _fetch_dcinside_list(url: str) -> list[dict]:
    response = requests.get(url, headers=_headers(), timeout=15)
    response.raise_for_status()
    html = response.text
    items: list[dict] = []

    for row in _table_rows(html):
        if "gall_tit" not in row:
            continue
        link = _first_link(row)
        if not link:
            continue
        href, raw_title = link
        title = _clean_html(raw_title)
        if not title or title.startswith("공지"):
            continue
        post_url = _absolute_url(href, "https://gall.dcinside.com")
        date = _class_text(row, "gall_date")
        views = _class_text(row, "gall_count")
        recommends = _class_text(row, "gall_recommend")
        items.append(
            TrendItem(
                title=title,
                summary=f"디시인사이드 공개 베스트/히트 게시글: {title}",
                source=url,
                source_label="디시인사이드",
                url=post_url,
                time=date or "최근",
                traffic=_traffic_text(views, recommends),
                platform="dcinside",
            ).to_dict()
        )
        if len(items) >= 20:
            break
    return items


def _fetch_ilbe_list(url: str) -> list[dict]:
    response = requests.get(url, headers=_headers(), timeout=15)
    response.raise_for_status()
    html = response.text
    items: list[dict] = []

    for row in _table_rows(html):
        links = [link for link in _links(row) if "/view/" in link[0]]
        if not links:
            continue
        href, raw_title = links[0]
        title = _clean_html(raw_title)
        if not title or title.startswith("공지"):
            continue
        cells = [_clean_html(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)]
        post_url = _absolute_url(href, "https://www.ilbe.com")
        metrics = " · ".join([cell for cell in cells[-3:] if cell])
        items.append(
            TrendItem(
                title=title,
                summary=f"일베저장소 공개 인기/베스트 게시글: {title}",
                source=url,
                source_label="일베저장소",
                url=post_url,
                time=_guess_time(cells) or "최근",
                traffic=metrics,
                platform="ilbe",
            ).to_dict()
        )
        if len(items) >= 20:
            break
    return items


def _mark_platform(items: list[dict], platform: str, source_label: str = "") -> list[dict]:
    for item in items:
        item["platform"] = platform
        if source_label:
            item["source_label"] = source_label
    return items


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique: list[dict] = []
    for item in items:
        key = re.sub(r"\s+", " ", item.get("title", "").lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _split_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _split_keywords(text: str) -> list[str]:
    parts = re.split(r"[,#\n]+", text)
    return [part.strip() for part in parts if part.strip()]


def _node_text(node: ET.Element, tag: str) -> str:
    child = node.find(tag)
    return child.text.strip() if child is not None and child.text else ""


def _clean_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _table_rows(html: str) -> list[str]:
    return re.findall(r"<tr\b[^>]*>.*?</tr>", html, re.DOTALL | re.IGNORECASE)


def _links(html: str) -> list[tuple[str, str]]:
    pattern = r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>"
    return re.findall(pattern, html, re.DOTALL | re.IGNORECASE)


def _first_link(html: str) -> tuple[str, str] | None:
    links = _links(html)
    return links[0] if links else None


def _class_text(html: str, class_name: str) -> str:
    pattern = rf"<[^>]*class=[\"'][^\"']*{re.escape(class_name)}[^\"']*[\"'][^>]*>(.*?)</[^>]+>"
    match = re.search(pattern, html, re.DOTALL | re.IGNORECASE)
    return _clean_html(match.group(1)) if match else ""


def _absolute_url(href: str, base_url: str) -> str:
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    if href.startswith("/"):
        return f"{base_url}{href}"
    return f"{base_url}/{href}"


def _traffic_text(views: str, recommends: str) -> str:
    parts = []
    if views:
        parts.append(f"조회 {views}")
    if recommends:
        parts.append(f"추천 {recommends}")
    return " · ".join(parts)


def _guess_time(cells: list[str]) -> str:
    for cell in cells:
        if re.search(r"\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}|\d{4}\.\d{2}\.\d{2}", cell):
            return cell
    return ""


def _short_time(value: str) -> str:
    if not value:
        return "방금"
    normalized = value.replace("Z", "+00:00")
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%m/%d %H:%M")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(normalized).strftime("%m/%d %H:%M")
    except ValueError:
        return value[:16]


def _headers() -> dict:
    return {"User-Agent": "Mozilla/5.0 compatible; YouTubeCreatorTool/1.0"}
