"""
YouTube Data API 클라이언트
영상 데이터, 채널 정보, 썸네일을 가져옵니다.
"""

import os
import re
from googleapiclient.discovery import build


def get_youtube_client():
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY가 설정되지 않았습니다.")
    return build('youtube', 'v3', developerKey=api_key)


def extract_video_id(url: str) -> str:
    """유튜브 URL에서 영상 ID를 추출합니다."""
    patterns = [
        r'(?:v=|\/v\/|youtu\.be\/|\/embed\/)([a-zA-Z0-9_-]{11})',
        r'(?:shorts\/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("올바른 유튜브 링크를 입력해주세요.")


def parse_duration(duration_str: str) -> str:
    """ISO 8601 기간을 사람이 읽을 수 있는 형식으로 변환합니다."""
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return duration_str
    h, m, s = match.groups()
    parts = []
    if h: parts.append(f"{h}시간")
    if m: parts.append(f"{m}분")
    if s: parts.append(f"{s}초")
    return ' '.join(parts) if parts else '0초'


def get_video_data(url: str) -> dict:
    """유튜브 영상의 기본 데이터를 가져옵니다."""
    youtube = get_youtube_client()
    video_id = extract_video_id(url)

    # 영상 데이터
    video_resp = youtube.videos().list(
        part="snippet,statistics,contentDetails", id=video_id
    ).execute()

    if not video_resp.get('items'):
        raise ValueError("영상을 찾을 수 없습니다. 링크를 확인해주세요.")

    item = video_resp['items'][0]
    snippet = item['snippet']
    stats = item['statistics']
    content = item['contentDetails']

    channel_id = snippet['channelId']

    # 채널 구독자 수
    channel_resp = youtube.channels().list(
        part="statistics", id=channel_id
    ).execute()

    subscribers = '비공개'
    if channel_resp.get('items'):
        sub_count = channel_resp['items'][0]['statistics'].get('subscriberCount')
        if sub_count:
            subscribers = format_number(int(sub_count))

    views = int(stats.get('viewCount', 0))
    likes = int(stats.get('likeCount', 0))
    comments = int(stats.get('commentCount', 0))

    like_ratio = round((likes / views * 100), 3) if views > 0 else 0
    comment_ratio = round((comments / views * 100), 3) if views > 0 else 0

    # 썸네일 URL (최고 해상도 우선)
    thumbs = snippet.get('thumbnails', {})
    thumb_url = ''
    for quality in ['maxres', 'high', 'medium', 'default']:
        if quality in thumbs:
            thumb_url = thumbs[quality]['url']
            break

    return {
        'video_id': video_id,
        'title': snippet.get('title', ''),
        'channel': snippet.get('channelTitle', ''),
        'channel_id': channel_id,
        'subscribers': subscribers,
        'views': views,
        'views_formatted': format_number(views),
        'likes': likes,
        'likes_formatted': format_number(likes),
        'comments': comments,
        'comments_formatted': format_number(comments),
        'upload_date': snippet.get('publishedAt', '')[:10],
        'duration': parse_duration(content.get('duration', '')),
        'thumbnail_url': thumb_url,
        'description': snippet.get('description', '')[:500],
        'like_ratio': like_ratio,
        'comment_ratio': comment_ratio,
        'like_eval': evaluate_ratio(like_ratio, 'like'),
        'comment_eval': evaluate_ratio(comment_ratio, 'comment'),
    }


def search_videos_by_keyword(
    keyword: str,
    max_results: int = 25,
    published_after: str = None,
    video_duration: str = None,
) -> list:
    """키워드로 유튜브 영상을 검색하고 조회수 순으로 정렬합니다."""
    youtube = get_youtube_client()

    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "maxResults": min(max_results, 50),
    }
    if published_after:
        params["publishedAfter"] = published_after
    if video_duration:
        params["videoDuration"] = video_duration

    search_resp = youtube.search().list(**params).execute()
    items = search_resp.get("items", [])
    if not items:
        return []

    video_ids = [item["id"]["videoId"] for item in items]

    stats_resp = youtube.videos().list(
        part="statistics,contentDetails",
        id=",".join(video_ids),
    ).execute()

    stats_map = {}
    for item in stats_resp.get("items", []):
        stats_map[item["id"]] = {
            "views": int(item["statistics"].get("viewCount", 0)),
            "likes": int(item["statistics"].get("likeCount", 0)),
            "comments": int(item["statistics"].get("commentCount", 0)),
            "duration": parse_duration(item["contentDetails"].get("duration", "")),
        }

    results = []
    for item in items:
        vid_id = item["id"]["videoId"]
        snippet = item["snippet"]
        stats = stats_map.get(vid_id, {"views": 0, "likes": 0, "comments": 0, "duration": ""})

        thumbs = snippet.get("thumbnails", {})
        thumb_url = ""
        for quality in ["high", "medium", "default"]:
            if quality in thumbs:
                thumb_url = thumbs[quality]["url"]
                break

        results.append({
            "video_id": vid_id,
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", "")[:10],
            "thumbnail_url": thumb_url,
            "views": stats["views"],
            "views_formatted": format_number(stats["views"]),
            "likes": stats["likes"],
            "likes_formatted": format_number(stats["likes"]),
            "comments": stats["comments"],
            "comments_formatted": format_number(stats["comments"]),
            "duration": stats["duration"],
        })

    results.sort(key=lambda x: x["views"], reverse=True)
    return results


def format_number(n: int) -> str:
    """숫자를 한국식으로 포맷합니다."""
    if n >= 100000000:
        return f"{n / 100000000:.1f}억"
    elif n >= 10000:
        return f"{n / 10000:.1f}만"
    elif n >= 1000:
        return f"{n / 1000:.1f}천"
    return str(n)


def evaluate_ratio(ratio: float, ratio_type: str) -> dict:
    """비율이 평균 대비 높은지 낮은지 평가합니다."""
    if ratio_type == 'like':
        if ratio >= 5.0:
            return {'level': '매우 높음', 'badge': 'good'}
        elif ratio >= 3.0:
            return {'level': '높음', 'badge': 'good'}
        elif ratio >= 1.5:
            return {'level': '보통', 'badge': 'avg'}
        else:
            return {'level': '낮음', 'badge': 'low'}
    else:
        if ratio >= 0.5:
            return {'level': '매우 높음', 'badge': 'good'}
        elif ratio >= 0.2:
            return {'level': '높음', 'badge': 'good'}
        elif ratio >= 0.05:
            return {'level': '보통', 'badge': 'avg'}
        else:
            return {'level': '낮음', 'badge': 'low'}
