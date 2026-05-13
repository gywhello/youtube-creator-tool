"""유튜버 정보 공유 커뮤니티 - Threads 스타일"""
from __future__ import annotations

import html
import os
import time
import uuid
from datetime import datetime, timezone

import requests
import streamlit as st

_TABLE = "community_posts"
_BUCKET = "community-media"
_CATEGORIES = ["전체", "팁 공유", "채널 공유", "질문", "성공 사례", "자유"]
_WRITE_CATS = _CATEGORIES[1:]
_AVATAR_COLORS = [
    "#5856d6", "#a78bfa", "#0a84ff", "#32d74b",
    "#ff9f0a", "#ff6b6b", "#bf5af2", "#30d158",
]
_MAX_IMG_MB = 5
_MAX_VID_MB = 50


# ── helpers ────────────────────────────────────────────────────────────────

def _cfg() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_ANON_KEY", "")


def _hdr(key: str, extra: dict | None = None) -> dict:
    h = {"apikey": key, "Authorization": f"Bearer {key}",
         "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _avatar_color(text: str) -> str:
    return _AVATAR_COLORS[abs(hash(text or "익")) % len(_AVATAR_COLORS)]


def _initial(text: str) -> str:
    t = (text or "익").strip()
    return t[0].upper() if t else "익"


def _rel_time(iso: str) -> str:
    if not iso:
        return "방금"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        diff = int((datetime.now(timezone.utc) - dt).total_seconds())
        if diff < 60:
            return "방금"
        if diff < 3600:
            return f"{diff // 60}분 전"
        if diff < 86400:
            return f"{diff // 3600}시간 전"
        return f"{diff // 86400}일 전"
    except Exception:
        return iso[:10]


def _avatar_html(nick: str, size: int = 42) -> str:
    color = _avatar_color(nick)
    letter = _initial(nick)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:{color};display:flex;align-items:center;justify-content:center;'
        f'font-weight:800;font-size:{size // 2.5:.0f}px;color:#fff;'
        f'flex-shrink:0;">{letter}</div>'
    )


# ── Supabase calls ─────────────────────────────────────────────────────────

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


def _create_post(nick: str, cat: str, title: str, content: str,
                 media_url: str = "", media_type: str = "") -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    payload: dict = {
        "nickname": nick.strip() or "익명",
        "category": cat,
        "title": title.strip(),
        "content": content.strip(),
    }
    if media_url:
        payload["media_url"] = media_url
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

    st.markdown(
        '<p class="section-header" style="margin-bottom:4px;">커뮤니티</p>'
        '<p style="color:#636366;font-size:0.78rem;margin-bottom:1rem;">'
        '유튜버들끼리 팁·채널·성공 사례를 자유롭게 공유해요</p>',
        unsafe_allow_html=True,
    )

    url, key = _cfg()
    if not url or not key:
        st.warning("Supabase가 연결되지 않아 커뮤니티를 사용할 수 없습니다.")
        return

    _render_compose()

    cat = st.radio("", _CATEGORIES, horizontal=True, key="comm_cat",
                   label_visibility="collapsed")

    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    posts = _fetch_posts(cat)
    if not posts:
        st.markdown(
            '<div style="text-align:center;color:#636366;padding:4rem 0;'
            'font-size:0.88rem;">아직 게시글이 없어요.<br>첫 번째 글을 남겨보세요! 🧵</div>',
            unsafe_allow_html=True,
        )
        return

    for post in posts:
        _render_card(post)


def _render_compose() -> None:
    remaining = max(0, int(30 - (time.time() - st.session_state.get("comm_last", 0))))

    nick_val = st.session_state.get("comm_nick", "")
    color = _avatar_color(nick_val or "나")
    letter = _initial(nick_val or "나")

    st.markdown(
        f'<div style="display:flex;gap:12px;align-items:flex-start;'
        f'background:#1c1c1e;border:1px solid #3a3a3c;border-radius:16px;'
        f'padding:16px 18px;margin-bottom:16px;">'
        f'<div style="width:42px;height:42px;border-radius:50%;background:{color};'
        f'display:flex;align-items:center;justify-content:center;'
        f'font-weight:800;font-size:17px;color:#fff;flex-shrink:0;'
        f'margin-top:4px;">{letter}</div>'
        f'<div style="flex:1;min-width:0;">'
        f'<div style="color:#636366;font-size:0.82rem;margin-bottom:8px;">'
        f'{"⏳ " + str(remaining) + "초 후 작성 가능" if remaining else "스레드 시작하기..."}'
        f'</div></div></div>',
        unsafe_allow_html=True,
    )

    if remaining:
        return

    with st.expander("✏️ 글쓰기", expanded=False):
        c1, c2 = st.columns([2, 1])
        with c1:
            nick = st.text_input("닉네임", placeholder="익명", max_chars=20,
                                 key="comm_nick", label_visibility="visible")
        with c2:
            cat = st.selectbox("카테고리", _WRITE_CATS, key="comm_wcat")

        title = st.text_input("제목 *", max_chars=80, key="comm_title")
        content = st.text_area("내용 *", max_chars=1500, height=100,
                               placeholder="팁, 질문, 성공 경험 등 자유롭게 공유해주세요.",
                               key="comm_content")

        mc1, mc2 = st.columns(2)
        with mc1:
            img_file = st.file_uploader("🖼️ 이미지 첨부",
                                        type=["jpg", "jpeg", "png", "gif", "webp"],
                                        key="comm_img")
        with mc2:
            vid_file = st.file_uploader("🎬 영상 첨부",
                                        type=["mp4", "mov", "webm"],
                                        key="comm_vid")

        if img_file:
            st.image(img_file, width=260)
        if vid_file:
            st.video(vid_file)

        if st.button("게시하기 🧵", type="primary", key="comm_submit"):
            if not title.strip() or not content.strip():
                st.error("제목과 내용을 입력해주세요.")
                return

            media_url, media_type = "", ""

            if img_file:
                if len(img_file.getvalue()) > _MAX_IMG_MB * 1024 * 1024:
                    st.error(f"이미지는 {_MAX_IMG_MB}MB 이하만 가능합니다.")
                    return
                ext = img_file.name.rsplit(".", 1)[-1]
                with st.spinner("이미지 업로드 중..."):
                    media_url = _upload_file(img_file.getvalue(),
                                             f"{uuid.uuid4().hex}.{ext}",
                                             img_file.type) or ""
                media_type = "image"

            elif vid_file:
                if len(vid_file.getvalue()) > _MAX_VID_MB * 1024 * 1024:
                    st.error(f"영상은 {_MAX_VID_MB}MB 이하만 가능합니다.")
                    return
                ext = vid_file.name.rsplit(".", 1)[-1]
                with st.spinner("영상 업로드 중..."):
                    media_url = _upload_file(vid_file.getvalue(),
                                             f"{uuid.uuid4().hex}.{ext}",
                                             vid_file.type) or ""
                media_type = "video"

            if _create_post(nick, cat, title, content, media_url, media_type):
                st.session_state.comm_last = time.time()
                for k in ["comm_nick", "comm_title", "comm_content",
                           "comm_img", "comm_vid"]:
                    st.session_state.pop(k, None)
                st.success("게시되었습니다! 🎉")
                st.rerun()
            else:
                st.error("게시 실패. 다시 시도해주세요.")


def _render_card(post: dict) -> None:
    post_id = post.get("id", 0)
    liked_key = f"comm_liked_{post_id}"
    already_liked = st.session_state.get(liked_key, False)

    nick_raw = post.get("nickname", "익명") or "익명"
    cat      = html.escape(post.get("category", ""))
    nick     = html.escape(nick_raw)
    title    = html.escape(post.get("title", ""))
    body     = html.escape(post.get("content", "")).replace("\n", "<br>")
    likes    = post.get("likes", 0)
    media_url  = post.get("media_url") or ""
    media_type = post.get("media_type") or ""
    t_label  = _rel_time(post.get("created_at", ""))
    color    = _avatar_color(nick_raw)
    letter   = _initial(nick_raw)

    col_av, col_body = st.columns([1, 11])

    with col_av:
        st.markdown(
            f'<div style="width:42px;height:42px;border-radius:50%;'
            f'background:{color};display:flex;align-items:center;'
            f'justify-content:center;font-weight:800;font-size:17px;'
            f'color:#fff;margin-top:6px;">{letter}</div>',
            unsafe_allow_html=True,
        )

    with col_body:
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">'
            f'<span style="font-weight:700;font-size:0.88rem;color:#e8e8ed;">{nick}</span>'
            f'<span style="color:#48484a;font-size:0.72rem;">·</span>'
            f'<span style="color:#636366;font-size:0.72rem;">{t_label}</span>'
            f'<span style="margin-left:auto;background:#2c2c2e;color:#a78bfa;'
            f'font-size:0.62rem;font-weight:700;padding:1px 8px;'
            f'border-radius:20px;">{cat}</span>'
            f'</div>'
            f'<div style="font-weight:700;font-size:0.9rem;color:#e8e8ed;'
            f'margin-bottom:4px;">{title}</div>'
            f'<div style="color:#aeaeb2;font-size:0.8rem;line-height:1.65;">{body}</div>',
            unsafe_allow_html=True,
        )

        if media_url:
            if media_type == "image":
                st.image(media_url, use_container_width=True)
            elif media_type == "video":
                st.video(media_url)

        heart = "❤️" if already_liked else "🤍"
        if st.button(f"{heart}  {likes}", key=f"comm_like_{post_id}"):
            if not already_liked:
                if _increment_likes(post_id, likes):
                    st.session_state[liked_key] = True
                    st.rerun()

    st.markdown(
        '<hr style="border:none;border-top:1px solid #2c2c2e;margin:10px 0 14px;">',
        unsafe_allow_html=True,
    )
