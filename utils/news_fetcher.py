"""
뉴스 수집 모듈
Google Trends RSS 피드에서 한국 트렌드 및 뉴스를 수집합니다.
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime

GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo=KR"
NAMESPACES = {'ht': 'https://trends.google.com/trending/rss'}


def fetch_trending_news() -> list:
    """Google Trends에서 오늘의 한국 트렌드 키워드와 관련 뉴스를 가져옵니다."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(GOOGLE_TRENDS_RSS_URL, headers=headers, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        news_list = []
        for item in root.findall('.//item'):
            trend_title = _get_text(item, 'title')
            pub_date = _get_text(item, 'pubDate')
            traffic = _get_text(item, 'ht:approx_traffic', NAMESPACES)
            news_items = item.findall('ht:news_item', NAMESPACES)
            if news_items:
                for ni in news_items:
                    news_list.append({
                        'title': _get_text(ni, 'ht:news_item_title', NAMESPACES) or trend_title,
                        'trend_keyword': trend_title,
                        'summary': _get_text(ni, 'ht:news_item_snippet', NAMESPACES) or f"'{trend_title}' 관련 트렌드 뉴스",
                        'source': _get_text(ni, 'ht:news_item_source', NAMESPACES) or '구글 트렌드',
                        'url': _get_text(ni, 'ht:news_item_url', NAMESPACES) or '',
                        'time': _format_date(pub_date),
                        'traffic': traffic or '',
                        'relevance_score': 0,
                        'relevance_reason': '',
                    })
            else:
                news_list.append({
                    'title': trend_title, 'trend_keyword': trend_title,
                    'summary': f"'{trend_title}' 검색이 급상승 중입니다.",
                    'source': '구글 트렌드', 'url': '', 'time': _format_date(pub_date),
                    'traffic': traffic or '', 'relevance_score': 0, 'relevance_reason': '',
                })
        return news_list
    except requests.exceptions.Timeout:
        raise ConnectionError("뉴스 수집 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.")
    except requests.exceptions.ConnectionError:
        raise ConnectionError("네트워크 연결을 확인해주세요.")
    except Exception as e:
        raise RuntimeError(f"뉴스를 가져오는 중 오류가 발생했습니다: {str(e)}")


def _get_text(element, tag, namespaces=None):
    child = element.find(tag, namespaces) if namespaces else element.find(tag)
    return child.text.strip() if child is not None and child.text else ''


def _format_date(date_str: str) -> str:
    if not date_str:
        return '오늘'
    try:
        dt = datetime.strptime(date_str[:16].strip(), '%a, %d %b %Y')
        delta = (datetime.now() - dt).days
        if delta == 0: return '오늘'
        elif delta == 1: return '어제'
        else: return f'{delta}일 전'
    except Exception:
        return date_str[:10] if len(date_str) > 10 else date_str
