"""
Hot issue to Shorts automation page.
"""

import os

import streamlit as st

from utils.gemini_client import score_news_relevance
from utils.shorts_timeline import (
    export_srt,
    export_timeline_json,
    fallback_shorts_package,
    generate_shorts_package,
)
from utils.social_trend_fetcher import fetch_social_trends


DEFAULT_TONE = "담백한 비평, 빠른 호흡, 과장 없는 온라인 이슈 해설"


def render():
    from utils.analytics import log_event
    log_event("page_view", "shorts_plugin")
    st.markdown('<p class="section-header">핫이슈 검색기</p>', unsafe_allow_html=True)

    st.caption("디시인사이드, 커뮤니티 최근 이슈, Google Trends, X API를 모아 9:16 쇼츠용 타임라인과 자막을 만듭니다.")

    col_left, col_right = st.columns([1, 1])
    with col_left:
        include_dcinside = st.checkbox("디시인사이드 최근 이슈", value=True)
        include_ilbe = st.checkbox("커뮤니티 최근 이슈", value=True)
        include_google = st.checkbox("Google Trends 최근 이슈", value=True)
        include_x = st.checkbox("X/Twitter 최근 이슈", value=True)
    with col_right:
        optional_keywords = st.text_area(
            "추가 필터 키워드",
            placeholder="비워두면 기본 최근 이슈 쿼리로 자동 수집",
            height=90,
        )
        dc_rss_urls = st.text_area(
            "추가 RSS URL",
            placeholder="원하면 공개 RSS URL을 한 줄에 하나씩 추가",
            height=90,
        )
        tone = st.text_input("쇼츠 톤", value=DEFAULT_TONE)

    col_fetch, col_hint = st.columns([1, 2])
    with col_fetch:
        fetch_clicked = st.button("핫이슈 수집", use_container_width=True)
    with col_hint:
        if not os.environ.get("TWITTER_BEARER_TOKEN"):
            st.caption("X/Twitter는 로그인 우회 없이 공식 API 토큰이 있을 때만 자동 수집됩니다.")

    if fetch_clicked:
        with st.spinner("핫이슈를 수집하고 있습니다..."):
            try:
                trends = fetch_social_trends(
                    keywords=optional_keywords,
                    dcinside_rss_urls=dc_rss_urls,
                    include_google_trends=include_google,
                    include_dcinside=include_dcinside,
                    include_ilbe=include_ilbe,
                    include_x=include_x,
                    max_items=60,
                )
                if trends:
                    with st.spinner("채널 톤과 맞는 이슈를 정렬하고 있습니다..."):
                        try:
                            trends = score_news_relevance(trends, tone)
                        except Exception:
                            pass
                st.session_state["social_trends"] = trends
            except Exception as exc:
                st.error(str(exc))

    _render_trend_list(tone)
    _render_package()


def _render_trend_list(tone: str):
    trends = st.session_state.get("social_trends", [])
    if not trends:
        return

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">최근 이슈 리스트</p>', unsafe_allow_html=True)

    for index, item in enumerate(trends[:30]):
        score = item.get("relevance_score", 0)
        badge_class = "relevance-high" if score >= 70 else "relevance-mid" if score >= 40 else "relevance-low"
        url = item.get("url") or "#"
        source_label = item.get("source_label") or item.get("source", "출처 미상")
        platform = item.get("platform", "web")
        card_html = f"""
        <div class="news-card">
            <div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">
                <span style="background:#2c2c2e; color:#ffffff; border:1px solid #3a3a3c; border-radius:8px; padding:3px 8px; font-size:0.72rem; font-weight:700;">{source_label}</span>
                <span style="color:#8e8e93; font-size:0.74rem;">{platform}</span>
            </div>
            <div style="display:flex; justify-content:space-between; gap:12px; align-items:flex-start;">
                <div class="news-card-title">
                    <a href="{url}" target="_blank" style="color:#fff; text-decoration:none;">{item.get("title", "")}</a>
                </div>
                <span class="relevance-badge {badge_class}">{score}</span>
            </div>
            <div style="color:#8e8e93; font-size:0.88rem; line-height:1.55; margin-top:8px;">{item.get("summary", "")[:220]}</div>
            <div class="news-card-meta" style="margin-top:10px; color:#636366; font-size:0.78rem;">
                출처 URL: {item.get("source", "")} · {item.get("time", "")} · {item.get("traffic", "")}
            </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

        if st.button("이 이슈로 쇼츠 만들기", key=f"make_shorts_{index}"):
            st.session_state["selected_social_trend"] = item
            _generate_package(item, tone)
            st.rerun()


def _generate_package(item: dict, tone: str):
    duration = st.session_state.get("shorts_duration", 45)
    try:
        st.session_state["shorts_package"] = generate_shorts_package(item, tone, duration)
        st.session_state["shorts_package_source"] = "ai"
    except Exception as exc:
        st.session_state["shorts_package"] = fallback_shorts_package(item, tone, duration)
        st.session_state["shorts_package_source"] = f"fallback: {exc}"


def _render_package():
    package = st.session_state.get("shorts_package")
    if not package:
        return

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<p class="section-header">쇼츠 타임라인</p>', unsafe_allow_html=True)

    source = st.session_state.get("shorts_package_source", "")
    if source.startswith("fallback"):
        st.warning("Gemini 생성에 실패해 기본 템플릿으로 구성했습니다. API 키를 확인하면 더 정교하게 생성됩니다.")

    duration = st.slider(
        "영상 길이",
        min_value=20,
        max_value=60,
        value=st.session_state.get("shorts_duration", 45),
        step=5,
        key="shorts_duration",
    )

    st.subheader(package.get("headline", "쇼츠 기획안"))
    st.write(package.get("summary", ""))
    if package.get("hashtags"):
        st.caption(" ".join(package["hashtags"]))

    scenes = package.get("scenes", [])
    for scene in scenes:
        with st.expander(f'{scene.get("start", 0)}s-{scene.get("end", 0)}s · {scene.get("title", "장면")}', expanded=True):
            st.write(scene.get("narration", ""))
            st.text_input("자막", value=scene.get("subtitle", ""), key=f'subtitle_{scene.get("start", 0)}')
            st.text_area("이미지 생성 프롬프트", value=scene.get("image_prompt", ""), height=90, key=f'prompt_{scene.get("start", 0)}')
            st.caption(scene.get("visual_note", ""))

    srt_text = export_srt(scenes)
    timeline_json = export_timeline_json(package)

    col_srt, col_json = st.columns(2)
    with col_srt:
        st.download_button(
            "SRT 자막 다운로드",
            data=srt_text,
            file_name="shorts_subtitles.srt",
            mime="text/plain",
            use_container_width=True,
        )
    with col_json:
        st.download_button(
            "타임라인 JSON 다운로드",
            data=timeline_json,
            file_name="shorts_timeline.json",
            mime="application/json",
            use_container_width=True,
        )

    with st.expander("SRT 미리보기"):
        st.code(srt_text, language="srt")
