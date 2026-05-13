"""
유튜브 크리에이터 도구
메인 앱 진입점
"""

import os
import streamlit as st
from dotenv import load_dotenv

# Streamlit secrets fallback (page_config 전에 로드해야 query_params 사용 가능)
load_dotenv()
for key in ["GEMINI_API_KEY", "YOUTUBE_API_KEY", "ADMIN_PASSWORD",
            "SUPABASE_URL", "SUPABASE_ANON_KEY",
            "AFFILIATE_BANNER_URL", "AFFILIATE_BANNER_IMG"]:
    if not os.environ.get(key):
        try:
            os.environ[key] = st.secrets[key]
        except Exception:
            pass

# 페이지 설정
st.set_page_config(
    page_title="유튜브 크리에이터 도구",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 어드민 라우팅 (URL에 ?admin=1 붙이면 대시보드로 이동) ──
if st.query_params.get("admin") == "1":
    from pages.admin_dashboard import render as render_admin
    render_admin()
    st.stop()

# ── 방문자 추적 ──
from utils.analytics import log_visit
log_visit()

# 커스텀 CSS 로드
css_path = os.path.join(os.path.dirname(__file__), "styles", "custom.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Google Fonts 임베드
st.markdown(
    '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">',
    unsafe_allow_html=True,
)

# Google Search Console 소유권 확인
st.markdown(
    '<meta name="google-site-verification" content="_Xcx4kSrTzJsEgH-nRvi-PBAa5sG8ROqO-Xkpghv-74" />',
    unsafe_allow_html=True,
)

# ── 헤더 ──
st.markdown(
    '<div class="app-title">유튜브 크리에이터 도구</div>'
    '<div class="app-subtitle">YOUTUBE CREATOR STUDIO</div>',
    unsafe_allow_html=True,
)

# ── API 키 검증 ──
gemini_key = os.environ.get("GEMINI_API_KEY", "")
youtube_key = os.environ.get("YOUTUBE_API_KEY", "")

if not gemini_key or not youtube_key:
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(
        '<div class="error-msg">'
        '⚙️ API 키가 설정되지 않았습니다. 아래에서 입력해주세요.'
        '</div>',
        unsafe_allow_html=True,
    )

    with st.container():
        if not gemini_key:
            g_key = st.text_input(
                "Gemini API Key",
                type="password",
                placeholder="AIza...",
            )
            if g_key:
                os.environ["GEMINI_API_KEY"] = g_key

        if not youtube_key:
            y_key = st.text_input(
                "YouTube API Key",
                type="password",
                placeholder="AIza...",
            )
            if y_key:
                os.environ["YOUTUBE_API_KEY"] = y_key

    st.markdown('<hr class="divider">', unsafe_allow_html=True)

# ── 탭 네비게이션 ──
tab1, tab2, tab3, tab4, tab5 = st.tabs(["⚡ 콘텐츠 생성기", "🔥 핫이슈 검색기", "📊 영상 분석기", "🚀 급성장 채널", "🔍 키워드 순위"])

with tab1:
    from pages.content_generator import render as render_content
    render_content()

with tab2:
    from pages.shorts_plugin import render as render_shorts_plugin
    render_shorts_plugin()

with tab3:
    from pages.video_analyzer import render as render_analyzer
    render_analyzer()

with tab4:
    from pages.growth_tracker import render as render_growth
    render_growth()

with tab5:
    from pages.keyword_search import render as render_keyword_search
    render_keyword_search()

# ── 하단 고정 배너 광고 ──
from utils.ads import render_sticky_footer
render_sticky_footer()
