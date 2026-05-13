"""
Analytics event tracking via Supabase REST API.
Falls back to in-memory session log if Supabase is not configured.
"""
from __future__ import annotations

import os
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import requests
import streamlit as st

_TABLE = "app_events"

FEATURE_LABELS: dict[str, str] = {
    "content_generator": "⚡ 콘텐츠 생성기",
    "shorts_plugin": "🔥 핫이슈 검색기",
    "video_analyzer": "📊 영상 분석기",
    "growth_tracker": "🚀 급성장 채널",
    "keyword_search": "🔍 키워드 순위",
    "app": "앱 진입",
}


# ── helpers ────────────────────────────────────────────────────────────────

def _cfg() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_ANON_KEY", "")


def _sid() -> str:
    if "anl_sid" not in st.session_state:
        st.session_state.anl_sid = uuid.uuid4().hex[:12]
    return st.session_state.anl_sid


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return datetime(2000, 1, 1, tzinfo=timezone.utc)


# ── public API ─────────────────────────────────────────────────────────────

def log_visit() -> None:
    """Log one visit per browser session. Safe to call on every render."""
    if st.session_state.get("anl_visit_done"):
        return
    st.session_state.anl_visit_done = True
    log_event("visit", "app")


def log_event(event_type: str, page: str = "", details: dict | None = None) -> None:
    """Fire-and-forget analytics event. Never raises exceptions."""
    _mem_append(event_type, page)
    url, key = _cfg()
    if not url or not key:
        return
    try:
        requests.post(
            f"{url}/rest/v1/{_TABLE}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json={
                "session_id": _sid(),
                "event_type": event_type,
                "page": page,
                "details": details or {},
            },
            timeout=5,
        )
    except Exception:
        pass


def fetch_events(days: int = 30) -> list[dict]:
    """Return raw events from Supabase (newest first). Empty list on error."""
    url, key = _cfg()
    if not url or not key:
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        resp = requests.get(
            f"{url}/rest/v1/{_TABLE}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={
                "select": "event_type,page,session_id,created_at",
                "created_at": f"gte.{since}",
                "order": "created_at.desc",
                "limit": 10000,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def compute_stats(events: list[dict]) -> dict:
    """Aggregate raw events into display-ready stats dict."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    week_ago = now - timedelta(days=7)

    visits = [e for e in events if e.get("event_type") == "visit"]
    features = [e for e in events if e.get("event_type") == "page_view"]

    def unique_sessions(evts: list[dict], since: datetime | None = None) -> int:
        return len({
            e["session_id"] for e in evts
            if not since or _parse_dt(e.get("created_at", "")) >= since
        })

    today_visits = [e for e in visits if e.get("created_at", "").startswith(today_str)]
    week_visits = [e for e in visits if _parse_dt(e.get("created_at", "")) >= week_ago]

    # daily unique sessions for chart
    daily: dict[str, set] = defaultdict(set)
    for e in visits:
        daily[e.get("created_at", "")[:10]].add(e.get("session_id", ""))

    # hourly distribution (KST = UTC+9)
    hour_counter: Counter = Counter()
    for e in visits:
        dt = _parse_dt(e.get("created_at", ""))
        hour_counter[(dt.hour + 9) % 24] += 1

    return {
        "today": unique_sessions(today_visits),
        "week": unique_sessions(week_visits),
        "total": unique_sessions(visits),
        "total_events": len(events),
        "daily": {day: len(sids) for day, sids in sorted(daily.items())},
        "features": dict(Counter(e.get("page", "") for e in features).most_common(10)),
        "hourly": {h: hour_counter.get(h, 0) for h in range(24)},
    }


# ── in-memory session fallback ─────────────────────────────────────────────

def _mem_append(event_type: str, page: str) -> None:
    if "anl_mem" not in st.session_state:
        st.session_state.anl_mem = []
    st.session_state.anl_mem.append(
        {"event_type": event_type, "page": page,
         "created_at": datetime.now(timezone.utc).isoformat()}
    )


def get_mem_stats() -> dict:
    events = st.session_state.get("anl_mem", [])
    return {
        "session_events": len(events),
        "features": dict(
            Counter(e["page"] for e in events if e["event_type"] == "page_view")
        ),
    }
