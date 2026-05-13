"""유튜버 정보 공유 커뮤니티 - Threads 스타일"""
from __future__ import annotations

import html
import os
import time
import uuid
from datetime import datetime, timezone

import requests
import streamlit as st

_TABLE  = "community_posts"
_BUCKET = "community-media"
_AVATAR_COLORS = [
    "#5856d6", "#a78bfa", "#0a84ff", "#32d74b",
    "#ff9f0a", "#ff6b6b", "#bf5af2", "#30d158",
]
_MAX_IMG_MB = 5
_MAX_VID_MB = 50
_CATEGORIES = ["전체", "팁 공유", "채널 공유", "질문", "성공 사례", "자유"]


# ── helpers ────────────────────────────────────────────────────────────────

def _cfg() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_ANON_KEY", "")


def _hdr(key: str, extra: dict | None = None) -> dict:
    h = {"apikey": key, "Authorization": f"Bearer {key}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _color(text: str) -> str:
    return _AVATAR_COLORS[abs(hash(text or "익")) % len(_AVATAR_COLORS)]


def _initial(text: str) -> str:
    t = (text or "익").strip()
    return t[0].upper() if t else "익"


def _rel_time(iso: str) -> str:
    if not iso:
        return "방금"
    try:
        dt   = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = int((datetime.now(timezone.utc) - dt).total_seconds())
        if diff < 60:    return "방금"
        if diff < 3600:  return f"{diff // 60}분 전"
        if diff < 86400: return f"{diff // 3600}시간 전"
        return f"{diff // 86400}일 전"
    except Exception:
        return iso[:10]


# ── Supabase ───────────────────────────────────────────────────────────────

def _fetch_posts(category: str) -> list[dict]:
    url, key = _cfg()
    if not url or not key:
        return []
    params: dict = {"select": "*", "order": "created_at.desc", "limit": "80"}
    if category != "전체":
        params["category"] = f"eq.{category}"
    try:
        r = requests.get(f"{url}/rest/v1/{_TABLE}",
                         headers=_hdr(key), params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return []


def _create_post(nick: str, content: str,
                 media_url: str = "", media_type: str = "") -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    payload: dict = {
        "nickname": nick.strip() or "익명",
        "category": "자유",
        "title": content.strip()[:60],
        "content": content.strip(),
    }
    if media_url:
        payload["media_url"]  = media_url
        payload["media_type"] = media_type
    try:
        r = requests.post(f"{url}/rest/v1/{_TABLE}",
                          headers=_hdr(key, {"Prefer": "return=minimal"}),
                          json=payload, timeout=10)
        r.raise_for_status()
        return True
    except Exception:
        return False


def _increment_likes(post_id: int, current: int) -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    try:
        r = requests.patch(f"{url}/rest/v1/{_TABLE}",
                           headers=_hdr(key, {"Prefer": "return=minimal"}),
                           params={"id": f"eq.{post_id}"},
                           json={"likes": current + 1}, timeout=10)
        r.raise_for_status()
        return True
    except Exception:
        return False


def _upload_file(data: bytes, filename: str, content_type: str) -> str | None:
    url, key = _cfg()
    if not url or not key:
        return None
    try:
        r = requests.post(
            f"{url}/storage/v1/object/{_BUCKET}/{filename}",
            headers={"apikey": key, "Authorization": f"Bearer {key}",
                     "Content-Type": content_type},
            data=data, timeout=60,
        )
        if r.status_code in (200, 201):
            return f"{url}/storage/v1/object/public/{_BUCKET}/{filename}"
        return None
    except Exception:
        return None


# ── render ─────────────────────────────────────────────────────────────────

def render() -> None:
    from utils.analytics import log_event
    log_event("page_view", "community")

    # 하트 버튼 스타일 - 테두리·배경 제거
    st.markdown("""
    <style>
    [data-testid="stBaseButton-secondary"] {
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
        padding: 2px 6px !important;
        min-height: 0 !important;
        color: #ff375f !important;
        font-size: 0.95rem !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        background: rgba(255,55,95,0.08) !important;
        border-radius: 8px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown(
        '<p class="section-header" style="margin-bottom:4px;">커뮤니티</p>',
        unsafe_allow_html=True,
    )

    url, key = _cfg()
    if not url or not key:
        st.warning("Supabase가 연결되지 않아 커뮤니티를 사용할 수 없습니다.")
        return

    _render_compose()

    # 카테고리 필터
    cat = st.radio("", _CATEGORIES, horizontal=True, key="comm_cat",
                   label_visibility="collapsed")

    posts = _fetch_posts(cat)
    st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

    if not posts:
        st.markdown(
            '<div style="text-align:center;color:#636366;padding:4rem 0;'
            'font-size:0.88rem;">아직 게시글이 없어요. 첫 번째 스레드를 시작해보세요 🧵</div>',
            unsafe_allow_html=True,
        )
        return

    for post in posts:
        _render_card(post)


def _render_compose() -> None:
    remaining = max(0, int(30 - (time.time() - st.session_state.get("comm_last", 0))))

    nick_val = st.session_state.get("comm_nick", "")
    bg_color = _color(nick_val or "나")
    letter   = _initial(nick_val or "나")

    col_av, col_form = st.columns([1, 12])

    with col_av:
        st.markdown(
            f'<div style="width:44px;height:44px;border-radius:50%;'
            f'background:{bg_color};display:flex;align-items:center;'
            f'justify-content:center;font-weight:800;font-size:18px;'
            f'color:#fff;margin-top:10px;">{letter}</div>',
            unsafe_allow_html=True,
        )

    with col_form:
        if remaining:
            st.markdown(
                f'<div style="color:#636366;font-size:0.82rem;padding:14px 0;">'
                f'⏳ {remaining}초 후 다시 작성 가능합니다.</div>',
                unsafe_allow_html=True,
            )
        else:
            nick    = st.text_input("", placeholder="닉네임 (선택)",
                                    max_chars=20, key="comm_nick",
                                    label_visibility="collapsed")
            content = st.text_area("", placeholder="무슨 생각을 하고 있나요?",
                                   max_chars=1500, height=90, key="comm_content",
                                   label_visibility="collapsed")

            media_file = st.file_uploader(
                "📎 사진 또는 영상 드래그앤드롭",
                type=["jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "webm"],
                key="comm_media",
                label_visibility="visible",
            )

            if media_file:
                if media_file.type.startswith("image"):
                    st.image(media_file, width=280)
                else:
                    st.video(media_file)

            _, btn_col = st.columns([8, 2])
            with btn_col:
                if st.button("게시", type="primary", key="comm_submit",
                             use_container_width=True):
                    if not content.strip():
                        st.error("내용을 입력해주세요.")
                        return

                    media_url, media_type = "", ""

                    if media_file:
                        is_img = media_file.type.startswith("image")
                        limit  = _MAX_IMG_MB if is_img else _MAX_VID_MB
                        if len(media_file.getvalue()) > limit * 1024 * 1024:
                            st.error(f"{'이미지' if is_img else '영상'}는 {limit}MB 이하만 가능합니다.")
                            return
                        ext = media_file.name.rsplit(".", 1)[-1]
                        with st.spinner("업로드 중..."):
                            media_url  = _upload_file(
                                media_file.getvalue(),
                                f"{uuid.uuid4().hex}.{ext}",
                                media_file.type,
                            ) or ""
                        media_type = "image" if is_img else "video"

                    if _create_post(nick, content, media_url, media_type):
                        st.session_state.comm_last = time.time()
                        for k in ["comm_nick", "comm_content", "comm_media"]:
                            st.session_state.pop(k, None)
                        st.success("게시되었습니다! 🎉")
                        st.rerun()
                    else:
                        st.error("게시 실패. 다시 시도해주세요.")

    st.markdown(
        '<hr style="border:none;border-top:1px solid #3a3a3c;margin:14px 0 16px;">',
        unsafe_allow_html=True,
    )


def _render_card(post: dict) -> None:
    post_id    = post.get("id", 0)
    liked_key  = f"comm_liked_{post_id}"
    already_liked = st.session_state.get(liked_key, False)

    nick_raw   = post.get("nickname", "익명") or "익명"
    nick       = html.escape(nick_raw)
    body       = html.escape(post.get("content", "")).replace("\n", "<br>")
    likes      = post.get("likes", 0)
    media_url  = post.get("media_url") or ""
    media_type = post.get("media_type") or ""
    t_label    = _rel_time(post.get("created_at", ""))
    bg_color   = _color(nick_raw)
    letter     = _initial(nick_raw)

    col_av, col_body = st.columns([1, 12])

    with col_av:
        st.markdown(
            f'<div style="width:44px;height:44px;border-radius:50%;'
            f'background:{bg_color};display:flex;align-items:center;'
            f'justify-content:center;font-weight:800;font-size:18px;'
            f'color:#fff;margin-top:6px;">{letter}</div>',
            unsafe_allow_html=True,
        )

    with col_body:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;">'
            f'<span style="font-weight:700;font-size:0.9rem;color:#e8e8ed;">{nick}</span>'
            f'<span style="color:#48484a;">·</span>'
            f'<span style="color:#636366;font-size:0.75rem;">{t_label}</span>'
            f'</div>'
            f'<div style="color:#e8e8ed;font-size:0.85rem;line-height:1.7;'
            f'margin-bottom:8px;">{body}</div>',
            unsafe_allow_html=True,
        )

        if media_url:
            if media_type == "image":
                st.image(media_url, use_container_width=True)
            elif media_type == "video":
                st.video(media_url)

        # 하트 버튼 - 우측 하단
        _, heart_col = st.columns([10, 2])
        with heart_col:
            heart = "❤️" if already_liked else "🤍"
            if st.button(f"{heart} {likes}", key=f"comm_like_{post_id}"):
                if not already_liked:
                    if _increment_likes(post_id, likes):
                        st.session_state[liked_key] = True
                        st.rerun()

    st.markdown(
        '<hr style="border:none;border-top:1px solid #2c2c2e;margin:8px 0 16px;">',
        unsafe_allow_html=True,
    )
