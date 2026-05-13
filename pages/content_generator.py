"""
기능 1: 뉴스 기반 자동 콘텐츠 생성기
"""

import streamlit as st
from utils.news_fetcher import fetch_trending_news
from utils.gemini_client import (
    score_news_relevance,
    generate_shorts_script,
    generate_image_prompt,
    split_subtitles,
)

DEFAULT_CONCEPTS = ""


def render():
    """콘텐츠 생성기 탭을 렌더링합니다."""

    # ── 채널 컨셉 입력 ──
    st.markdown('<p class="section-header">채널 컨셉 설정</p>', unsafe_allow_html=True)

    concepts = st.text_input(
        "채널 컨셉 키워드",
        value=st.session_state.get("concepts", DEFAULT_CONCEPTS),
        placeholder="쉼표로 구분하여 입력하세요...",
        label_visibility="collapsed",
    )
    st.session_state["concepts"] = concepts

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    # ── 뉴스 수집 ──
    st.markdown('<p class="section-header">오늘의 트렌드 뉴스</p>', unsafe_allow_html=True)

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        fetch_clicked = st.button("🔍 트렌드 가져오기", use_container_width=True)

    if fetch_clicked:
        with st.spinner("뉴스를 수집하고 있습니다..."):
            try:
                news_list = fetch_trending_news()
                if not news_list:
                    st.warning("수집된 뉴스가 없습니다. 잠시 후 다시 시도해주세요.")
                    return

                # AI 관련도 점수 매기기
                with st.spinner("AI가 채널 컨셉과의 관련도를 분석하고 있습니다..."):
                    news_list = score_news_relevance(news_list, concepts)

                st.session_state["news_list"] = news_list
            except Exception as e:
                st.markdown(f'<div class="error-msg">❌ {str(e)}</div>', unsafe_allow_html=True)
                return

    # ── 뉴스 카드 표시 ──
    if "news_list" in st.session_state and st.session_state["news_list"]:
        news_list = st.session_state["news_list"]

        for i, news in enumerate(news_list[:20]):
            score = news.get("relevance_score", 0)
            if score >= 70:
                badge_class = "relevance-high"
            elif score >= 40:
                badge_class = "relevance-mid"
            else:
                badge_class = "relevance-low"

            reason = news.get("relevance_reason", "")

            card_html = f"""
            <div class="news-card" style="animation-delay: {i * 0.05}s;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div class="news-card-title" style="flex: 1;">
                        <a href="{news.get('url', '#')}" target="_blank" style="color: #e8e8ed; text-decoration: none;">{news['title']}</a>
                    </div>
                    <span class="relevance-badge {badge_class}">{score}</span>
                </div>
                <div class="news-card-summary">{news['summary'][:120]}</div>
                {f'<div style="font-size: 0.72rem; color: #a78bfa; margin-bottom: 0.4rem;">💡 {reason}</div>' if reason else ''}
                <div class="news-card-meta">
                    <span><span class="news-card-source">{news['source']}</span> · {news['time']}</span>
                    <span>{news.get('traffic', '')}</span>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

            # 뉴스 선택 버튼 (버튼 클릭 시 session_state에 저장하고 rerun)
            if st.button(f"📝 이 뉴스로 대본 생성", key=f"select_news_{i}"):
                st.session_state["selected_news"] = news
                st.session_state.pop("generated_script", None)
                st.session_state.pop("generated_prompt", None)
                st.session_state.pop("generated_subtitles", None)
                st.rerun()

    # ── 대본 생성 ──
    if "selected_news" in st.session_state:
        selected = st.session_state["selected_news"]

        st.markdown('<hr class="divider">', unsafe_allow_html=True)
        st.markdown('<p class="section-header">쇼츠 대본 생성</p>', unsafe_allow_html=True)

        st.markdown(
            f'<div style="background: #16161f; border: 1px solid #2a2a3a; border-radius: 6px; padding: 0.8rem 1rem; margin-bottom: 1rem;">'
            f'<span style="color: #a78bfa; font-size: 0.75rem; letter-spacing: 0.1em;">선택된 뉴스</span><br>'
            f'<span style="color: #e8e8ed; font-size: 0.95rem;">{selected["title"]}</span></div>',
            unsafe_allow_html=True,
        )

        col_gen, col_regen = st.columns([1, 1])
        with col_gen:
            gen_clicked = st.button("✨ 대본 생성하기", use_container_width=True)
        with col_regen:
            regen_clicked = st.button("🔄 다시 생성", use_container_width=True)

        if gen_clicked or regen_clicked:
            with st.spinner("AI가 대본을 작성하고 있습니다..."):
                try:
                    script = generate_shorts_script(
                        selected["title"], selected["summary"], concepts
                    )
                    st.session_state["generated_script"] = script
                except Exception as e:
                    st.markdown(f'<div class="error-msg">❌ {str(e)}</div>', unsafe_allow_html=True)

            # 이미지 프롬프트 자동 생성
            if "generated_script" in st.session_state:
                with st.spinner("이미지 프롬프트를 생성하고 있습니다..."):
                    try:
                        prompt = generate_image_prompt(st.session_state["generated_script"])
                        st.session_state["generated_prompt"] = prompt
                    except Exception as e:
                        st.session_state["generated_prompt"] = f"프롬프트 생성 실패: {str(e)}"

                # 자막 자동 분리
                with st.spinner("자막을 분리하고 있습니다..."):
                    try:
                        subs = split_subtitles(st.session_state["generated_script"])
                        st.session_state["generated_subtitles"] = subs
                    except Exception as e:
                        st.session_state["generated_subtitles"] = []

        # ── 대본 표시 ──
        if "generated_script" in st.session_state:
            script = st.session_state["generated_script"]

            sections = [
                ("후킹", "hook", "3초 안에 시선을 잡는 첫 문장"),
                ("문제 제시", "problem", "공감을 유발하는 상황 설명"),
                ("핵심 내용", "core", "이슈의 핵심을 감성적으로 전달"),
                ("반전 · 인사이트", "twist", "예상 못한 시각 제시"),
                ("마무리", "closing", "비관적이고 현실적인 톤"),
            ]

            for label, key, desc in sections:
                content = script.get(key, "")
                st.markdown(
                    f'<div class="script-section">'
                    f'<span class="script-label">{label} — {desc}</span>'
                    f'<div class="script-content">{content}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # 전체 대본 복사용 텍스트
            full_script = "\n\n".join([
                f"[{s[0]}]\n{script.get(s[1], '')}" for s in sections
            ])

            st.text_area("전체 대본 (복사용)", value=full_script, height=200, label_visibility="collapsed")

            st.markdown('<hr class="divider">', unsafe_allow_html=True)

            # ── 이미지 프롬프트 ──
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown('<p class="section-header">AI 이미지 프롬프트</p>', unsafe_allow_html=True)

                if "generated_prompt" in st.session_state:
                    prompt_text = st.session_state["generated_prompt"]
                    st.markdown(
                        f'<div class="prompt-box">{prompt_text}</div>',
                        unsafe_allow_html=True,
                    )
                    st.text_area(
                        "프롬프트 복사용",
                        value=prompt_text,
                        height=120,
                        label_visibility="collapsed",
                        key="prompt_copy",
                    )

            with col_right:
                st.markdown('<p class="section-header">자막 텍스트 분리</p>', unsafe_allow_html=True)

                if "generated_subtitles" in st.session_state:
                    subs = st.session_state["generated_subtitles"]
                    if subs:
                        # 태그 형태로 표시
                        tags_html = "".join(
                            [f'<span class="subtitle-line">{s}</span>' for s in subs]
                        )
                        st.markdown(
                            f'<div class="subtitle-box">{tags_html}</div>',
                            unsafe_allow_html=True,
                        )

                        # 전체 자막 복사
                        all_subs = "\n".join(subs)
                        st.text_area(
                            "전체 자막 복사용",
                            value=all_subs,
                            height=150,
                            label_visibility="collapsed",
                            key="subs_copy",
                        )
                    else:
                        st.info("자막 분리 결과가 없습니다.")
