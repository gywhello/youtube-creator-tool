"""
Shorts storyboard, timeline, and subtitle export helpers.
"""

from __future__ import annotations

import json
import re

from utils.gemini_client import get_client, MODEL_NAME


DEFAULT_SCENES = [
    ("hook", "첫 3초 후킹"),
    ("context", "논란 또는 배경"),
    ("turn", "사람들이 반응한 지점"),
    ("insight", "숨은 의미"),
    ("closing", "마무리"),
]


def generate_shorts_package(trend_item: dict, tone: str, duration: int = 45) -> dict:
    """Generate a complete Shorts production package with AI."""
    client = get_client()
    duration = max(20, min(duration, 60))
    prompt = f"""너는 한국어 쇼츠 편집 기획자야.

아래 핫이슈를 바탕으로 {duration}초짜리 세로 쇼츠 패키지를 만들어줘.

이슈 제목: {trend_item.get("title", "")}
요약: {trend_item.get("summary", "")}
출처: {trend_item.get("source", "")}
톤: {tone}

규칙:
1. 사실처럼 단정하기 어려운 내용은 "온라인에서 이런 반응이 나온다"처럼 조심스럽게 표현해.
2. 혐오, 괴롭힘, 개인정보 노출, 허위 단정은 피하고 안전한 비평 톤으로 써.
3. 전체 화면은 9:16 세로 쇼츠 기준이야.
4. scenes는 5개 장면으로 만들고, 각 장면은 start, end, title, narration, subtitle, image_prompt, visual_note를 포함해.
5. subtitle은 실제 화면에 들어갈 짧은 한국어 문장으로 써.
6. image_prompt는 영어로, 이미지 안에 글자가 없도록 작성해.

반드시 아래 JSON 형식만 출력해.
{{
  "headline": "영상 제목",
  "summary": "전체 기획 요약",
  "hashtags": ["#태그1", "#태그2", "#태그3"],
  "scenes": [
    {{
      "start": 0,
      "end": 5,
      "title": "장면 이름",
      "narration": "내레이션 문장",
      "subtitle": "짧은 자막",
      "image_prompt": "English image generation prompt, no text in image, vertical 9:16",
      "visual_note": "화면 구성 메모"
    }}
  ]
}}
"""
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )
    return normalize_package(_parse_json(response.text), duration)


def fallback_shorts_package(trend_item: dict, tone: str, duration: int = 45) -> dict:
    """Create a deterministic package when an AI key is not configured."""
    title = trend_item.get("title", "오늘의 핫이슈")
    summary = trend_item.get("summary", title)
    duration = max(20, min(duration, 60))
    segment = max(4, duration // len(DEFAULT_SCENES))
    scenes = []

    for index, (key, label) in enumerate(DEFAULT_SCENES):
        start = index * segment
        end = duration if index == len(DEFAULT_SCENES) - 1 else min(duration, start + segment)
        subtitle = _fallback_subtitle(key, title)
        scenes.append(
            {
                "start": start,
                "end": end,
                "title": label,
                "narration": _fallback_narration(key, title, summary, tone),
                "subtitle": subtitle,
                "image_prompt": (
                    "vertical 9:16 cinematic editorial image, Korean online trend mood, "
                    "smartphone glow, city night, realistic documentary style, no text in image"
                ),
                "visual_note": "세로 화면 중앙에 피사체를 두고, 하단 20%는 자막 영역으로 비워둡니다.",
            }
        )

    return {
        "headline": title[:60],
        "summary": summary[:180],
        "hashtags": ["#핫이슈", "#쇼츠", "#트렌드"],
        "scenes": scenes,
    }


def normalize_package(package: dict, duration: int) -> dict:
    scenes = package.get("scenes") or []
    if not scenes:
        return fallback_shorts_package(package, "담백한 비평", duration)

    normalized = []
    previous_end = 0
    for index, scene in enumerate(scenes[:5]):
        start = int(scene.get("start", previous_end))
        end = int(scene.get("end", start + 7))
        if start < previous_end:
            start = previous_end
        if end <= start:
            end = start + 5
        previous_end = end
        normalized.append(
            {
                "start": start,
                "end": min(end, duration),
                "title": scene.get("title") or DEFAULT_SCENES[min(index, 4)][1],
                "narration": scene.get("narration", ""),
                "subtitle": scene.get("subtitle") or scene.get("narration", "")[:32],
                "image_prompt": scene.get("image_prompt", ""),
                "visual_note": scene.get("visual_note", ""),
            }
        )

    if normalized:
        normalized[-1]["end"] = duration

    return {
        "headline": package.get("headline", "쇼츠 기획안"),
        "summary": package.get("summary", ""),
        "hashtags": package.get("hashtags", []),
        "scenes": normalized,
    }


def export_srt(scenes: list[dict]) -> str:
    blocks = []
    for index, scene in enumerate(scenes, 1):
        blocks.append(
            "\n".join(
                [
                    str(index),
                    f"{_srt_time(scene['start'])} --> {_srt_time(scene['end'])}",
                    scene.get("subtitle", ""),
                ]
            )
        )
    return "\n\n".join(blocks)


def export_timeline_json(package: dict) -> str:
    return json.dumps(package, ensure_ascii=False, indent=2)


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise ValueError("AI 응답에서 JSON을 찾지 못했습니다.")
    return json.loads(match.group())


def _srt_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{sec:02},000"


def _fallback_subtitle(key: str, title: str) -> str:
    subtitles = {
        "hook": f"지금 사람들이 보는 건 {title[:18]}",
        "context": "핵심은 사건보다 반응입니다",
        "turn": "여기서 분위기가 바뀌었습니다",
        "insight": "진짜 쟁점은 따로 있습니다",
        "closing": "오늘 이 흐름은 기억해둘 만합니다",
    }
    return subtitles.get(key, title[:32])


def _fallback_narration(key: str, title: str, summary: str, tone: str) -> str:
    if key == "hook":
        return f"{title}. 지금 온라인에서 가장 빠르게 번지는 이야기입니다."
    if key == "context":
        return f"요약하면 {summary[:120]}"
    if key == "turn":
        return f"사람들이 반응한 지점은 사실 하나입니다. {tone} 톤으로 보면 더 선명해집니다."
    if key == "insight":
        return "겉으로는 단순한 이슈처럼 보여도, 그 안에는 지금 사람들이 예민하게 느끼는 감정이 들어 있습니다."
    return "그래서 이 이슈는 결과보다 흐름을 보는 게 중요합니다."
