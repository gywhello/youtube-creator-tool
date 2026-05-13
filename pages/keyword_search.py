"""키워드 조회수 순위 검색기"""

import html as html_lib
import streamlit as st
from datetime import datetime, timedelta, timezone
from utils.youtube_client import search_videos_by_keyword
from utils.gemini_client import analyze_keyword_videos_batch

HOOK_TYPE_COLORS = {
    "트렌드 편승":   ("#0a84ff", "rgba(10,132,255,0.12)"),
    "감정 자극":     ("#bf5af2", "rgba(191,90,242,0.12)"),
    "정보성":        ("#30d158", "rgba(48,209,88,0.12)"),
    "충격/논란":     ("#ff453a", "rgba(255,69,58,0.12)"),
    "유명인 효과":   ("#ff375f", "rgba(255,55,95,0.12)"),
    "실용 정보":     ("#34c759", "rgba(52,199,89,0.12)"),
    "호기심 유발":   ("#ff9f0a", "rgba(255,159,10,0.12)"),
    "커뮤니티 공감": ("#64d2ff", "rgba(100,210,255,0.12)"),
}


def _esc(text: str) -> str:
    return html_lib.escape(str(text))


def render():
    from utils.analytics import log_event
    log_event("page_view", "keyword_search")
    st.markdown('<p class="section-header">키워드 조회수 순위</p>', unsafe_allow_html=True)

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        keyword = st.text_input(
            "검색 키워드",
            placeholder="예: 요리 레시피, 영어 공부, 주식 투자...",
            label_visibility="collapsed",
            key="keyword_search_input",
        )
    with col_btn:
        search_clicked = st.button("검색", use_container_width=True)

    with st.expander("🎛️ 필터 설정"):
        f1, f2, f3 = st.columns(3)
        with f1:
            max_results = st.selectbox("결과 수", [10, 25, 50], index=1)
        with f2:
            period = st.selectbox("기간", ["전체", "최근 7일", "최근 30일", "최근 1년"], index=0)
        with f3:
            duration_filter = st.selectbox("영상 길이", ["전체", "쇼트 (4분 이하)", "일반 (4~20분)", "롱폼 (20분 이상)"], index=0)

    if search_clicked and keyword:
        published_after = None
        now = datetime.now(timezone.utc)
        if period == "최근 7일":
            published_after = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif period == "최근 30일":
            published_after = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        elif period == "최근 1년":
            published_after = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")

        video_duration = None
        if duration_filter == "쇼트 (4분 이하)":
            video_duration = "short"
        elif duration_filter == "일반 (4~20분)":
            video_duration = "medium"
        elif duration_filter == "롱폼 (20분 이상)":
            video_duration = "long"

        with st.spinner(f"'{keyword}' 검색 중..."):
            try:
                results = search_videos_by_keyword(
                    keyword=keyword,
                    max_results=max_results,
                    published_after=published_after,
                    video_duration=video_duration,
                )
                st.session_state["keyword_results"] = results
                st.session_state["keyword_query"] = keyword
                st.session_state.pop("keyword_analysis", None)
            except Exception as e:
                st.markdown(f'<div class="error-msg">❌ 검색 오류: {_esc(str(e))}</div>', unsafe_allow_html=True)
                return

        if results:
            with st.spinner("AI가 각 영상의 성공 이유를 분석하고 있습니다..."):
                try:
                    analysis = analyze_keyword_videos_batch(results)
                    # "분석 실패" / "분석 불가" 항목은 None 처리
                    cleaned = []
                    for item in analysis:
                        if item.get("one_line", "") in ("분석 실패", "분석 불가", ""):
                            cleaned.append(None)
                        else:
                            cleaned.append(item)
                    st.session_state["keyword_analysis"] = cleaned
                except Exception:
                    st.session_state["keyword_analysis"] = None

    if "keyword_results" not in st.session_state:
        return

    results = st.session_state["keyword_results"]
    query = st.session_state.get("keyword_query", "")
    analysis_list = st.session_state.get("keyword_analysis") or []

    if not results:
        st.info("검색 결과가 없습니다. 다른 키워드를 시도해보세요.")
        return

    has_analysis = any(a is not None for a in analysis_list)

    st.markdown(
        f'<div style="color:#8e8e93;font-size:0.9rem;margin:16px 0 20px;">'
        f'<strong style="color:#fff;">&quot;{_esc(query)}&quot;</strong> 검색 결과 &mdash; '
        f'조회수 높은 순 {len(results)}개'
        f'{"&nbsp;&nbsp;&middot;&nbsp;&nbsp;🤖 AI 분석 포함" if has_analysis else ""}'
        f'</div>',
        unsafe_allow_html=True,
    )

    rank_colors = ["#FFD700", "#C0C0C0", "#CD7F32"]
    rank_icons  = ["🥇", "🥈", "🥉"]

    for i, video in enumerate(results):
        rank       = i + 1
        rank_color = rank_colors[i] if i < 3 else "#636366"
        rank_label = rank_icons[i]  if i < 3 else f"#{rank}"
        rank_font  = "1.5rem"       if i < 3 else "0.95rem"
        video_url  = f"https://www.youtube.com/watch?v={video['video_id']}"
        ai         = analysis_list[i] if analysis_list and i < len(analysis_list) else None

        # ── 영상 정보 영역 ──
        duration_part = f" &middot; {_esc(video['duration'])}" if video['duration'] else ""

        left_html = (
            f'<div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:6px;">'
            f'<a href="{video_url}" target="_blank"'
            f' style="font-size:0.95rem;font-weight:600;color:#fff;text-decoration:none;line-height:1.4;display:block;">'
            f'{_esc(video["title"])}</a>'
            f'<div style="color:#8e8e93;font-size:0.76rem;">'
            f'{_esc(video["channel"])} &middot; {_esc(video["published_at"])}{duration_part}</div>'
            f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:2px;">'
            f'<span style="font-size:0.85rem;font-weight:700;color:#0a84ff;">👁 {_esc(video["views_formatted"])}</span>'
            f'<span style="font-size:0.85rem;color:#8e8e93;">👍 {_esc(video["likes_formatted"])}</span>'
            f'<span style="font-size:0.85rem;color:#8e8e93;">💬 {_esc(video["comments_formatted"])}</span>'
            f'</div>'
            f'</div>'
        )

        # ── AI 분석 패널 ──
        right_html = ""
        if ai:
            hook_type  = _esc(ai.get("hook_type", ""))
            one_line   = _esc(ai.get("one_line", ""))
            factors    = ai.get("factors", [])
            hook_color, hook_bg = HOOK_TYPE_COLORS.get(ai.get("hook_type", ""), ("#8e8e93", "rgba(142,142,147,0.12)"))

            factors_tags = "".join(
                f'<span style="display:inline-block;margin:2px 4px 2px 0;background:rgba(255,255,255,0.06);border:1px solid #3a3a3c;border-radius:6px;padding:3px 9px;font-size:0.75rem;color:#c4c4c6;">{_esc(f)}</span>'
                for f in factors
            )

            right_html = (
                f'<div style="width:36%;flex-shrink:0;background:{hook_bg};border:1px solid {hook_color}44;border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:10px;">'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<span style="background:{hook_bg};border:1px solid {hook_color};color:{hook_color};border-radius:6px;padding:2px 9px;font-size:0.72rem;font-weight:700;white-space:nowrap;">{hook_type}</span>'
                f'<span style="font-size:0.7rem;color:#636366;">AI 분석</span>'
                f'</div>'
                f'<div style="font-size:0.88rem;font-weight:600;color:#fff;line-height:1.45;">{one_line}</div>'
                f'<div>{factors_tags}</div>'
                f'</div>'
            )

        card = (
            f'<div style="background:#1c1c1e;border:1px solid #3a3a3c;border-radius:16px;padding:16px;margin-bottom:10px;display:flex;gap:14px;align-items:flex-start;">'
            f'<div style="font-size:{rank_font};font-weight:700;color:{rank_color};min-width:40px;text-align:center;padding-top:6px;flex-shrink:0;">{rank_label}</div>'
            f'<img src="{_esc(video["thumbnail_url"])}" width="124" height="70" style="object-fit:cover;border-radius:10px;flex-shrink:0;">'
            f'{left_html}'
            f'{right_html}'
            f'</div>'
        )

        st.markdown(card, unsafe_allow_html=True)
