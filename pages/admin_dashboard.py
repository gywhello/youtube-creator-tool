"""
Private admin analytics dashboard.
Access: append ?admin=1 to the app URL. Password-gated.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import streamlit as st

from utils.analytics import (
    FEATURE_LABELS,
    compute_stats,
    fetch_events,
    get_mem_stats,
)


def _check_password() -> bool:
    correct = os.environ.get("ADMIN_PASSWORD", "")
    if not correct:
        st.warning("⚠️ ADMIN_PASSWORD 환경변수가 설정되지 않았습니다.")
        return False
    if st.session_state.get("admin_authed"):
        return True
    st.markdown("### 🔐 관리자 로그인")
    pw = st.text_input("비밀번호", type="password", key="adm_pw")
    if st.button("로그인", key="adm_btn"):
        if pw == correct:
            st.session_state.admin_authed = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    return False


def render() -> None:
    st.markdown(
        '<div style="font-size:1.4rem;font-weight:800;margin-bottom:0.5rem">'
        "📊 관리자 대시보드</div>",
        unsafe_allow_html=True,
    )

    if not _check_password():
        return

    has_supabase = bool(os.environ.get("SUPABASE_URL"))

    if not has_supabase:
        _render_no_supabase()
        return

    col_r, col_days = st.columns([3, 1])
    with col_days:
        days = st.selectbox("기간", [7, 14, 30, 90], index=2, key="adm_days",
                            format_func=lambda d: f"최근 {d}일")
    with col_r:
        st.markdown(
            f'<div style="font-size:0.75rem;color:#8e8e93;margin-top:1.8rem">'
            f'마지막 갱신: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")} UTC</div>',
            unsafe_allow_html=True,
        )

    with st.spinner("데이터 불러오는 중..."):
        events = fetch_events(days=days)

    if not events:
        st.info("아직 수집된 데이터가 없습니다. 앱이 사용되면 자동으로 표시됩니다.")
        _render_setup_guide()
        return

    stats = compute_stats(events)

    _render_kpi(stats)
    st.markdown("---")

    col_a, col_b = st.columns(2)
    with col_a:
        _render_daily_chart(stats)
    with col_b:
        _render_hourly_chart(stats)

    st.markdown("---")
    _render_feature_chart(stats)
    st.markdown("---")
    _render_recent_events(events[:100])
    st.markdown("---")
    _render_setup_guide()


def _render_kpi(stats: dict) -> None:
    c1, c2, c3, c4 = st.columns(4)
    _kpi(c1, "오늘 방문자", stats["today"], "명")
    _kpi(c2, "이번 주 방문자", stats["week"], "명")
    _kpi(c3, "누적 방문자", stats["total"], "명")
    _kpi(c4, "총 이벤트", stats["total_events"], "건")


def _kpi(col, label: str, value: int, unit: str) -> None:
    with col:
        st.markdown(
            f'<div style="background:#1c1c1e;border-radius:12px;padding:14px 18px;'
            f'border:1px solid #3a3a3c;text-align:center;">'
            f'<div style="font-size:0.7rem;color:#8e8e93;font-weight:600;'
            f'letter-spacing:0.04em;margin-bottom:4px">{label}</div>'
            f'<div style="font-size:1.8rem;font-weight:800;color:#fff">'
            f'{value:,}<span style="font-size:0.85rem;color:#636366;margin-left:3px">'
            f'{unit}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_daily_chart(stats: dict) -> None:
    st.markdown("#### 📈 일별 방문자")
    daily = stats.get("daily", {})
    if daily:
        st.line_chart(daily, height=200, use_container_width=True)
    else:
        st.caption("데이터 없음")


def _render_hourly_chart(stats: dict) -> None:
    st.markdown("#### ⏰ 시간대별 접속 (KST)")
    hourly = {f"{h:02d}시": stats["hourly"].get(h, 0) for h in range(24)}
    st.bar_chart(hourly, height=200, use_container_width=True)


def _render_feature_chart(stats: dict) -> None:
    st.markdown("#### 🔧 기능별 사용 현황")
    raw = stats.get("features", {})
    if not raw:
        st.caption("데이터 없음")
        return
    labeled = {FEATURE_LABELS.get(k, k): v for k, v in raw.items() if v}
    st.bar_chart(labeled, height=220, use_container_width=True)


def _render_recent_events(events: list[dict]) -> None:
    st.markdown("#### 📋 최근 이벤트 로그")
    rows = []
    for e in events:
        rows.append({
            "시간 (UTC)": e.get("created_at", "")[:16].replace("T", " "),
            "유형": e.get("event_type", ""),
            "페이지": FEATURE_LABELS.get(e.get("page", ""), e.get("page", "")),
            "세션ID": e.get("session_id", "")[:8],
        })
    if rows:
        st.dataframe(rows, use_container_width=True, height=300)


def _render_no_supabase() -> None:
    st.info(
        "Supabase가 연결되지 않아 **현재 세션** 데이터만 표시됩니다.  \n"
        "아래 연동 가이드를 따라 설정하면 누적 방문자 통계를 볼 수 있습니다."
    )
    mem = get_mem_stats()
    st.metric("현재 세션 이벤트 수", mem["session_events"])
    if mem["features"]:
        labeled = {FEATURE_LABELS.get(k, k): v for k, v in mem["features"].items()}
        st.bar_chart(labeled, height=200)
    _render_setup_guide()


def _render_setup_guide() -> None:
    with st.expander("🔧 Supabase 연동 가이드 (클릭해서 펼치기)"):
        st.markdown(
            """
**Step 1 — Supabase 프로젝트 생성** (무료, 카드 불필요)
→ [supabase.com](https://supabase.com) → New Project

**Step 2 — SQL Editor에서 테이블 생성:**
```sql
create table app_events (
  id        bigserial primary key,
  session_id text,
  event_type text,
  page       text,
  details    jsonb default '{}',
  created_at timestamptz default now()
);
create index on app_events (created_at desc);
create index on app_events (event_type);
```

**Step 3 — API 키 복사**
Project Settings → API
- `Project URL` → `SUPABASE_URL`
- `anon public` key → `SUPABASE_ANON_KEY`

**Step 4 — .env 에 추가:**
```
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGci...
ADMIN_PASSWORD=원하는_비밀번호
```

**Step 5 — Streamlit Cloud Secrets에도 동일하게 추가**
share.streamlit.io → 앱 → Settings → Secrets

---
이후 앱 사용자들의 방문·기능 사용이 자동으로 기록됩니다.
"""
        )
