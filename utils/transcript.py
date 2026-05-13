"""
자막 추출 모듈
youtube-transcript-api를 사용하여 영상 자막을 가져옵니다.
"""

from youtube_transcript_api import YouTubeTranscriptApi


def get_transcript(video_id: str) -> str:
    """영상 자막을 추출하여 전체 텍스트로 반환합니다."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        # 한국어 우선
        try:
            transcript = transcript_list.find_transcript(['ko'])
        except Exception:
            pass

        # 영어 폴백
        if not transcript:
            try:
                transcript = transcript_list.find_transcript(['en'])
            except Exception:
                pass

        # 자동 생성 자막
        if not transcript:
            try:
                for t in transcript_list:
                    transcript = t
                    break
            except Exception:
                pass

        if not transcript:
            return ""

        entries = transcript.fetch()
        full_text = " ".join([entry['text'] for entry in entries])
        return full_text

    except Exception:
        return ""


def get_transcript_with_timestamps(video_id: str) -> list:
    """타임스탬프 포함 자막 목록을 반환합니다."""
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        transcript = None
        try:
            transcript = transcript_list.find_transcript(['ko'])
        except Exception:
            pass

        if not transcript:
            try:
                transcript = transcript_list.find_transcript(['en'])
            except Exception:
                pass

        if not transcript:
            try:
                for t in transcript_list:
                    transcript = t
                    break
            except Exception:
                pass

        if not transcript:
            return []

        return transcript.fetch()

    except Exception:
        return []
