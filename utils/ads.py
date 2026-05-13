import os
import streamlit as st
import streamlit.components.v1 as components


def render_adfit_banner():
    """Kakao AdFit 배너 (국내 광고 네트워크)"""
    unit_id = os.environ.get("ADFIT_UNIT_ID", "")
    if not unit_id:
        return
    width, height = 728, 90
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script type="text/javascript" src="//t1.daumcdn.net/kas/static/ba.min.js" async></script>
</head>
<body style="margin:0;padding:0;background:transparent;overflow:hidden;">
  <ins class="kakao_ad_area"
       style="display:none;"
       data-ad-unit="{unit_id}"
       data-ad-width="{width}"
       data-ad-height="{height}"></ins>
</body>
</html>"""
    _wrap(html, height)


def render_adsense_banner():
    """Google AdSense 배너"""
    client = os.environ.get("ADSENSE_CLIENT_ID", "")
    slot = os.environ.get("ADSENSE_SLOT_ID", "")
    if not client or not slot:
        return
    width, height = 728, 90
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={client}" crossorigin="anonymous"></script>
</head>
<body style="margin:0;padding:0;background:transparent;overflow:hidden;">
  <ins class="adsbygoogle"
       style="display:block;width:{width}px;height:{height}px;"
       data-ad-client="{client}"
       data-ad-slot="{slot}"
       data-ad-format="fixed"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
</body>
</html>"""
    _wrap(html, height)


def render_affiliate_banner():
    """쿠팡파트너스 / 기타 제휴 이미지 배너 (JS 불필요, 가장 안정적)"""
    href = os.environ.get("AFFILIATE_BANNER_URL", "")
    image = os.environ.get("AFFILIATE_BANNER_IMG", "")
    if not href or not image:
        return
    st.markdown(
        f'<div class="ad-banner-wrapper">'
        f'  <span class="ad-label">AD</span>'
        f'  <a href="{href}" target="_blank" rel="noopener sponsored">'
        f'    <img src="{image}" class="ad-banner-img" alt="광고">'
        f'  </a>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_banner():
    """활성화된 광고 네트워크를 자동 선택해서 렌더링"""
    if os.environ.get("ADFIT_UNIT_ID"):
        render_adfit_banner()
    elif os.environ.get("ADSENSE_CLIENT_ID"):
        render_adsense_banner()
    elif os.environ.get("AFFILIATE_BANNER_URL"):
        render_affiliate_banner()


def _wrap(html: str, ad_height: int):
    """광고 iframe을 AD 라벨과 함께 감싸서 표시"""
    st.markdown('<div class="ad-banner-wrapper"><span class="ad-label">AD</span></div>', unsafe_allow_html=True)
    components.html(html, height=ad_height + 4, scrolling=False)
