"""
기능 3: 급성장 채널 트래커
최근 3개월간 가장 가파른 성장세를 보인 유튜브 채널을 분석합니다.
"""

import streamlit as st
from datetime import datetime, timedelta
import csv
import io
import json
import re
from html import escape
from utils.youtube_client import (
    get_youtube_client,
    format_number,
)
from utils.gemini_client import analyze_growth_channels


# 카테고리 매핑 (YouTube API videoCategory IDs)
CATEGORIES = {
    "전체": None,
    "엔터테인먼트": "24",
    "음악": "10",
    "게임": "20",
    "교육": "27",
    "과학기술": "28",
    "스포츠": "17",
    "뉴스/정치": "25",
    "일상/브이로그": "22",
    "영화/애니메이션": "1",
    "코미디": "23",
    "요리/먹방": "26",
}

# 지역 매핑
REGIONS = {
    "한국": "KR",
    "일본": "JP",
    "미국": "US",
    "대만": "TW",
    "중국": "CN",
    "글로벌": None,
}

DISCOVERY_PRESETS = {
    "1천 이하": {
        "sub_max": 1000,
        "view_min": 3000,
        "ratio_min": 500,
        "label": "초기 채널이 갑자기 노출된 사례",
    },
    "5천 이하": {
        "sub_max": 5000,
        "view_min": 8000,
        "ratio_min": 400,
        "label": "작은 채널의 첫 확산 신호",
    },
    "1만 이하": {
        "sub_max": 10000,
        "view_min": 10000,
        "ratio_min": 300,
        "label": "소형 채널 발굴 기본값",
    },
    "10만 이하": {
        "sub_max": 100000,
        "view_min": 30000,
        "ratio_min": 150,
        "label": "성장 궤도에 오른 채널",
    },
    "직접 설정": {
        "sub_max": 10000,
        "view_min": 10000,
        "ratio_min": 300,
        "label": "기준을 직접 조정",
    },
}

SMALL_CHANNEL_SEARCH_TERMS = {
    "엔터테인먼트": ["근황", "논란", "반응", "레전드", "실화"],
    "음악": ["커버", "라이브", "플레이리스트", "버스킹", "노래"],
    "게임": ["공략", "신작", "버그", "랭크", "하이라이트"],
    "교육": ["공부법", "꿀팁", "정리", "입문", "설명"],
    "과학기술": ["AI", "앱", "스마트폰", "리뷰", "업데이트"],
    "스포츠": ["하이라이트", "반응", "분석", "훈련", "경기"],
    "뉴스/정치": ["이슈", "속보", "논란", "분석", "정리"],
    "일상/브이로그": ["브이로그", "자취", "직장인", "일상", "루틴"],
    "영화/애니메이션": ["리뷰", "해석", "결말", "추천", "명장면"],
    "코미디": ["웃긴", "상황극", "밈", "몰카", "개그"],
    "요리/먹방": ["레시피", "먹방", "맛집", "요리", "간단"],
    "전체": ["근황", "이슈", "리뷰", "브이로그", "쇼츠", "꿀팁", "반응"],
}


def duration_to_seconds(duration_str: str) -> int:
    """ISO 8601 기간을 초 단위로 변환합니다."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0
    h, m, s = match.groups()
    total = 0
    if h: total += int(h) * 3600
    if m: total += int(m) * 60
    if s: total += int(s)
    return total


def _fetch_trending_channels(
    category_id: str | None,
    region_code: str | None,
    max_results: int = 50,
    date_range: tuple = None,
    content_types: list = None,
    query_terms: list[str] | None = None,
):
    """
    인기 급상승 동영상 또는 특정 기간의 영상에서 채널들을 추출한 후,
    각 채널의 통계를 가져와 성장 지표를 계산합니다.
    """
    youtube = get_youtube_client()
    max_results = min(max_results, 50)
    
    video_items = []
    
    # 1단계: 영상 목록 가져오기
    if query_terms:
        video_ids = _search_recent_video_ids(
            youtube=youtube,
            query_terms=query_terms,
            category_id=category_id,
            region_code=region_code,
            date_range=date_range,
            per_query=12,
            max_total=max_results,
        )
        if video_ids:
            video_items = _fetch_video_items(youtube, video_ids)
    elif date_range:
        start_date, end_date = date_range
        # search API 사용
        search_params = {
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "publishedAfter": start_date.strftime("%Y-%m-%dT00:00:00Z"),
            "publishedBefore": end_date.strftime("%Y-%m-%dT23:59:59Z"),
            "maxResults": max_results,
        }
        if region_code: search_params["regionCode"] = region_code
        if category_id and category_id != "None": search_params["videoCategoryId"] = category_id
        
        search_resp = youtube.search().list(**search_params).execute()
        video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
        
        if video_ids:
            # 상세 정보 (statistics, contentDetails) 가져오기
            video_items = _fetch_video_items(youtube, video_ids)
    else:
        # 인기 급상승(mostPopular) 동영상 가져오기
        videos_params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "maxResults": max_results,
        }
        if region_code: videos_params["regionCode"] = region_code
        if category_id and category_id != "None": videos_params["videoCategoryId"] = category_id
        
        try:
            videos_resp = youtube.videos().list(**videos_params).execute()
            video_items = videos_resp.get("items", [])
        except Exception as e:
            # 특정 지역/카테고리 조합에서 trending 데이터가 없는 경우 404 발생 가능
            if "notFound" in str(e) or "404" in str(e):
                return []
            raise e

    # 2단계: 유형별 필터링 (롱폼/숏폼/스트리밍)
    # content_types: ["Long-form", "Shorts", "Live"]
    filtered_items = []
    for item in video_items:
        snippet = item["snippet"]
        content_details = item.get("contentDetails", {})
        duration_sec = duration_to_seconds(content_details.get("duration", "PT0S"))
        is_live = snippet.get("liveBroadcastContent") in ["live", "upcoming"] or "actualStartTime" in item.get("liveStreamingDetails", {})
        
        v_type = "Long-form"
        if is_live:
            v_type = "Live"
        elif duration_sec <= 60:
            v_type = "Shorts"
            
        if content_types and v_type not in content_types:
            continue
        
        item["v_type"] = v_type # 타입 저장
        filtered_items.append(item)

    # 3단계: 채널별 영상 집계
    channel_map = {}
    for item in filtered_items:
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        ch_id = snippet["channelId"]
        ch_title = snippet["channelTitle"]

        views = _safe_int(stats.get("viewCount", 0))
        likes = _safe_int(stats.get("likeCount", 0))
        comments = _safe_int(stats.get("commentCount", 0))
        published = snippet.get("publishedAt", "")[:10]
        days_since_upload = _days_since(published)

        if ch_id not in channel_map:
            channel_map[ch_id] = {
                "channel_id": ch_id,
                "channel_name": ch_title,
                "videos": [],
                "total_views": 0,
            }

        channel_map[ch_id]["videos"].append({
            "title": snippet["title"],
            "views": views,
            "likes": likes,
            "comments": comments,
            "published": published,
            "days_since_upload": days_since_upload,
            "views_per_day": int(views / max(days_since_upload, 1)),
            "like_ratio": round((likes / views) * 100, 2) if views else 0,
            "comment_ratio": round((comments / views) * 100, 3) if views else 0,
            "video_id": item["id"],
            "v_type": item["v_type"],
        })
        channel_map[ch_id]["total_views"] += views

    if not channel_map:
        return []

    # 4단계: 채널 통계 조회
    channel_ids = list(channel_map.keys())

    # 50개씩 배치 처리
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i : i + 50]
        ch_resp = youtube.channels().list(
            part="statistics,snippet,brandingSettings",
            id=",".join(batch),
        ).execute()

        for ch_item in ch_resp.get("items", []):
            ch_id = ch_item["id"]
            ch_stats = ch_item.get("statistics", {})
            ch_snippet = ch_item.get("snippet", {})

            if ch_id in channel_map:
                subs = ch_stats.get("subscriberCount")
                total_videos = ch_stats.get("videoCount", "0")
                total_channel_views = ch_stats.get("viewCount", "0")

                channel_map[ch_id]["subscribers"] = int(subs) if subs else None
                channel_map[ch_id]["subscribers_hidden"] = ch_stats.get("hiddenSubscriberCount", False)
                channel_map[ch_id]["total_channel_videos"] = _safe_int(total_videos)
                channel_map[ch_id]["total_channel_views"] = _safe_int(total_channel_views)
                channel_map[ch_id]["channel_created"] = ch_snippet.get("publishedAt", "")[:10]
                channel_map[ch_id]["description"] = ch_snippet.get("description", "")[:200]

                # 썸네일
                thumbs = ch_snippet.get("thumbnails", {})
                for quality in ["high", "medium", "default"]:
                    if quality in thumbs:
                        channel_map[ch_id]["thumbnail"] = thumbs[quality]["url"]
                        break

    # 3단계: 성장 지표 계산
    result = []
    for ch_id, data in channel_map.items():
        recent_videos = data["videos"]
        video_count = len(recent_videos)
        total_views = data["total_views"]
        subs = data.get("subscribers")
        avg_views = total_views // video_count if video_count > 0 else 0

        # 성장 점수 계산: 조회수 대비 구독자 비율, 영상 효율 등
        if subs and subs > 0:
            view_sub_ratio = total_views / subs
        else:
            view_sub_ratio = 0

        # 영상당 평균 조회수가 구독자 수보다 높으면 급성장 시그널
        growth_score = 0
        if subs and subs > 0:
            growth_score = (avg_views / subs) * 100  # 구독자 대비 영상당 조회수 비율
        else:
            growth_score = avg_views / 1000  # 구독자 비공개 시 조회수 기반

        # 최근 업로드 날짜들 정렬
        dates = sorted([v["published"] for v in recent_videos])
        latest_upload = dates[-1] if dates else ""
        earliest_upload = dates[0] if dates else ""

        # 상위 영상
        top_video = max(recent_videos, key=lambda x: x["views"]) if recent_videos else None
        top_video_views = top_video["views"] if top_video else 0
        top_video_sub_ratio = (top_video_views / subs * 100) if subs and subs > 0 else 0
        views_per_day = sum(v.get("views_per_day", 0) for v in recent_videos)
        avg_views_per_day = views_per_day // video_count if video_count else 0
        algorithm_score = _algorithm_signal_score(
            avg_view_sub_ratio=growth_score,
            top_video_sub_ratio=top_video_sub_ratio,
            avg_views_per_day=avg_views_per_day,
            comment_ratio=sum(v.get("comment_ratio", 0) for v in recent_videos) / video_count if video_count else 0,
        )
        discovery_score = _small_channel_discovery_score(
            subscribers=subs,
            top_video_views=top_video_views,
            avg_views=avg_views,
            avg_views_per_day=avg_views_per_day,
        )

        result.append({
            "channel_id": ch_id,
            "channel_name": data["channel_name"],
            "subscribers": subs,
            "subscribers_formatted": format_number(subs) if subs else "비공개",
            "total_views": total_views,
            "total_views_formatted": format_number(total_views),
            "avg_views": avg_views,
            "avg_views_formatted": format_number(avg_views),
            "video_count": video_count,
            "total_channel_videos": data.get("total_channel_videos", 0),
            "growth_score": round(growth_score, 1),
            "view_sub_ratio": round(view_sub_ratio, 1),
            "top_video_sub_ratio": round(top_video_sub_ratio, 1),
            "avg_views_per_day": avg_views_per_day,
            "avg_views_per_day_formatted": format_number(avg_views_per_day),
            "algorithm_score": algorithm_score,
            "discovery_score": discovery_score,
            "algorithm_signals": _algorithm_signal_labels(growth_score, top_video_sub_ratio, avg_views_per_day),
            "latest_upload": latest_upload,
            "earliest_upload": earliest_upload,
            "top_video": top_video,
            "thumbnail": data.get("thumbnail", ""),
            "description": data.get("description", ""),
            "channel_created": data.get("channel_created", ""),
            "videos": recent_videos,
        })

    # 성장 점수 기준 정렬
    result.sort(key=lambda x: x["growth_score"], reverse=True)
    return result


def _search_recent_video_ids(
    youtube,
    query_terms: list[str],
    category_id: str | None,
    region_code: str | None,
    date_range: tuple | None,
    per_query: int = 12,
    max_total: int = 50,
) -> list[str]:
    if date_range:
        start_date, end_date = date_range
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=14)

    seen = set()
    video_ids = []
    for term in query_terms:
        search_params = {
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "q": term,
            "publishedAfter": start_date.strftime("%Y-%m-%dT00:00:00Z"),
            "publishedBefore": end_date.strftime("%Y-%m-%dT23:59:59Z"),
            "maxResults": min(per_query, 50),
        }
        if region_code:
            search_params["regionCode"] = region_code
        if category_id and category_id != "None":
            search_params["videoCategoryId"] = category_id

        search_resp = youtube.search().list(**search_params).execute()
        for item in search_resp.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if video_id and video_id not in seen:
                seen.add(video_id)
                video_ids.append(video_id)
            if len(video_ids) >= max_total:
                return video_ids
    return video_ids


def _fetch_video_items(youtube, video_ids: list[str]) -> list[dict]:
    items = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        v_resp = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch)
        ).execute()
        items.extend(v_resp.get("items", []))
    return items


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _days_since(date_text: str) -> int:
    try:
        uploaded = datetime.strptime(date_text, "%Y-%m-%d")
        return max((datetime.now() - uploaded).days, 1)
    except Exception:
        return 1


def _algorithm_signal_score(avg_view_sub_ratio: float, top_video_sub_ratio: float, avg_views_per_day: int, comment_ratio: float) -> int:
    ratio_score = min(avg_view_sub_ratio, 300) * 0.35
    top_score = min(top_video_sub_ratio, 500) * 0.35
    velocity_score = min(avg_views_per_day / 10000, 100) * 0.2
    engagement_score = min(comment_ratio * 20, 100) * 0.1
    return round(ratio_score + top_score + velocity_score + engagement_score)


def _algorithm_signal_labels(avg_view_sub_ratio: float, top_video_sub_ratio: float, avg_views_per_day: int) -> list[str]:
    labels = []
    if avg_view_sub_ratio >= 100:
        labels.append("평균 조회수가 구독자 수 초과")
    if top_video_sub_ratio >= 200:
        labels.append("대표 영상이 구독자 대비 2배 이상 확산")
    if avg_views_per_day >= 50000:
        labels.append("일 조회수 속도 강함")
    if not labels:
        labels.append("안정적 확산")
    return labels


def _small_channel_discovery_score(subscribers: int | None, top_video_views: int, avg_views: int, avg_views_per_day: int) -> int:
    if subscribers is None or subscribers <= 0:
        return 0
    size_bonus = 120 if subscribers <= 1000 else 90 if subscribers <= 10000 else 50 if subscribers <= 100000 else 0
    top_ratio = min((top_video_views / subscribers) * 100, 5000) * 0.05
    avg_ratio = min((avg_views / subscribers) * 100, 2000) * 0.04
    velocity = min(avg_views_per_day / 1000, 80)
    return round(size_bonus + top_ratio + avg_ratio + velocity)


def _parse_int(value, default: int = 0) -> int:
    try:
        return int(re.sub(r'[^0-9]', '', str(value))) if str(value).strip() else default
    except Exception:
        return default


def _render_discovery_intro(selected_preset: str, preset_config: dict):
    st.markdown(
        f"""
        <div class="discovery-hero">
            <div>
                <div class="discovery-eyebrow">SMALL CHANNEL RADAR</div>
                <div class="discovery-title">구독자보다 먼저 터진 영상을 찾습니다</div>
                <div class="discovery-subtitle">{preset_config["label"]}</div>
            </div>
            <div class="discovery-pill">{selected_preset}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(3)
    with metric_cols[0]:
        st.markdown(_metric_tile("최대 구독자", format_number(preset_config["sub_max"])), unsafe_allow_html=True)
    with metric_cols[1]:
        st.markdown(_metric_tile("대표 영상 최소 조회수", format_number(preset_config["view_min"])), unsafe_allow_html=True)
    with metric_cols[2]:
        st.markdown(_metric_tile("구독자 대비 조회율", f'{preset_config["ratio_min"]}%+'), unsafe_allow_html=True)

    if preset_config["sub_max"] <= 10000:
        st.caption("1만 이하 프리셋은 인기 급상승 목록이 아니라 카테고리별 최근 검색 후보를 먼저 모은 뒤 구독자/조회율로 거릅니다.")


def _metric_tile(label: str, value: str) -> str:
    return f"""
    <div class="discovery-metric">
        <div class="discovery-metric-label">{label}</div>
        <div class="discovery-metric-value">{value}</div>
    </div>
    """


def _query_terms_for_category(category_name: str) -> list[str]:
    terms = SMALL_CHANNEL_SEARCH_TERMS.get(category_name) or SMALL_CHANNEL_SEARCH_TERMS["전체"]
    broad_terms = ["쇼츠", "이슈", "근황"]
    merged = []
    for term in [*terms, *broad_terms]:
        if term not in merged:
            merged.append(term)
    return merged[:8]


def _growth_reason(ch: dict) -> str:
    top_video = ch.get("top_video") or {}
    parts = []
    if ch.get("subscribers"):
        parts.append(f"구독자 대비 대표 영상 조회율 {ch.get('top_video_sub_ratio', 0)}%")
    if top_video.get("views_per_day", 0) >= 10000:
        parts.append(f"일 조회수 {format_number(top_video.get('views_per_day', 0))}")
    if top_video.get("comment_ratio", 0) >= 0.2:
        parts.append("댓글 반응 높음")
    if top_video.get("v_type") == "Shorts":
        parts.append("쇼츠 확산")
    title = top_video.get("title", "")
    if _has_curiosity_title(title):
        parts.append("궁금증형 제목")
    if not parts:
        parts.append("작은 모수 대비 조회 효율이 높음")
    return " · ".join(parts)


def _video_work_formula(ch: dict) -> dict:
    top_video = ch.get("top_video") or {}
    title = top_video.get("title", "급성장 영상")
    is_shorts = top_video.get("v_type") == "Shorts"
    return {
        "hook": _hook_formula(title),
        "structure": "문제 제기 -> 사례/증거 -> 반전 또는 결과 -> 짧은 결론" if is_shorts else "강한 제목 약속 -> 맥락 압축 -> 핵심 장면 반복 보상 -> 결론",
        "edit_note": "첫 2초에 결과 화면을 먼저 보여주고, 자막은 한 줄 12자 안팎으로 끊기",
        "premiere_note": "마커 기준으로 후킹/맥락/증거/반전/CTA 구간을 나눠 컷 편집",
    }


def _hook_formula(title: str) -> str:
    if _has_curiosity_title(title):
        return "제목의 빈칸을 첫 문장에 다시 던지고, 답은 8초 뒤로 미루기"
    if re.search(r"\d", title):
        return "숫자를 첫 자막에 크게 보여주고, 왜 이 수치가 비정상인지 바로 설명"
    return "결과를 먼저 보여준 뒤 '이게 왜 떴는지'를 한 문장으로 열기"


def _has_curiosity_title(title: str) -> bool:
    patterns = ["왜", "이유", "근황", "결과", "정체", "충격", "실화", "처음", "갑자기", "?"]
    return any(pattern in title for pattern in patterns)


def _build_production_package(channels: list[dict]) -> list[dict]:
    package = []
    for rank, ch in enumerate(channels, 1):
        top_video = ch.get("top_video") or {}
        formula = _video_work_formula(ch)
        video_url = f"https://www.youtube.com/watch?v={top_video.get('video_id', '')}" if top_video.get("video_id") else ""
        package.append({
            "rank": rank,
            "channel": ch.get("channel_name", ""),
            "subscribers": ch.get("subscribers", 0),
            "top_video_title": top_video.get("title", ""),
            "video_url": video_url,
            "views": top_video.get("views", 0),
            "views_per_day": top_video.get("views_per_day", 0),
            "subscriber_view_ratio": ch.get("top_video_sub_ratio", 0),
            "why_it_worked": _growth_reason(ch),
            "hook_formula": formula["hook"],
            "shorts_structure": formula["structure"],
            "edit_note": formula["edit_note"],
            "premiere_markers": _premiere_markers(formula),
        })
    return package


def _premiere_markers(formula: dict) -> list[dict]:
    return [
        {"time": "00:00:00", "name": "HOOK", "note": formula["hook"]},
        {"time": "00:00:03", "name": "CONTEXT", "note": "맥락을 한 문장으로 압축"},
        {"time": "00:00:08", "name": "PROOF", "note": "조회수/댓글/화면 증거 제시"},
        {"time": "00:00:18", "name": "PAYOFF", "note": "왜 터졌는지 결론"},
        {"time": "00:00:27", "name": "CTA", "note": "다음 이슈 예고 또는 짧은 질문"},
    ]


def _production_package_json(channels: list[dict]) -> str:
    return json.dumps(_build_production_package(channels), ensure_ascii=False, indent=2)


def _production_package_csv(channels: list[dict]) -> str:
    output = io.StringIO()
    fieldnames = [
        "rank",
        "channel",
        "top_video_title",
        "video_url",
        "subscribers",
        "views",
        "subscriber_view_ratio",
        "why_it_worked",
        "hook_formula",
        "shorts_structure",
        "edit_note",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for item in _build_production_package(channels):
        writer.writerow({key: item.get(key, "") for key in fieldnames})
    return output.getvalue()


def _premiere_jsx(channels: list[dict]) -> str:
    package = _build_production_package(channels)
    marker_blocks = []
    block_gap = 35

    for item in package:
        base_time = (item["rank"] - 1) * block_gap
        marker_blocks.append(
            {
                "time": base_time,
                "name": f'{item["rank"]:02d} VIDEO',
                "comment": (
                    f'채널: {item["channel"]}\n'
                    f'영상: {item["top_video_title"]}\n'
                    f'URL: {item["video_url"]}\n'
                    f'왜 터졌나: {item["why_it_worked"]}\n'
                    f'후킹 공식: {item["hook_formula"]}\n'
                    f'구성: {item["shorts_structure"]}\n'
                    f'편집 메모: {item["edit_note"]}'
                ),
            }
        )
        for marker in item["premiere_markers"]:
            marker_blocks.append(
                {
                    "time": base_time + _timecode_to_seconds(marker["time"]),
                    "name": f'{item["rank"]:02d} {marker["name"]}',
                    "comment": marker["note"],
                }
            )

    marker_json = json.dumps(marker_blocks, ensure_ascii=False, indent=2)
    package_json = json.dumps(package, ensure_ascii=False, indent=2)
    return f"""/*
Small Channel Shorts Automation
Generated by YouTube Creator Tool.

How to use:
1. Open Premiere Pro and select or create a sequence.
2. File > Scripts > Run Script File...
3. Choose this JSX file.
4. Sequence markers will be added as an editing blueprint.
*/

var MARKERS = {marker_json};
var PACKAGE = {package_json};

function addMarker(sequence, seconds, name, comment) {{
    var marker = sequence.markers.createMarker(seconds);
    marker.name = name;
    marker.comments = comment;
    marker.end = seconds + 1;
    return marker;
}}

function main() {{
    if (!app.project) {{
        alert("Premiere project is not open.");
        return;
    }}

    var sequence = app.project.activeSequence;
    if (!sequence) {{
        alert("활성 시퀀스가 없습니다. 시퀀스를 하나 열고 다시 실행하세요.");
        return;
    }}

    for (var i = 0; i < MARKERS.length; i++) {{
        addMarker(sequence, MARKERS[i].time, MARKERS[i].name, MARKERS[i].comment);
    }}

    alert("쇼츠 작업 마커 " + MARKERS.length + "개를 활성 시퀀스에 추가했습니다.");
}}

main();
"""


def _reference_package_jsx(package: dict, video_url: str) -> str:
    markers = package.get("premiere_markers") or []
    visual_plan = package.get("visual_plan") or []
    marker_blocks = []

    for marker in markers:
        marker_blocks.append({
            "time": _timecode_to_seconds(marker.get("time", "00:00:00")),
            "name": marker.get("name", "MARKER"),
            "comment": marker.get("note", ""),
        })

    for item in visual_plan:
        marker_blocks.append({
            "time": _timecode_to_seconds(item.get("time", "00:00:00")),
            "name": "SUBTITLE",
            "comment": f'{item.get("subtitle", "")}\n장면: {item.get("scene", "")}\n생성 프롬프트: {item.get("asset_prompt", "")}',
        })

    marker_json = json.dumps(marker_blocks, ensure_ascii=False, indent=2)
    package_json = json.dumps(package, ensure_ascii=False, indent=2)
    source_note = package.get("source_note", "")
    return f"""/*
Reference Shorts Rebuild Blueprint
Generated by YouTube Creator Tool.

Reference URL:
{video_url}

Source note:
{source_note}

This script creates sequence markers only. Use licensed/self-created/generated assets for the final edit.
*/

var MARKERS = {marker_json};
var PACKAGE = {package_json};

function addMarker(sequence, seconds, name, comment) {{
    var marker = sequence.markers.createMarker(seconds);
    marker.name = name;
    marker.comments = comment;
    marker.end = seconds + 1;
    return marker;
}}

function main() {{
    if (!app.project) {{
        alert("Premiere project is not open.");
        return;
    }}

    var sequence = app.project.activeSequence;
    if (!sequence) {{
        alert("활성 시퀀스가 없습니다. 시퀀스를 하나 열고 다시 실행하세요.");
        return;
    }}

    for (var i = 0; i < MARKERS.length; i++) {{
        addMarker(sequence, MARKERS[i].time, MARKERS[i].name, MARKERS[i].comment);
    }}

    alert("레퍼런스 재구성 마커 " + MARKERS.length + "개를 추가했습니다.");
}}

main();
"""


def _timecode_to_seconds(timecode: str) -> int:
    parts = [int(part) for part in timecode.split(":")]
    if len(parts) != 3:
        return 0
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def _render_channel_card(ch: dict, rank: int):
    """채널 카드 HTML을 렌더링합니다. (Enhanced Style)"""
    # 성장 등급
    score = ch["growth_score"]
    if score >= 200:
        grade = "🔥 폭발적"
        grade_class = "growth-explosive"
    elif score >= 100:
        grade = "🚀 급성장"
        grade_class = "growth-rapid"
    elif score >= 50:
        grade = "📈 성장"
        grade_class = "growth-steady"
    else:
        grade = "📊 안정"
        grade_class = "growth-stable"

    channel_url = f"https://www.youtube.com/channel/{ch['channel_id']}"
    reason = escape(_growth_reason(ch))
    formula = _video_work_formula(ch)
    
    # 상위 영상 정보
    top_video = ch.get("top_video")
    top_video_html = ""
    if top_video:
        video_url = f"https://www.youtube.com/watch?v={top_video['video_id']}"
        from utils.youtube_client import format_number
        views_fmt = format_number(top_video['views'])
        top_video_html = f"""<div class="growth-details">
<div style="font-size: 0.7rem; color: #8e8e93; font-weight: 600; margin-bottom: 4px;">분석 대상 영상</div>
<a href="{video_url}" target="_blank" class="growth-top-video">
<span class="growth-video-icon">🎬</span>
<div style="overflow: hidden;">
<div class="growth-video-title">{escape(top_video['title'])}</div>
<div class="growth-video-stats">조회수 {views_fmt}회 • {top_video['v_type']}</div>
</div>
</a>
</div>"""

    card_html = f"""<div class="growth-card">
<div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
<div class="growth-card-header">
<div class="growth-rank">#{rank}</div>
{'<a href="' + channel_url + '" target="_blank"><img src="' + ch["thumbnail"] + '" class="growth-avatar" /></a>' if ch.get("thumbnail") else ''}
<div>
<div class="growth-channel-name">
<a href="{channel_url}" target="_blank" style="color: #ffffff; text-decoration: none;">{ch["channel_name"]}</a>
</div>
<div class="growth-channel-meta">구독자 {ch["subscribers_formatted"]}</div>
</div>
</div>
<div class="growth-badge {grade_class}">{grade}</div>
</div>
</div>
<div class="growth-stats-grid">
<div class="growth-stat">
<div class="growth-stat-value">{ch["total_views_formatted"]}</div>
<div class="growth-stat-label">분석 기간 총 조회수</div>
</div>
<div class="growth-stat">
<div class="growth-stat-value">{ch["avg_views_formatted"]}</div>
<div class="growth-stat-label">평균 조회수</div>
</div>
<div class="growth-stat">
<div class="growth-score-tag">📊 성장지수 {ch["growth_score"]}%</div>
</div>
<div class="growth-stat">
<div class="growth-score-tag">⚙️ 알고리즘 {ch.get("algorithm_score", 0)}</div>
</div>
<div class="growth-stat">
<div class="growth-score-tag">🔎 발굴 {ch.get("discovery_score", 0)}</div>
</div>
</div>
<div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:10px;">
<span style="font-size:0.72rem; color:#0a84ff; background:rgba(10,132,255,0.12); padding:4px 8px; border-radius:8px;">최고 영상/구독자 {ch.get("top_video_sub_ratio", 0)}%</span>
<span style="font-size:0.72rem; color:#30d158; background:rgba(48,209,88,0.12); padding:4px 8px; border-radius:8px;">평균 일조회 {ch.get("avg_views_per_day_formatted", "0")}</span>
</div>
<div style="font-size:0.74rem; color:#8e8e93; margin-top:8px;">{", ".join(ch.get("algorithm_signals", []))}</div>
<div class="why-card">
<div class="why-label">왜 터졌나</div>
<div class="why-text">{reason}</div>
</div>
<div class="formula-card">
<div class="formula-row"><span>후킹</span><strong>{escape(formula["hook"])}</strong></div>
<div class="formula-row"><span>구성</span><strong>{escape(formula["structure"])}</strong></div>
<div class="formula-row"><span>편집</span><strong>{escape(formula["edit_note"])}</strong></div>
</div>
{top_video_html}
</div>"""
    st.markdown(card_html, unsafe_allow_html=True)

    # 상위 영상 분석 버튼 및 결과 렌더링
    if top_video:
        btn_key = f"analyze_btn_{ch['channel_id']}"
        state_key = f"viral_analysis_{ch['channel_id']}"
        rebuild_key = f"rebuild_package_{ch['channel_id']}"
        video_url = f"https://www.youtube.com/watch?v={top_video['video_id']}"
        
        action_col1, action_col2 = st.columns(2)
        with action_col1:
            analyze_clicked = st.button("영상 분석", key=btn_key, use_container_width=True)
        with action_col2:
            rebuild_clicked = st.button("새 쇼츠 재구성", key=f"rebuild_btn_{ch['channel_id']}", use_container_width=True)

        if analyze_clicked:
            st.session_state[state_key] = "loading"
            from utils.transcript import get_transcript
            from utils.gemini_client import analyze_video_algorithm_strategy
            
            transcript = get_transcript(top_video['video_id'])
            try:
                res = analyze_video_algorithm_strategy(top_video, transcript or "")
                st.session_state[state_key] = res
            except Exception as e:
                st.session_state[state_key] = {"error": str(e)}
            st.rerun()

        if rebuild_clicked:
            st.session_state[rebuild_key] = "loading"
            from utils.transcript import get_transcript
            from utils.gemini_client import generate_reference_rebuild_package

            transcript = get_transcript(top_video['video_id'])
            try:
                reference_data = {
                    **top_video,
                    "channel": ch.get("channel_name", ""),
                    "channel_id": ch.get("channel_id", ""),
                    "subscribers": ch.get("subscribers", 0),
                    "description": ch.get("description", ""),
                }
                package = generate_reference_rebuild_package(reference_data, transcript or "")
                st.session_state[rebuild_key] = package
            except Exception as e:
                st.session_state[rebuild_key] = {"error": str(e)}
            st.rerun()

        if state_key in st.session_state:
            res = st.session_state[state_key]
            if res == "loading":
                st.info("🔄 자막 추출 및 심층 분석 중입니다...")
            elif "error" in res:
                st.error(res["error"])
            else:
                with st.expander("✨ 영상 완벽 분석 결과 보기", expanded=True):
                    if res.get("one_line_reason"):
                        st.markdown(f"#### 한 줄 요약\n{res.get('one_line_reason', '')}")

                    st.markdown("#### ⚙️ 알고리즘 반응 이유")
                    st.markdown(res.get("algorithm_reason", ""))

                    st.markdown("#### 📐 영상 구성")
                    struct = res.get("structure", {})
                    st.markdown(f"**초반:** {struct.get('opening', '')}")
                    st.markdown(f"**중반:** {struct.get('development', '')}")
                    st.markdown(f"**보상/반전:** {struct.get('payoff', '')}")
                    st.markdown(f"**마무리:** {struct.get('ending', '')}")
                    
                    st.markdown("#### 🧲 후킹 분석")
                    st.markdown(res.get("hook_analysis", ""))
                    
                    st.markdown("#### 🧠 시청 지속 장치")
                    devices = res.get("retention_devices", [])
                    if isinstance(devices, list):
                        for device in devices:
                            st.markdown(f"- {device}")
                    else:
                        st.markdown(devices)

                    recipe = res.get("editing_recipe", [])
                    if recipe:
                        st.markdown("#### 🎛️ 편집 작업 레시피")
                        if isinstance(recipe, list):
                            for item in recipe:
                                st.markdown(f"- {item}")
                        else:
                            st.markdown(recipe)
                    
                    st.markdown("#### 🏆 재현 가능한 공식")
                    st.markdown(res.get("replicable_formula", ""))

                    if res.get("cautions"):
                        st.caption(res.get("cautions"))

        if rebuild_key in st.session_state:
            package = st.session_state[rebuild_key]
            if package == "loading":
                st.info("새 쇼츠 제작 패키지를 생성하고 있습니다...")
            elif isinstance(package, dict) and "error" in package:
                st.error(package["error"])
            else:
                with st.expander("새 쇼츠 재구성 패키지", expanded=True):
                    st.markdown(f"**왜 떴나:** {package.get('reference_summary', '')}")
                    st.markdown(f"**새 관점:** {package.get('new_angle', '')}")
                    titles = package.get("title_options", [])
                    if titles:
                        st.markdown("**제목 후보:** " + " / ".join(titles))

                    script = package.get("script", {})
                    st.markdown("#### 새 대본")
                    for key, label in [
                        ("hook", "후킹"),
                        ("context", "맥락"),
                        ("proof", "근거"),
                        ("payoff", "결론"),
                        ("cta", "마무리"),
                    ]:
                        if script.get(key):
                            st.markdown(f"**{label}:** {script[key]}")

                    layout = package.get("subtitle_layout", {})
                    if layout:
                        st.markdown(
                            f"**자막 위치:** {layout.get('safe_position', '')} · "
                            f"{layout.get('reason', '')} · {layout.get('style', '')}"
                        )

                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            "재구성 JSON",
                            data=json.dumps(package, ensure_ascii=False, indent=2),
                            file_name="reference_rebuild_package.json",
                            mime="application/json",
                            use_container_width=True,
                        )
                    with dl_col2:
                        st.download_button(
                            "재구성 Premiere JSX",
                            data=_reference_package_jsx(package, video_url),
                            file_name="reference_rebuild_markers.jsx",
                            mime="text/plain",
                            use_container_width=True,
                        )


def render():
    """급성장 채널 트래커 탭을 렌더링합니다."""
    from utils.analytics import log_event
    log_event("page_view", "growth_tracker")

    preset = st.radio(
        "채널 규모",
        list(DISCOVERY_PRESETS.keys()),
        horizontal=True,
        index=2,
        key="growth_discovery_preset",
    )
    preset_config = DISCOVERY_PRESETS[preset]

    _render_discovery_intro(preset, preset_config)

    st.markdown('<p class="section-header">검색 조건</p>', unsafe_allow_html=True)
    col_cat, col_region, col_type = st.columns([2, 1, 2])

    with col_cat:
        selected_categories = st.multiselect(
            "카테고리",
            list(CATEGORIES.keys())[1:],
            default=["엔터테인먼트", "일상/브이로그"],
            key="growth_category_multi",
        )
        if not selected_categories:
            selected_categories = ["전체"]

    with col_region:
        selected_region = st.selectbox(
            "지역",
            list(REGIONS.keys()),
            index=0,
            key="growth_region_select",
        )

    with col_type:
        content_types = st.multiselect(
            "콘텐츠 유형",
            ["Long-form", "Shorts", "Live"],
            default=["Long-form", "Shorts"],
            help="초소형 채널 발굴은 라이브보다 일반 영상과 쇼츠를 우선 보는 편이 좋습니다.",
            key="growth_type_multi"
        )

    with st.expander("상세 기준 조정", expanded=(preset == "직접 설정")):
        col_sub_max, col_view_min, col_ratio_min, col_view_max = st.columns([1, 1, 1, 1])
        with col_sub_max:
            sub_max = st.number_input(
                "최대 구독자수",
                min_value=0,
                max_value=10000000,
                value=preset_config["sub_max"],
                step=500,
                help="0이면 구독자 수 제한을 두지 않습니다.",
                key=f"growth_sub_max_{preset}",
            )

        with col_view_min:
            view_min = st.number_input(
                "최소 대표영상 조회수",
                min_value=0,
                max_value=100000000,
                value=preset_config["view_min"],
                step=1000,
                key=f"growth_view_min_{preset}",
            )

        with col_ratio_min:
            ratio_min = st.number_input(
                "최소 구독자 대비 조회율 %",
                min_value=0,
                max_value=100000,
                value=preset_config["ratio_min"],
                step=50,
                help="구독자 300명, 조회수 3만이면 10000%입니다.",
                key=f"growth_ratio_min_{preset}",
            )

        with col_view_max:
            view_max = st.number_input(
                "최대 총 조회수",
                min_value=0,
                max_value=100000000,
                value=0,
                step=10000,
                help="0이면 조회수 상한을 두지 않습니다.",
                key=f"growth_view_max_{preset}",
            )

        col_period, col_count, col_sort, col_order = st.columns([2, 1, 1, 1])
        with col_period:
            is_realtime = st.toggle("실시간 트렌드", value=True, help="현재 인기 영상 목록에서 발굴합니다.")
            if not is_realtime:
                today = datetime.now()
                date_range = st.date_input(
                    "분석 기간",
                    value=(today - timedelta(days=30), today),
                    max_value=today,
                    help="이 기간 사이에 업로드된 영상을 분석합니다."
                )
                if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
                    final_date_range = date_range
                else:
                    final_date_range = (today - timedelta(days=30), today)
            else:
                final_date_range = None

        with col_count:
            max_results = st.selectbox(
                "결과 수",
                [25, 50],
                index=1,
                key="growth_max_results_select",
            )

        with col_sort:
            sort_by = st.selectbox(
                "정렬",
                ["소형 채널 발굴순", "성장 지수순", "알고리즘 신호순", "구독자 대비 최고영상순", "조회수순", "구독자순"],
                index=0,
                key="growth_sort_by_select"
            )

        with col_order:
            sort_order = st.selectbox(
                "방향",
                ["내림차순", "오름차순"],
                index=0,
                key="growth_sort_order_select"
            )

    with st.expander("레퍼런스 링크로 바로 새 쇼츠 만들기"):
        ref_url = st.text_input(
            "YouTube Shorts 또는 영상 링크",
            placeholder="https://www.youtube.com/shorts/...",
            key="reference_rebuild_url",
        )
        ref_clicked = st.button("링크 분석 후 재구성", use_container_width=True, key="reference_rebuild_btn")
        if ref_clicked and ref_url:
            with st.spinner("레퍼런스 링크를 분석해 새 쇼츠 패키지를 만들고 있습니다..."):
                try:
                    from utils.youtube_client import get_video_data
                    from utils.transcript import get_transcript
                    from utils.gemini_client import generate_reference_rebuild_package

                    video_data = get_video_data(ref_url)
                    transcript = get_transcript(video_data["video_id"])
                    package = generate_reference_rebuild_package(video_data, transcript or "")
                    st.session_state["reference_rebuild_package"] = {
                        "url": ref_url,
                        "video_data": video_data,
                        "package": package,
                    }
                except Exception as e:
                    st.error(str(e))

        if "reference_rebuild_package" in st.session_state:
            stored = st.session_state["reference_rebuild_package"]
            package = stored["package"]
            st.markdown(f"**왜 떴나:** {package.get('reference_summary', '')}")
            st.markdown(f"**새 관점:** {package.get('new_angle', '')}")
            script = package.get("script", {})
            if script:
                st.markdown(" / ".join([value for value in script.values() if value]))

            ref_col1, ref_col2 = st.columns(2)
            with ref_col1:
                st.download_button(
                    "재구성 JSON",
                    data=json.dumps(package, ensure_ascii=False, indent=2),
                    file_name="reference_rebuild_package.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with ref_col2:
                st.download_button(
                    "재구성 Premiere JSX",
                    data=_reference_package_jsx(package, stored["url"]),
                    file_name="reference_rebuild_markers.jsx",
                    mime="text/plain",
                    use_container_width=True,
                )

    search_clicked = st.button("🔍 급성장 채널 검색 시작", use_container_width=True, key="growth_search_main_btn")

    if search_clicked:
        region_code = REGIONS[selected_region]
        all_channels = []
        use_small_channel_search = sub_max > 0 and sub_max <= 10000
        
        # 최적화: 카테고리를 너무 많이 선택한 경우 통합 검색으로 전환 (성능/할당량 최적화)
        # 선택된 카테고리가 전체 리스트의 80% 이상이면 브로드 검색 수행
        is_broad_search = len(selected_categories) >= 8
        search_list = ["전체"] if is_broad_search else selected_categories
        
        if is_broad_search:
            st.info("💡 많은 카테고리가 선택되어 전체 통합 분석을 진행합니다.")

        with st.spinner("실시간 분석 중..."):
            error_count = 0
            last_error = ""
            
            for cat_name in search_list:
                try:
                    cat_id = CATEGORIES[cat_name]
                    # 필터가 설정되어 있으면 검색 범위를 넓혀서 필터링 후에도 결과가 남도록 함
                    fetch_count = max_results if (sub_max == 0 and view_max == 0 and view_min == 0 and ratio_min == 0) else 100
                    query_terms = _query_terms_for_category(cat_name) if use_small_channel_search else None
                    
                    cat_channels = _fetch_trending_channels(
                        category_id=cat_id,
                        region_code=region_code,
                        max_results=fetch_count,
                        date_range=final_date_range,
                        content_types=content_types,
                        query_terms=query_terms,
                    )
                    all_channels.extend(cat_channels)
                except Exception as e:
                    error_count += 1
                    last_error = str(e)
                    print(f"Error fetching category {cat_name}: {e}")
                    continue
            
            # 중복 제거 및 필터링
            unique_channels = {}
            for ch in all_channels:
                ch_id = ch["channel_id"]
                if ch_id not in unique_channels:
                    # 필터 조건 체크
                    if sub_max > 0 and (ch.get("subscribers") is None or ch.get("subscribers") > sub_max):
                        continue
                    top_video = ch.get("top_video") or {}
                    if view_min > 0 and top_video.get("views", 0) < view_min:
                        continue
                    if ratio_min > 0 and ch.get("top_video_sub_ratio", 0) < ratio_min:
                        continue
                    if view_max > 0 and ch.get("total_views", 0) > view_max:
                        continue
                    unique_channels[ch_id] = ch
            
            channels = list(unique_channels.values())

            if not channels:
                if error_count > 0:
                    st.error(f"분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. (오류: {last_error})")
                else:
                    st.warning(
                        "검색 결과가 없습니다. 1천/1만 이하 채널은 후보가 적을 수 있어요. "
                        "최소 대표영상 조회수를 낮추거나, 최소 구독자 대비 조회율을 100~200%로 낮춰보세요."
                    )
            else:
                # 정렬 키 결정
                sort_key = "discovery_score"
                if sort_by == "성장 지수순":
                    sort_key = "growth_score"
                elif sort_by == "알고리즘 신호순":
                    sort_key = "algorithm_score"
                elif sort_by == "구독자 대비 최고영상순":
                    sort_key = "top_video_sub_ratio"
                elif sort_by == "조회수순":
                    sort_key = "total_views"
                elif sort_by == "구독자순":
                    sort_key = "subscribers"
                
                # 정렬 방향 결정
                is_reverse = (sort_order == "내림차순")
                
                # 정렬 수행
                if sort_key == "subscribers":
                    channels.sort(key=lambda x: x.get("subscribers") or 0, reverse=is_reverse)
                else:
                    channels.sort(key=lambda x: x.get(sort_key, 0), reverse=is_reverse)

                # 최종 결과 제한
                channels = channels[:max_results]
                
                st.session_state["growth_channels"] = channels
                st.session_state["growth_filter"] = {
                    "categories": selected_categories,
                    "region": selected_region,
                    "date_range": final_date_range,
                    "content_types": content_types,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                    "sub_max": sub_max,
                    "view_min": view_min,
                    "ratio_min": ratio_min,
                    "view_max": view_max,
                }
                st.success(f"총 {len(channels)}개의 채널을 분석했습니다.")

    # ── 결과 표시 ──
    if "growth_channels" in st.session_state and st.session_state["growth_channels"]:
        channels = st.session_state["growth_channels"]
        filter_info = st.session_state.get("growth_filter", {})

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # 요약 헤더
        cat_label = ", ".join(filter_info.get("categories", ["전체"]))
        region_label = filter_info.get("region", "한국")
        period_label = f"{filter_info['date_range'][0]} ~ {filter_info['date_range'][1]}" if filter_info.get("date_range") else "전체"
        types_label = ", ".join(filter_info.get("content_types", []))
        
        st.markdown(
            f'<div class="growth-summary-header">'
            f'<span class="growth-summary-tag">📍 {region_label}</span>'
            f'<span class="growth-summary-tag">🏷️ {cat_label}</span>'
            f'<span class="growth-summary-tag">📅 {period_label}</span>'
            f'<span class="growth-summary-tag">🎬 {types_label}</span>'
            f'<span class="growth-summary-tag">📊 {len(channels)}개 채널</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<p class="section-header">작업 패키지</p>', unsafe_allow_html=True)
        package_targets = channels[:10]
        st.markdown(
            '<div class="production-brief">'
            '상위 10개 급성장 영상을 쇼츠 기획/프리미어 마커 초안으로 바로 쓸 수 있게 묶었습니다.'
            '</div>',
            unsafe_allow_html=True,
        )
        pkg_col1, pkg_col2, pkg_col3 = st.columns(3)
        with pkg_col1:
            st.download_button(
                "작업 패키지 JSON",
                data=_production_package_json(package_targets),
                file_name="small_channel_shorts_package.json",
                mime="application/json",
                use_container_width=True,
            )
        with pkg_col2:
            st.download_button(
                "작업 패키지 CSV",
                data=_production_package_csv(package_targets),
                file_name="small_channel_shorts_package.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with pkg_col3:
            st.download_button(
                "Premiere JSX",
                data=_premiere_jsx(package_targets),
                file_name="small_channel_shorts_markers.jsx",
                mime="text/plain",
                use_container_width=True,
            )

        # 상위 3개 하이라이트
        if len(channels) >= 3:
            st.markdown('<p class="section-header">🏆 TOP 3 급성장 채널</p>', unsafe_allow_html=True)
            top3_cols = st.columns(3)
            for i, col in enumerate(top3_cols):
                ch = channels[i]
                medal = ["🥇", "🥈", "🥉"][i]
                channel_url = f"https://www.youtube.com/channel/{ch['channel_id']}"
                with col:
                    st.markdown(
                        f'<div class="growth-top3-card">'
                        f'<div class="growth-top3-medal">{medal}</div>'
                        f'<div class="growth-top3-name"><a href="{channel_url}" target="_blank" style="color: #e8e8ed; text-decoration: none;">{ch["channel_name"]}</a></div>'
                        f'<div class="growth-top3-subs">구독자 {ch["subscribers_formatted"]}</div>'
                        f'<div class="growth-top3-views">조회수 {ch["total_views_formatted"]}</div>'
                        f'<div class="growth-top3-score">'
                        f'발굴점수 <strong>{ch.get("discovery_score", 0)}</strong> · 성장지수 <strong>{ch["growth_score"]}%</strong></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # 전체 채널 리스트
        st.markdown('<p class="section-header">전체 채널 리스트</p>', unsafe_allow_html=True)

        total_count = len(channels)
        sort_order = filter_info.get("sort_order", "내림차순")

        # 2열(Tile) 형태로 배치
        cols = st.columns(2)

        for i, ch in enumerate(channels):
            if sort_order == "내림차순":
                display_rank = i + 1
            else:
                display_rank = total_count - i
            
            with cols[i % 2]:
                _render_channel_card(ch, display_rank)

        st.markdown('<hr class="divider">', unsafe_allow_html=True)

        # AI 종합 분석
        st.markdown('<p class="section-header">AI 성장 트렌드 분석</p>', unsafe_allow_html=True)

        if st.button("🤖 AI 분석 요청", use_container_width=True, key="growth_ai_btn"):
            with st.spinner("AI가 성장 트렌드를 분석하고 있습니다..."):
                try:
                    top_channels = channels[:10]
                    analysis_data = []
                    for ch in top_channels:
                        analysis_data.append({
                            "channel_name": ch["channel_name"],
                            "subscribers": ch["subscribers_formatted"],
                            "total_views": ch["total_views_formatted"],
                            "avg_views": ch["avg_views_formatted"],
                            "video_count": ch["video_count"],
                            "growth_score": ch["growth_score"],
                            "top_video_sub_ratio": ch.get("top_video_sub_ratio", 0),
                            "avg_views_per_day": ch.get("avg_views_per_day", 0),
                            "algorithm_score": ch.get("algorithm_score", 0),
                            "discovery_score": ch.get("discovery_score", 0),
                            "algorithm_signals": ch.get("algorithm_signals", []),
                        })

                    analysis = analyze_growth_channels(
                        analysis_data,
                        cat_label,
                        region_label,
                    )
                    st.session_state["growth_analysis"] = analysis
                except Exception as e:
                    st.markdown(
                        f'<div class="error-msg">❌ AI 분석 실패: {str(e)}</div>',
                        unsafe_allow_html=True,
                    )

        if "growth_analysis" in st.session_state:
            st.markdown(
                f'<div class="analysis-card"><h3>📊 AI 성장 트렌드 인사이트</h3>'
                f'<p>{st.session_state["growth_analysis"]}</p></div>',
                unsafe_allow_html=True,
            )
