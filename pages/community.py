"""유튜버 정보 공유 커뮤니티"""
from __future__ import annotations

import html
import os
import time

import requests
import streamlit as st

_TABLE = "community_posts"
_CATEGORIES = ["전체", "팁 공유", "채널 공유", "질문", "성공 사례", "자유"]
_WRITE_CATS = _CATEGORIES[1:]


def _cfg() -> tuple[str, str]:
    return os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_ANON_KEY", "")


def _headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _fetch_posts(category: str) -> list[dict]:
    url, key = _cfg()
    if not url or not key:
        return []
    params = {
        "select": "*",
        "order": "created_at.desc",
        "limit": "100",
    }
    if category != "전체":
        params["category"] = f"eq.{category}"
    try:
        resp = requests.get(
            f"{url}/rest/v1/{_TABLE}",
            headers=_headers(key),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def _create_post(nickname: str, category: str, title: str, content: str) -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    try:
        resp = requests.post(
            f"{url}/rest/v1/{_TABLE}",
            headers={**_headers(key), "Prefer": "return=minimal"},
            json={
                "nickname": nickname.strip() or "익명",
                "category": category,
                "title": title.strip(),
                "content": content.strip(),
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False


def _increment_likes(post_id: int, current: int) -> bool:
    url, key = _cfg()
    if not url or not key:
        return False
    try:
        resp = requests.patch(
            f"{url}/rest/v1/{_TABLE}",
            headers={**_headers(key), "Prefer": "return=minimal"},
            params={"id": f"eq.{post_id}"},
            json={"likes": current + 1},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception:
        return False


def render() -> None:
    from utils.analytics import log_event
    log_event("page_view", "community")

    st.markdown('<p class="section-header">커뮤니티</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="section-caption">유튜버들끼리 팁·채널·성공 사례를 자유롭게 공유해요 🎬</p>',
        unsafe_allow_html=True,
    )

    url, key = _cfg()
    if not url or not key:
        st.warning("Supabase가 연결되지 않아 커뮤니티를 사용할 수 없습니다.")
        return

    _render_write_form()
    st.markdown('<hr class="divider">', unsafe_allow_html=True)

    cat = st.radio("", _CATEGORIES, horizontal=True, key="comm_cat",
                   label_visibility="collapsed")

    posts = _fetch_posts(cat)
    if not posts:
        st.markdown(
            '<div style="text-align:center;color:#636366;padding:3rem 0;font-size:0.9rem;">'
            "아직 게시글이 없습니다.<br>첫 번째 글을 남겨보세요! 🙌"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    for post in posts:
        _render_card(post)


def _render_write_form() -> None:
    cooldown = st.session_state.get("comm_last_post", 0)
    remaining = int(30 - (time.time() - cooldown))

    with st.expander("✏️ 글쓰기", expanded=False):
        if remaining > 0:
            st.warning(f"{remaining}초 후에 다시 작성할 수 있습니다.")
            return

        nick = st.text_input("닉네임 (선택)", placeholder="익명", max_chars=20,
                             key="comm_nick")
        cat = st.selectbox("카테고리", _WRITE_CATS, key="comm_wcat")
        title = st.text_input("제목 *", max_chars=80, key="comm_title")
        content = st.text_area("내용 *", max_chars=1500, height=130,
                               placeholder="팁, 채널 소개, 질문 등 자유롭게 공유해주세요.",
                               key="comm_content")

        if st.button("등록하기", type="primary", key="comm_submit"):
            if not title.strip() or not content.strip():
                st.error("제목과 내용을 모두 입력해주세요.")
                return
            if _create_post(nick, cat, title, content):
                st.session_state.comm_last_post = time.time()
                for k in ["comm_nick", "comm_title", "comm_content"]:
                    st.session_state.pop(k, None)
                st.success("등록되었습니다! 🎉")
                st.rerun()
            else:
                st.error("등록에 실패했습니다. 다시 시도해주세요.")


def _render_card(post: dict) -> None:
    post_id = post.get("id", 0)
    liked_key = f"comm_liked_{post_id}"
    already_liked = st.session_state.get(liked_key, False)

    cat = html.escape(post.get("category", ""))
    nick = html.escape(post.get("nickname", "익명"))
    title = html.escape(post.get("title", ""))
    content = html.escape(post.get("content", ""))
    likes = post.get("likes", 0)
    created = post.get("created_at", "")[:16].replace("T", " ")

    preview = content[:220] + ("…" if len(content) > 220 else "")

    st.markdown(
        f"""
        <div style="background:#1c1c1e;border-radius:14px;padding:16px 20px;
                    border:1px solid #3a3a3c;margin-bottom:4px;">
            <div style="display:flex;justify-content:space-between;
                        align-items:center;margin-bottom:8px;">
                <span style="background:#2c2c2e;color:#a78bfa;font-size:0.68rem;
                             font-weight:700;padding:2px 9px;border-radius:20px;
                             letter-spacing:0.03em;">{cat}</span>
                <span style="color:#636366;font-size:0.7rem;">{nick} · {created}</span>
            </div>
            <div style="font-weight:700;font-size:0.92rem;color:#e8e8ed;
                        margin-bottom:6px;">{title}</div>
            <div style="color:#aeaeb2;font-size:0.8rem;line-height:1.6;
                        white-space:pre-wrap;">{preview}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    like_label = f"{'❤️' if already_liked else '🤍'}  {likes}"
    if st.button(like_label, key=f"comm_like_{post_id}"):
        if not already_liked:
            if _increment_likes(post_id, likes):
                st.session_state[liked_key] = True
                st.rerun()

    st.markdown(
        '<div style="height:6px;"></div>',
        unsafe_allow_html=True,
    )
