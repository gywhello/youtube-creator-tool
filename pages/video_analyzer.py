"""
기능 2: 유튜브 영상 성공 구조 분석기
"""

import streamlit as st
import requests
from utils.youtube_client import get_video_data, extract_video_id
from utils.transcript import get_transcript
from utils.gemini_client import (
    analyze_video_structure,
    analyze_thumbnail_from_bytes,
    compare_videos,
)
from utils.pdf_export import generate_report_pdf, generate_text_report


def render():
    """영상 분석기 탭을 렌더링합니다."""
    from utils.analytics import log_event
    log_event("page_view", "video_analyzer")

    st.markdown('<p class="section-header">유튜브 영상 분석</p>', unsafe_allow_html=True)

    # ── 영상 링크 입력 ──
    url1 = st.text_input(
        "영상 링크 1 (필수)",
        placeholder="https://www.youtube.com/watch?v=...",
        key="video_url_1",
    )

    with st.expander("🔗 경쟁 영상 비교 (선택 — 최대 2개 추가)"):
        url2 = st.text_input(
            "영상 링크 2",
            placeholder="https://www.youtube.com/watch?v=...",
            key="video_url_2",
        )
        url3 = st.text_input(
            "영상 링크 3",
            placeholder="https://www.youtube.com/watch?v=...",
            key="video_url_3",
        )

    analyze_clicked = st.button("🔬 분석 시작", use_container_width=True)

    if analyze_clicked and url1:
        urls = [url1]
        if url2: urls.append(url2)
        if url3: urls.append(url3)

        all_data = []

        for idx, url in enumerate(urls):
            with st.spinner(f"영상 {idx + 1} 데이터를 수집하고 있습니다..."):
                try:
                    data = get_video_data(url)
                    all_data.append(data)
                except Exception as e:
                    st.markdown(
                        f'<div class="error-msg">❌ 영상 {idx + 1}: {str(e)}</div>',
                        unsafe_allow_html=True,
                    )

        if all_data:
            st.session_state["analysis_data"] = all_data

            # 첫 번째 영상에 대해 심화 분석
            primary = all_data[0]

            # 자막 추출
            with st.spinner("자막을 추출하고 있습니다..."):
                transcript_text = get_transcript(primary["video_id"])
                st.session_state["transcript_text"] = transcript_text

            # 구조 분석
            if transcript_text:
                with st.spinner("AI가 영상 구조를 분석하고 있습니다..."):
                    try:
                        analysis = analyze_video_structure(transcript_text)
                        st.session_state["structure_analysis"] = analysis
                    except Exception as e:
                        st.session_state["structure_analysis"] = None
                        st.warning(f"구조 분석 중 오류: {str(e)}")
            else:
                st.session_state["structure_analysis"] = None

            # 썸네일 분석
            if primary.get("thumbnail_url"):
                with st.spinner("AI가 썸네일을 분석하고 있습니다..."):
                    try:
                        thumb_resp = requests.get(primary["thumbnail_url"], timeout=10)
                        thumb_bytes = thumb_resp.content
                        thumb_analysis = analyze_thumbnail_from_bytes(thumb_bytes)
                        st.session_state["thumbnail_analysis"] = thumb_analysis
                    except Exception as e:
                        st.session_state["thumbnail_analysis"] = None
                        st.warning(f"썸네일 분석 중 오류: {str(e)}")

            # 경쟁 비교
            if len(all_data) > 1:
                with st.spinner("경쟁 영상을 비교 분석하고 있습니다..."):
                    try:
                        comp_data = []
                        for d in all_data:
                            comp_data.append({
                                'title': d['title'],
                                'channel': d['channel'],
                                'subscribers': d['subscribers'],
                                'views': d['views_formatted'],
                                'likes': d['likes_formatted'],
                                'comments': d['comments_formatted'],
                                'like_ratio': d['like_ratio'],
                                'comment_ratio': d['comment_ratio'],
                                'duration': d['duration'],
                            })
                        comparison = compare_videos(comp_data)
                        st.session_state["comparison_result"] = comparison
                    except Exception as e:
                        st.session_state["comparison_result"] = None

    # ── 결과 표시 ──
    if "analysis_data" in st.session_state:
        all_data = st.session_state["analysis_data"]
        primary = all_data[0]

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ── 저장 버튼 (상단) ──
        save_col1, save_col2, save_col3 = st.columns([2, 1, 1])
        with save_col1:
            st.markdown(
                f'<div style="font-size: 1.1rem; color: #e8e8ed; font-weight: 500;">{primary["title"]}</div>',
                unsafe_allow_html=True,
            )
        with save_col2:
            text_report = generate_text_report(
                primary,
                st.session_state.get("structure_analysis"),
                st.session_state.get("thumbnail_analysis"),
            )
            st.download_button(
                "📄 텍스트 저장",
                data=text_report,
                file_name="분석리포트.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with save_col3:
            try:
                pdf_bytes = generate_report_pdf(
                    primary,
                    st.session_state.get("structure_analysis"),
                    st.session_state.get("thumbnail_analysis"),
                )
                st.download_button(
                    "📋 PDF 저장",
                    data=pdf_bytes,
                    file_name="분석리포트.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception:
                st.download_button(
                    "📋 PDF 저장",
                    data=text_report,
                    file_name="분석리포트.txt",
                    mime="text/plain",
                    use_container_width=True,
                    disabled=True,
                )

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ── 기본 데이터 ──
        st.markdown('<p class="section-header">기본 데이터</p>', unsafe_allow_html=True)

        # 썸네일 + 기본 정보
        thumb_col, info_col = st.columns([1, 2])

        with thumb_col:
            if primary.get("thumbnail_url"):
                st.image(primary["thumbnail_url"], use_container_width=True)
            st.markdown(
                f'<div style="text-align: center; color: #6b6b7b; font-size: 0.75rem; margin-top: 0.3rem;">'
                f'{primary["channel"]} · 구독자 {primary["subscribers"]}</div>',
                unsafe_allow_html=True,
            )

        with info_col:
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(
                    f'<div class="metric-container">'
                    f'<div class="metric-value">{primary["views_formatted"]}</div>'
                    f'<div class="metric-label">조회수</div></div>',
                    unsafe_allow_html=True,
                )
            with m2:
                eval_badge = primary["like_eval"]
                st.markdown(
                    f'<div class="metric-container">'
                    f'<div class="metric-value">{primary["likes_formatted"]}</div>'
                    f'<div class="metric-label">좋아요</div>'
                    f'<div class="metric-sub">{primary["like_ratio"]}% '
                    f'<span class="badge-{eval_badge["badge"]}">{eval_badge["level"]}</span></div></div>',
                    unsafe_allow_html=True,
                )
            with m3:
                eval_badge_c = primary["comment_eval"]
                st.markdown(
                    f'<div class="metric-container">'
                    f'<div class="metric-value">{primary["comments_formatted"]}</div>'
                    f'<div class="metric-label">댓글</div>'
                    f'<div class="metric-sub">{primary["comment_ratio"]}% '
                    f'<span class="badge-{eval_badge_c["badge"]}">{eval_badge_c["level"]}</span></div></div>',
                    unsafe_allow_html=True,
                )

            m4, m5 = st.columns(2)
            with m4:
                st.markdown(
                    f'<div class="metric-container" style="margin-top: 0.5rem;">'
                    f'<div class="metric-value" style="font-size: 1.1rem;">{primary["upload_date"]}</div>'
                    f'<div class="metric-label">업로드일</div></div>',
                    unsafe_allow_html=True,
                )
            with m5:
                st.markdown(
                    f'<div class="metric-container" style="margin-top: 0.5rem;">'
                    f'<div class="metric-value" style="font-size: 1.1rem;">{primary["duration"]}</div>'
                    f'<div class="metric-label">영상 길이</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ── 구조 분석 ──
        analysis = st.session_state.get("structure_analysis")
        if analysis:
            st.markdown('<p class="section-header">영상 구조 분석</p>', unsafe_allow_html=True)

            # 후킹 문구
            hook = analysis.get("hook", "")
            if hook:
                st.markdown(
                    f'<div class="analysis-card">'
                    f'<h3>🎯 후킹 문구 (처음 15초)</h3>'
                    f'<p style="font-size: 1rem; color: #c4b5fd; font-style: italic;">"{hook}"</p></div>',
                    unsafe_allow_html=True,
                )

            # 전체 구조
            structure = analysis.get("structure", {})
            struct_labels = [("intro", "인트로", "🎬"), ("development", "전개", "📖"),
                           ("climax", "클라이맥스", "⚡"), ("outro", "아웃트로", "🔚")]
            struct_html = '<div class="analysis-card"><h3>📐 영상 구조</h3>'
            for key, label, icon in struct_labels:
                val = structure.get(key, "")
                if val:
                    struct_html += f'<p><strong style="color: #a78bfa;">{icon} {label}:</strong> {val}</p>'
            struct_html += '</div>'
            st.markdown(struct_html, unsafe_allow_html=True)

            # 감정선
            ef = analysis.get("emotion_flow", {})
            if ef:
                st.markdown(
                    f'<div class="analysis-card"><h3>💫 감정선 흐름</h3>'
                    f'<p>🌅 <strong>초반:</strong> {ef.get("early", "")}</p>'
                    f'<p>☀️ <strong>중반:</strong> {ef.get("middle", "")}</p>'
                    f'<p>🌙 <strong>후반:</strong> {ef.get("late", "")}</p></div>',
                    unsafe_allow_html=True,
                )

            # 키워드
            kw = analysis.get("top_keywords", [])
            if kw:
                kw_tags = " ".join([f'<span class="subtitle-line">{k}</span>' for k in kw[:10]])
                st.markdown(
                    f'<div class="analysis-card"><h3>🔑 반복 키워드 TOP 10</h3>'
                    f'<div>{kw_tags}</div></div>',
                    unsafe_allow_html=True,
                )

            # 이탈 위험
            risk = analysis.get("risk_sections", "")
            if risk:
                st.markdown(
                    f'<div class="analysis-card"><h3>⚠️ 시청자 이탈 위험 구간</h3>'
                    f'<p>{risk}</p></div>',
                    unsafe_allow_html=True,
                )

            # 성공 요인
            sf = analysis.get("success_factors", [])
            if sf:
                sf_html = '<div class="analysis-card"><h3>🏆 핵심 성공 요인</h3><ol>'
                for f_item in sf:
                    sf_html += f'<li style="margin-bottom: 0.5rem;">{f_item}</li>'
                sf_html += '</ol></div>'
                st.markdown(sf_html, unsafe_allow_html=True)

        elif st.session_state.get("transcript_text") == "":
            st.info("ℹ️ 이 영상에서 자막을 추출할 수 없어 구조 분석을 건너뛰었습니다.")

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ── 썸네일 분석 ──
        thumb_analysis = st.session_state.get("thumbnail_analysis")
        if thumb_analysis:
            st.markdown('<p class="section-header">썸네일 분석</p>', unsafe_allow_html=True)

            ta = thumb_analysis
            ta_html = f"""
            <div class="analysis-card">
                <h3>🖼️ 썸네일 AI 평가</h3>
                <p>📝 <strong>텍스트:</strong> {'포함' if ta.get('has_text') else '없음'}
                   (글자 수: {ta.get('text_count', 0)}자)</p>
                <p>👤 <strong>인물:</strong> {'포함' if ta.get('has_person') else '없음'}</p>
                <p>😊 <strong>감정 표현:</strong> {ta.get('emotion_level', 'N/A')}</p>
                <p>🖱️ <strong>클릭 유발 요소:</strong> {ta.get('click_factors', 'N/A')}</p>
                <p><strong style="color: #a78bfa;">💡 개선 제안:</strong></p>
                <ul>
            """
            for imp in ta.get("improvements", []):
                ta_html += f"<li>{imp}</li>"
            ta_html += "</ul></div>"
            st.markdown(ta_html, unsafe_allow_html=True)

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # ── 경쟁 비교 ──
        if len(all_data) > 1:
            st.markdown('<p class="section-header">경쟁 영상 비교</p>', unsafe_allow_html=True)

            # 비교 테이블
            table_html = '<table class="comparison-table"><thead><tr>'
            table_html += '<th>항목</th>'
            for d in all_data:
                table_html += f'<th>{d["title"][:25]}...</th>'
            table_html += '</tr></thead><tbody>'

            rows = [
                ("채널", "channel"), ("구독자", "subscribers"),
                ("조회수", "views_formatted"), ("좋아요", "likes_formatted"),
                ("댓글", "comments_formatted"), ("좋아요/조회수", "like_ratio"),
                ("댓글/조회수", "comment_ratio"), ("영상 길이", "duration"),
                ("업로드일", "upload_date"),
            ]

            for label, key in rows:
                table_html += f'<tr><td style="color: #a78bfa;">{label}</td>'
                for d in all_data:
                    val = d.get(key, "N/A")
                    if key in ("like_ratio", "comment_ratio"):
                        val = f"{val}%"
                    table_html += f'<td>{val}</td>'
                table_html += '</tr>'

            table_html += '</tbody></table>'
            st.markdown(table_html, unsafe_allow_html=True)

            # AI 종합 평가
            comparison = st.session_state.get("comparison_result")
            if comparison:
                st.markdown(
                    f'<div class="analysis-card"><h3>🤖 AI 종합 평가</h3>'
                    f'<p>{comparison}</p></div>',
                    unsafe_allow_html=True,
                )
