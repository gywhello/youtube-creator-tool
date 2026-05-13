"""
Gemini API 클라이언트
Google Gemini 2.5 Flash를 활용한 AI 기능 모듈
"""

import os
import json
import re
from google import genai
from google.genai import types


def get_client():
    """Gemini 클라이언트를 반환합니다."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다.")
    client = genai.Client(api_key=api_key)
    return client


MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
FALLBACK_MODELS = [
    MODEL_NAME,
    "gemini-2.5-flash",
    "gemini-2.0-flash-lite",
]


def generate_content(client, contents, config=None):
    """Generate content with a current Gemini model and safe fallbacks."""
    last_error = None
    tried = []
    for model_name in dict.fromkeys(FALLBACK_MODELS):
        tried.append(model_name)
        try:
            kwargs = {
                "model": model_name,
                "contents": contents,
            }
            if config is not None:
                kwargs["config"] = config
            return client.models.generate_content(**kwargs)
        except Exception as exc:
            last_error = exc
            if "not found" not in str(exc).lower() and "not_found" not in str(exc).lower():
                raise
    raise RuntimeError(f"사용 가능한 Gemini 모델을 찾지 못했습니다. 시도한 모델: {', '.join(tried)} / {last_error}")


def _analyze_batch_chunk(client, chunk: list, offset: int) -> list:
    """chunk 내 영상들을 분석하고 결과 리스트를 반환합니다."""
    video_texts = []
    for i, v in enumerate(chunk):
        like_rate = round(v["likes"] / v["views"] * 100, 2) if v["views"] > 0 else 0
        comment_rate = round(v["comments"] / v["views"] * 100, 3) if v["views"] > 0 else 0
        video_texts.append(
            f"{offset + i + 1}. 제목: {v['title']}\n"
            f"   채널: {v['channel']} | 조회수: {v['views_formatted']} | "
            f"좋아요율: {like_rate}% | 댓글율: {comment_rate}% | "
            f"업로드: {v['published_at']} | 길이: {v['duration']}"
        )

    prompt = (
        "당신은 유튜브 알고리즘과 콘텐츠 전략 전문가입니다.\n\n"
        "아래는 특정 키워드로 검색된 조회수 상위 영상 목록입니다.\n"
        "각 영상이 왜 높은 조회수를 기록했는지 핵심 이유를 분석해주세요.\n\n"
        "영상 목록:\n"
        + "\n".join(video_texts)
        + "\n\n각 영상에 대해 다음을 분석하세요:\n"
        "1. one_line: 왜 조회수가 높은지 핵심을 한 줄로 (25자 이내)\n"
        "2. factors: 핵심 성공 요인 2~3가지 (배열, 각 20자 이내)\n"
        '3. hook_type: 후킹 유형 — 아래 중 하나만 선택\n'
        '   "트렌드 편승" | "감정 자극" | "정보성" | "충격/논란" | "유명인 효과" | "실용 정보" | "호기심 유발" | "커뮤니티 공감"\n\n'
        "반드시 아래 JSON 배열 형식으로만 답변하세요. 다른 텍스트 없이 JSON만 출력하세요:\n"
        '[{"index": 번호, "one_line": "한 줄 핵심 이유", "factors": ["요인1", "요인2"], "hook_type": "후킹 유형"}]'
    )

    response = generate_content(
        client,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.4, max_output_tokens=8192),
    )
    text = response.text.strip()
    # 마크다운 코드 블록 제거
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("```").strip()
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    return json.loads(json_match.group() if json_match else text)


def analyze_keyword_videos_batch(videos: list) -> list:
    """
    키워드 검색 결과 영상 목록을 분석하여
    각 영상이 왜 조회수가 높은지 핵심 이유를 반환합니다.
    20개씩 나눠 처리해 토큰 한도 초과를 방지합니다.
    """
    client = get_client()
    CHUNK = 20
    all_results = []

    for start in range(0, len(videos), CHUNK):
        chunk = videos[start:start + CHUNK]
        try:
            items = _analyze_batch_chunk(client, chunk, offset=start)
            all_results.extend(items)
        except Exception:
            for j in range(len(chunk)):
                all_results.append({"index": start + j + 1, "one_line": "", "factors": [], "hook_type": "-"})

    analysis_map = {item["index"]: item for item in all_results}
    return [
        analysis_map.get(i + 1, {"index": i + 1, "one_line": "", "factors": [], "hook_type": "-"})
        for i in range(len(videos))
    ]


def score_news_relevance(news_list: list, concepts: str) -> list:
    """
    뉴스 목록에 대해 채널 컨셉 관련도 점수(0~100)를 매깁니다.
    """
    client = get_client()

    news_texts = []
    for i, news in enumerate(news_list):
        news_texts.append(f"{i+1}. 제목: {news.get('title', '')} | 요약: {news.get('summary', '')}")

    news_block = "\n".join(news_texts)

    prompt = f"""당신은 유튜브 채널 컨셉 분석 전문가입니다.

아래는 유튜브 채널의 컨셉 키워드입니다:
{concepts}

아래 뉴스 목록을 분석하고, 각 뉴스가 위 채널 컨셉과 얼마나 관련이 있는지 0~100 점수를 매겨주세요.

뉴스 목록:
{news_block}

반드시 아래 JSON 형식으로만 답변하세요. 다른 텍스트는 포함하지 마세요:
[
  {{"index": 1, "score": 85, "reason": "관련 이유 한 줄"}},
  {{"index": 2, "score": 40, "reason": "관련 이유 한 줄"}}
]
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048,
            )
        )

        text = response.text.strip()
        # JSON 블록 추출
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            scores = json.loads(json_match.group())
        else:
            scores = json.loads(text)

        # 뉴스 목록에 점수 추가
        for item in scores:
            idx = item.get("index", 0) - 1
            if 0 <= idx < len(news_list):
                news_list[idx]["relevance_score"] = item.get("score", 0)
                news_list[idx]["relevance_reason"] = item.get("reason", "")

        # 점수 없는 항목에 기본값
        for news in news_list:
            if "relevance_score" not in news:
                news["relevance_score"] = 0
                news["relevance_reason"] = ""

        # 점수 기준 정렬
        news_list.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return news_list

    except Exception as e:
        # 에러 시 기본값 설정
        for news in news_list:
            news["relevance_score"] = 50
            news["relevance_reason"] = "분석 중 오류 발생"
        return news_list


def generate_shorts_script(news_title: str, news_summary: str, concepts: str) -> dict:
    """
    뉴스를 기반으로 유튜브 쇼츠 대본을 생성합니다.
    5단 구조: 후킹 / 문제 제시 / 핵심 내용 / 반전 또는 인사이트 / 마무리
    """
    client = get_client()

    prompt = f"""당신은 유튜브 쇼츠 대본 작가입니다.
채널 컨셉: {concepts}

아래 뉴스를 기반으로 유튜브 쇼츠 대본을 작성해주세요.

뉴스 제목: {news_title}
뉴스 요약: {news_summary}

대본 규칙:
1. 반드시 아래 5단 구조를 따르세요
2. 전체 길이는 읽는 데 45~60초 분량 (약 300~400자)
3. 채널 톤: 비관적이고 현실적이며, 감성적인 독백 스타일
4. 새벽에 혼자 중얼거리는 듯한 톤
5. 일본 감성의 쓸쓸하고 철학적인 분위기

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "hook": "후킹 - 3초 안에 시선을 잡는 첫 문장 (1~2문장)",
  "problem": "문제 제시 - 공감을 유발하는 상황 설명 (2~3문장)",
  "core": "핵심 내용 - 이슈의 핵심을 감성적으로 전달 (3~4문장)",
  "twist": "반전 또는 인사이트 - 예상 못한 시각 제시 (2~3문장)",
  "closing": "마무리 - 비관적이고 현실적인 톤으로 끝내기 (1~2문장)"
}}
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=2048,
            )
        )

        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            script = json.loads(json_match.group())
        else:
            script = json.loads(text)

        return script

    except Exception as e:
        raise RuntimeError(f"대본 생성 중 오류가 발생했습니다: {str(e)}")


def generate_image_prompt(script: dict) -> str:
    """
    대본에 맞는 AI 이미지 생성용 영어 프롬프트를 생성합니다.
    스타일: 디스토피아 지브리 / 새벽 도시 / 쓸쓸한 분위기
    """
    client = get_client()

    full_script = "\n".join([
        script.get("hook", ""),
        script.get("problem", ""),
        script.get("core", ""),
        script.get("twist", ""),
        script.get("closing", ""),
    ])

    prompt = f"""You are an AI image prompt engineer.

Based on the following Korean YouTube Shorts script, create a single detailed English prompt for AI image generation (Midjourney/DALL-E style).

Script:
{full_script}

Style requirements:
- Studio Ghibli art style BUT dystopian and melancholic atmosphere
- Dawn/early morning city or a solitary figure alone
- 16:9 aspect ratio, 4K cinematic quality
- Soft muted colors with cool blue/purple tones
- Atmospheric fog or haze
- Detailed environment with emotional depth
- No text in the image

Output ONLY the English prompt, nothing else. Make it one paragraph, highly detailed.
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1024,
            )
        )
        return response.text.strip()

    except Exception as e:
        raise RuntimeError(f"이미지 프롬프트 생성 중 오류가 발생했습니다: {str(e)}")


def split_subtitles(script: dict) -> list:
    """
    대본을 자막 단위(2~6단어)로 분리합니다.
    """
    client = get_client()

    full_script = "\n".join([
        script.get("hook", ""),
        script.get("problem", ""),
        script.get("core", ""),
        script.get("twist", ""),
        script.get("closing", ""),
    ])

    prompt = f"""아래 대본을 유튜브 쇼츠 자막용으로 분리해주세요.

규칙:
1. 각 자막은 한국어 기준 2~6단어(어절) 이내로 끊어주세요
2. 자연스러운 호흡 단위로 분리하세요
3. 한 줄에 하나의 자막만 적으세요
4. 번호나 기호 없이 텍스트만 출력하세요

대본:
{full_script}
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=2048,
            )
        )

        lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
        return lines

    except Exception as e:
        raise RuntimeError(f"자막 분리 중 오류가 발생했습니다: {str(e)}")


def analyze_video_structure(transcript_text: str) -> dict:
    """
    영상 자막을 분석하여 구조, 감정선, 키워드 등을 추출합니다.
    """
    client = get_client()

    # 자막이 너무 길면 잘라서 보냄
    if len(transcript_text) > 15000:
        transcript_text = transcript_text[:15000] + "\n...(이하 생략)"

    prompt = f"""당신은 유튜브 영상 분석 전문가입니다.

아래 영상 자막을 분석해서 다음 항목들을 JSON 형식으로 답변해주세요.

자막 전문:
{transcript_text}

분석 항목:
1. structure: 영상 전체 구조 분석 (인트로/전개/클라이맥스/아웃트로 각각 설명)
2. hook: 처음 부분에서 나온 핵심 후킹 문구 (원문 그대로)
3. emotion_flow: 감정선 흐름 (초반/중반/후반 각각의 감정 톤)
4. top_keywords: 반복 등장 키워드 상위 10개 (배열)
5. risk_sections: 시청자 이탈 위험 구간 설명 (내용이 늘어지거나 전환이 없는 부분)
6. success_factors: 이 영상의 핵심 성공 요인 3가지 (배열)

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "structure": {{
    "intro": "인트로 설명",
    "development": "전개 설명",
    "climax": "클라이맥스 설명",
    "outro": "아웃트로 설명"
  }},
  "hook": "후킹 문구",
  "emotion_flow": {{
    "early": "초반 감정 톤",
    "middle": "중반 감정 톤",
    "late": "후반 감정 톤"
  }},
  "top_keywords": ["키워드1", "키워드2", ...],
  "risk_sections": "이탈 위험 구간 설명",
  "success_factors": ["요인1", "요인2", "요인3"]
}}
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.4,
                max_output_tokens=3000,
            )
        )

        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)

    except Exception as e:
        raise RuntimeError(f"영상 구조 분석 중 오류가 발생했습니다: {str(e)}")


def analyze_thumbnail(image_url: str) -> dict:
    """
    썸네일 이미지를 Gemini Vision으로 분석합니다.
    """
    client = get_client()

    prompt = """이 유튜브 썸네일 이미지를 분석해주세요.

다음 항목을 JSON 형식으로 평가해주세요:
1. has_text: 텍스트 포함 여부 (true/false)
2. text_count: 텍스트가 있다면 대략적인 글자 수
3. has_person: 인물 포함 여부 (true/false)
4. emotion_level: 감정 표현 수준 ("강함" / "보통" / "약함")
5. click_factors: 클릭 유발 요소 분석 (문자열)
6. improvements: 개선 제안 2가지 (배열)

반드시 JSON 형식으로만 답변하세요:
{
  "has_text": true,
  "text_count": 5,
  "has_person": true,
  "emotion_level": "강함",
  "click_factors": "클릭 유발 요소 설명",
  "improvements": ["제안1", "제안2"]
}
"""

    try:
        response = generate_content(client,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(file_uri=image_url, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1500,
            )
        )

        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)

    except Exception as e:
        raise RuntimeError(f"썸네일 분석 중 오류가 발생했습니다: {str(e)}")


def analyze_thumbnail_from_bytes(image_bytes: bytes) -> dict:
    """
    썸네일 이미지 바이트를 Gemini Vision으로 분석합니다.
    """
    client = get_client()

    prompt = """이 유튜브 썸네일 이미지를 분석해주세요.

다음 항목을 JSON 형식으로 평가해주세요:
1. has_text: 텍스트 포함 여부 (true/false)
2. text_count: 텍스트가 있다면 대략적인 글자 수
3. has_person: 인물 포함 여부 (true/false)
4. emotion_level: 감정 표현 수준 ("강함" / "보통" / "약함")
5. click_factors: 클릭 유발 요소 분석 (문자열)
6. improvements: 개선 제안 2가지 (배열)

반드시 JSON 형식으로만 답변하세요:
{
  "has_text": true,
  "text_count": 5,
  "has_person": true,
  "emotion_level": "강함",
  "click_factors": "클릭 유발 요소 설명",
  "improvements": ["제안1", "제안2"]
}
"""

    try:
        response = generate_content(client,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1500,
            )
        )

        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)

    except Exception as e:
        raise RuntimeError(f"썸네일 분석 중 오류가 발생했습니다: {str(e)}")


def compare_videos(videos_data: list) -> str:
    """
    여러 영상의 데이터를 비교 분석합니다.
    """
    client = get_client()

    video_info = ""
    for i, v in enumerate(videos_data, 1):
        video_info += f"""
영상 {i}: {v.get('title', 'N/A')}
- 채널: {v.get('channel', 'N/A')} (구독자: {v.get('subscribers', 'N/A')})
- 조회수: {v.get('views', 'N/A')}
- 좋아요: {v.get('likes', 'N/A')}
- 댓글: {v.get('comments', 'N/A')}
- 좋아요/조회수: {v.get('like_ratio', 'N/A')}%
- 댓글/조회수: {v.get('comment_ratio', 'N/A')}%
- 영상 길이: {v.get('duration', 'N/A')}
"""

    prompt = f"""당신은 유튜브 영상 분석 전문가입니다.

아래 영상들의 데이터를 비교 분석하고 종합 평가를 해주세요.

{video_info}

분석 항목:
1. 어떤 영상이 가장 효율적인지 (조회수 대비 인게이지먼트)
2. 각 영상의 강점과 약점
3. 전체적인 인사이트와 배울 점

한국어로 자세하게 분석해주세요. 마크다운 형식 없이 일반 텍스트로 답변하세요.
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=2000,
            )
        )
        return response.text.strip()

    except Exception as e:
        raise RuntimeError(f"비교 분석 중 오류가 발생했습니다: {str(e)}")


def analyze_growth_channels(channels_data: list, category: str, region: str) -> str:
    """
    급성장 채널 데이터를 분석하여 트렌드 인사이트를 제공합니다.
    """
    client = get_client()

    channel_info = ""
    for i, ch in enumerate(channels_data, 1):
        channel_info += f"""
{i}. {ch.get('channel_name', 'N/A')}
   - 구독자: {ch.get('subscribers', 'N/A')}
   - 분석 기간 총 조회수: {ch.get('total_views', 'N/A')}
   - 영상당 평균 조회수: {ch.get('avg_views', 'N/A')}
   - 분석 영상 수: {ch.get('video_count', 'N/A')}개
   - 성장 지수(평균 조회수/구독자): {ch.get('growth_score', 'N/A')}%
   - 최고 영상/구독자 비율: {ch.get('top_video_sub_ratio', 'N/A')}%
   - 평균 일 조회수 속도: {ch.get('avg_views_per_day', 'N/A')}
   - 알고리즘 신호 점수: {ch.get('algorithm_score', 'N/A')}
   - 소형 채널 발굴 점수: {ch.get('discovery_score', 'N/A')}
   - 주요 신호: {", ".join(ch.get('algorithm_signals', []))}
"""

    prompt = f"""당신은 유튜브 채널 성장 분석 전문가입니다.

아래는 [{region}] 지역, [{category}] 카테고리에서 구독자 대비 조회수와 확산 속도가 높은 채널 데이터입니다.

{channel_info}

다음 항목들을 분석해주세요:

1. 알고리즘이 이 채널들을 밀어줬을 가능성이 높은 이유
2. 구독자 대비 조회수가 튄 채널들의 공통 패턴
3. 썸네일/제목/주제 선택에서 추정되는 클릭 유도 구조
4. 영상 구성에서 반복될 가능성이 높은 후킹 방식
5. 새 채널이 따라 할 수 있는 실전 전략 5가지
6. 주의해야 할 착시 지표와 검증 방법

한국어로 자세하게 분석해주세요. 마크다운 형식 없이 일반 텍스트로 답변하세요.
분석은 실용적이고 크리에이터가 바로 적용할 수 있는 인사이트를 제공해주세요.
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.6,
                max_output_tokens=2500,
            )
        )
        return response.text.strip()

    except Exception as e:
        raise RuntimeError(f"성장 트렌드 분석 중 오류가 발생했습니다: {str(e)}")


def analyze_video_algorithm_strategy(video_data: dict, transcript_text: str = "") -> dict:
    """
    영상의 메타데이터와 가능한 경우 자막을 함께 사용해 알고리즘/후킹/구성 전략을 분석합니다.
    """
    client = get_client()

    if len(transcript_text) > 15000:
        transcript_text = transcript_text[:15000] + "\n...(이하 생략)"

    transcript_block = transcript_text if transcript_text else "자막 없음. 제목, 성과 지표, 업로드 정보 기반으로 추정 분석."
    prompt = f"""당신은 유튜브 알고리즘과 쇼츠/롱폼 대본 구조를 분석하는 전문가입니다.

아래 영상 데이터를 분석해서 JSON으로 답변하세요.

영상 데이터:
- 제목: {video_data.get('title', '')}
- 영상 유형: {video_data.get('v_type', '')}
- 조회수: {video_data.get('views', 0)}
- 좋아요: {video_data.get('likes', 0)}
- 댓글: {video_data.get('comments', 0)}
- 좋아요율: {video_data.get('like_ratio', 0)}%
- 댓글율: {video_data.get('comment_ratio', 0)}%
- 업로드일: {video_data.get('published', '')}
- 일 조회수: {video_data.get('views_per_day', 0)}

자막:
{transcript_block}

분석 기준:
1. 자막이 있으면 실제 대본 구조를 우선 분석한다.
2. 자막이 없으면 제목, 지표, 영상 유형을 기반으로 추정이라고 명확히 표현한다.
3. "왜 알고리즘이 반응했을지", "처음 5초 후킹", "중반 유지 장치", "댓글/공유 유도 장치"를 실전적으로 분석한다.

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "algorithm_reason": "알고리즘 반응 가능성 분석",
  "one_line_reason": "왜 터졌는지 한 줄 요약",
  "structure": {{
    "opening": "초반 구성",
    "development": "중반 구성",
    "payoff": "후반 보상/반전",
    "ending": "마무리 구조"
  }},
  "hook_analysis": "후킹 방식과 심리 장치",
  "retention_devices": ["유지 장치1", "유지 장치2", "유지 장치3"],
  "editing_recipe": ["편집에 바로 적용할 작업1", "작업2", "작업3"],
  "replicable_formula": "다른 영상에 적용할 수 있는 공식",
  "cautions": "추정의 한계와 확인해야 할 점"
}}
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.45,
                max_output_tokens=3000,
            )
        )

        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)

    except Exception as e:
        raise RuntimeError(f"영상 알고리즘 분석 중 오류가 발생했습니다: {str(e)}")


def generate_reference_rebuild_package(video_data: dict, transcript_text: str = "") -> dict:
    """
    레퍼런스 영상의 구조를 분석해 새 쇼츠 제작 패키지를 생성합니다.
    원본 영상 복제나 재업로드가 아니라 새 대본/새 구성/새 편집안을 만드는 용도입니다.
    """
    client = get_client()

    if len(transcript_text) > 12000:
        transcript_text = transcript_text[:12000] + "\n...(이하 생략)"

    transcript_block = transcript_text if transcript_text else "자막 없음. 제목/설명/성과 지표 기반으로 추정."
    prompt = f"""당신은 유튜브 쇼츠 기획자이자 프리미어 프로 편집 설계자입니다.

아래 레퍼런스 영상은 구조와 성공 요인을 참고하기 위한 것입니다.
원본 영상의 문장, 고유한 표현, 장면을 복제하지 말고, 같은 성공 공식을 바탕으로 완전히 새로운 쇼츠 제작안을 만들어주세요.
출처는 기록하되, 새 영상은 독립적인 대본과 시각 자료로 제작되어야 합니다.

레퍼런스 데이터:
- 제목: {video_data.get('title', '')}
- 채널: {video_data.get('channel', video_data.get('channel_name', ''))}
- 영상 ID: {video_data.get('video_id', '')}
- 조회수: {video_data.get('views', 0)}
- 좋아요: {video_data.get('likes', 0)}
- 댓글: {video_data.get('comments', 0)}
- 영상 유형: {video_data.get('v_type', '')}
- 설명: {video_data.get('description', '')}

자막/내용:
{transcript_block}

반드시 아래 JSON 형식으로만 답변하세요:
{{
  "reference_summary": "레퍼런스가 왜 뜬 것 같은지 한 줄 요약",
  "source_note": "출처/인용 기록에 넣을 문구",
  "new_angle": "새 영상에서 사용할 독립적인 관점",
  "title_options": ["새 제목1", "새 제목2", "새 제목3"],
  "script": {{
    "hook": "0~3초 새 후킹 대본",
    "context": "3~8초 맥락 설명",
    "proof": "8~18초 근거/사례 전개",
    "payoff": "18~27초 반전/결론",
    "cta": "27~32초 마무리 질문 또는 다음 영상 연결"
  }},
  "subtitle_layout": {{
    "safe_position": "top | middle | bottom",
    "reason": "자막 위치 선택 이유",
    "style": "자막 스타일 설명"
  }},
  "visual_plan": [
    {{"time": "00:00:00", "scene": "장면 설명", "asset_prompt": "새 이미지/영상 생성 프롬프트", "subtitle": "화면 자막"}},
    {{"time": "00:00:03", "scene": "장면 설명", "asset_prompt": "새 이미지/영상 생성 프롬프트", "subtitle": "화면 자막"}}
  ],
  "premiere_markers": [
    {{"time": "00:00:00", "name": "HOOK", "note": "편집 메모"}},
    {{"time": "00:00:03", "name": "CONTEXT", "note": "편집 메모"}}
  ],
  "rights_checklist": ["원본 문장 복제 금지", "출처 기록", "새 시각 자료 사용"]
}}
"""

    try:
        response = generate_content(
            client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.65,
                max_output_tokens=3500,
            )
        )
        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)
    except Exception as e:
        raise RuntimeError(f"레퍼런스 재구성 패키지 생성 중 오류가 발생했습니다: {str(e)}")


def analyze_viral_video(transcript_text: str, video_title: str) -> dict:
    """
    급성장한 영상의 자막을 기반으로 기승전결, 후킹, 대본 형성 이유를 심층 분석합니다.
    """
    client = get_client()

    # 자막이 너무 길면 잘라서 보냄
    if len(transcript_text) > 15000:
        transcript_text = transcript_text[:15000] + "\n...(이하 생략)"

    prompt = f"""당신은 유튜브 대본 분석 및 심리 전문가입니다.

아래는 단기간에 급성장한 유튜브 영상의 제목과 자막입니다.
영상 제목: {video_title}
자막 전문:
{transcript_text}

이 자막 데이터를 기반으로 영상을 심층 분석하여 아래 항목들을 JSON 형식으로 답변해주세요.

분석 항목:
1. structure (기승전결 대본 구성): 대본의 기-승-전-결이 어떻게 나뉘어 있고, 각 단계에서 어떤 흐름으로 진행되는지.
2. hook_analysis (후킹 분석): 대본의 어느 지점(어떤 내용)에서 시청자의 이목을 끄는 강력한 후킹이 발생했는지, 그리고 그 이유.
3. script_strategy (대본 형성 이유): 왜 이런 대본 구조와 단어 선택이 형성되었는지, 시청자의 심리를 어떻게 자극하고 반응을 이끌어내도록 설계되었는지 분석.
4. comprehensive_report (완벽 종합 분석): 위 내용들을 종합하여 이 영상이 성공할 수밖에 없었던 완벽한 종합 분석 내용 (서술형).

반드시 아래 JSON 형식으로만 답변하세요. 다른 텍스트는 포함하지 마세요:
{{
  "structure": {{
    "introduction": "기 (시작 부분 설명)",
    "development": "승 (전개 부분 설명)",
    "turn": "전 (전환 및 절정 부분 설명)",
    "conclusion": "결 (결론 및 마무리 부분 설명)"
  }},
  "hook_analysis": "후킹 지점 및 요인 설명",
  "script_strategy": "이런 대본이 형성된 이유와 시청자 심리 자극 전략",
  "comprehensive_report": "완벽한 종합 분석 내용"
}}
"""

    try:
        response = generate_content(client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.5,
                max_output_tokens=3000,
            )
        )

        text = response.text.strip()
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(text)

    except Exception as e:
        raise RuntimeError(f"급성장 영상 심층 분석 중 오류가 발생했습니다: {str(e)}")


