"""
PDF 리포트 생성 모듈
분석 결과를 PDF 파일로 내보냅니다.
"""

import io
import os
from fpdf import FPDF


class ReportPDF(FPDF):
    """분석 리포트용 PDF 클래스"""

    def __init__(self):
        super().__init__()
        # 한국어 지원을 위한 유니코드 폰트 등록
        font_dir = os.path.join(os.path.dirname(__file__), '..', 'fonts')
        font_path = os.path.join(font_dir, 'NotoSansKR-Regular.ttf')
        font_bold_path = os.path.join(font_dir, 'NotoSansKR-Bold.ttf')

        if os.path.exists(font_path):
            self.add_font('NotoSansKR', '', font_path, uni=True)
            self.default_font = 'NotoSansKR'
        else:
            self.default_font = 'Helvetica'

        if os.path.exists(font_bold_path):
            self.add_font('NotoSansKR', 'B', font_bold_path, uni=True)

    def header(self):
        self.set_font(self.default_font, 'B' if self.default_font == 'NotoSansKR' else '', 14)
        self.set_text_color(120, 100, 220)
        self.cell(0, 10, '유튜브 영상 분석 리포트', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        self.set_draw_color(60, 60, 80)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.default_font, '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')


def generate_report_pdf(video_data: dict, analysis: dict = None, thumbnail_analysis: dict = None) -> bytes:
    """분석 결과를 PDF 바이트로 변환합니다."""
    pdf = ReportPDF()
    pdf.add_page()
    fn = pdf.default_font

    # 기본 정보
    pdf.set_font(fn, 'B' if fn == 'NotoSansKR' else '', 12)
    pdf.set_text_color(167, 139, 250)
    pdf.cell(0, 8, '기본 정보', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font(fn, '', 10)
    pdf.set_text_color(220, 220, 220)

    info_lines = [
        f"영상 제목: {video_data.get('title', 'N/A')}",
        f"채널: {video_data.get('channel', 'N/A')} (구독자: {video_data.get('subscribers', 'N/A')})",
        f"조회수: {video_data.get('views_formatted', 'N/A')}",
        f"좋아요: {video_data.get('likes_formatted', 'N/A')} ({video_data.get('like_ratio', 0)}%)",
        f"댓글: {video_data.get('comments_formatted', 'N/A')} ({video_data.get('comment_ratio', 0)}%)",
        f"업로드일: {video_data.get('upload_date', 'N/A')}",
        f"영상 길이: {video_data.get('duration', 'N/A')}",
    ]

    for line in info_lines:
        pdf.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)

    # 구조 분석
    if analysis:
        pdf.set_font(fn, 'B' if fn == 'NotoSansKR' else '', 12)
        pdf.set_text_color(167, 139, 250)
        pdf.cell(0, 8, '영상 구조 분석', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        pdf.set_font(fn, '', 10)
        pdf.set_text_color(220, 220, 220)

        structure = analysis.get('structure', {})
        for key, label in [('intro', '인트로'), ('development', '전개'), ('climax', '클라이맥스'), ('outro', '아웃트로')]:
            val = structure.get(key, '')
            if val:
                pdf.multi_cell(0, 6, f"[{label}] {val}")
                pdf.ln(2)

        hook = analysis.get('hook', '')
        if hook:
            pdf.ln(3)
            pdf.set_text_color(167, 139, 250)
            pdf.cell(0, 7, f'후킹 문구: "{hook}"', new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(220, 220, 220)

        ef = analysis.get('emotion_flow', {})
        if ef:
            pdf.ln(3)
            pdf.cell(0, 7, f"감정선: 초반({ef.get('early','')}) → 중반({ef.get('middle','')}) → 후반({ef.get('late','')})", new_x="LMARGIN", new_y="NEXT")

        kw = analysis.get('top_keywords', [])
        if kw:
            pdf.ln(3)
            pdf.cell(0, 7, f"핵심 키워드: {', '.join(kw[:10])}", new_x="LMARGIN", new_y="NEXT")

        risk = analysis.get('risk_sections', '')
        if risk:
            pdf.ln(3)
            pdf.multi_cell(0, 6, f"이탈 위험: {risk}")

        sf = analysis.get('success_factors', [])
        if sf:
            pdf.ln(3)
            pdf.cell(0, 7, '성공 요인:', new_x="LMARGIN", new_y="NEXT")
            for i, f_item in enumerate(sf, 1):
                pdf.cell(0, 7, f"  {i}. {f_item}", new_x="LMARGIN", new_y="NEXT")

    # 썸네일 분석
    if thumbnail_analysis:
        pdf.ln(5)
        pdf.set_font(fn, 'B' if fn == 'NotoSansKR' else '', 12)
        pdf.set_text_color(167, 139, 250)
        pdf.cell(0, 8, '썸네일 분석', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        pdf.set_font(fn, '', 10)
        pdf.set_text_color(220, 220, 220)

        ta = thumbnail_analysis
        pdf.cell(0, 7, f"텍스트 포함: {'예' if ta.get('has_text') else '아니오'} (글자 수: {ta.get('text_count', 0)})", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"인물 포함: {'예' if ta.get('has_person') else '아니오'}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 7, f"감정 표현: {ta.get('emotion_level', 'N/A')}", new_x="LMARGIN", new_y="NEXT")
        pdf.multi_cell(0, 6, f"클릭 요소: {ta.get('click_factors', 'N/A')}")

        improvements = ta.get('improvements', [])
        if improvements:
            pdf.ln(2)
            pdf.cell(0, 7, '개선 제안:', new_x="LMARGIN", new_y="NEXT")
            for imp in improvements:
                pdf.cell(0, 7, f"  • {imp}", new_x="LMARGIN", new_y="NEXT")

    # PDF 바이트 반환
    return pdf.output()


def generate_text_report(video_data: dict, analysis: dict = None, thumbnail_analysis: dict = None) -> str:
    """분석 결과를 텍스트 형식으로 변환합니다."""
    lines = []
    lines.append("=" * 50)
    lines.append("유튜브 영상 분석 리포트")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"영상 제목: {video_data.get('title', 'N/A')}")
    lines.append(f"채널: {video_data.get('channel', 'N/A')} (구독자: {video_data.get('subscribers', 'N/A')})")
    lines.append(f"조회수: {video_data.get('views_formatted', 'N/A')}")
    lines.append(f"좋아요: {video_data.get('likes_formatted', 'N/A')} ({video_data.get('like_ratio', 0)}%)")
    lines.append(f"댓글: {video_data.get('comments_formatted', 'N/A')} ({video_data.get('comment_ratio', 0)}%)")
    lines.append(f"업로드일: {video_data.get('upload_date', 'N/A')}")
    lines.append(f"영상 길이: {video_data.get('duration', 'N/A')}")

    if analysis:
        lines.append("")
        lines.append("-" * 50)
        lines.append("영상 구조 분석")
        lines.append("-" * 50)
        s = analysis.get('structure', {})
        for key, label in [('intro', '인트로'), ('development', '전개'), ('climax', '클라이맥스'), ('outro', '아웃트로')]:
            lines.append(f"[{label}] {s.get(key, '')}")
        lines.append(f"\n후킹 문구: {analysis.get('hook', '')}")
        ef = analysis.get('emotion_flow', {})
        lines.append(f"감정선: 초반({ef.get('early','')}) → 중반({ef.get('middle','')}) → 후반({ef.get('late','')})")
        lines.append(f"핵심 키워드: {', '.join(analysis.get('top_keywords', []))}")
        lines.append(f"이탈 위험: {analysis.get('risk_sections', '')}")
        sf = analysis.get('success_factors', [])
        for i, f_item in enumerate(sf, 1):
            lines.append(f"성공 요인 {i}: {f_item}")

    if thumbnail_analysis:
        lines.append("")
        lines.append("-" * 50)
        lines.append("썸네일 분석")
        lines.append("-" * 50)
        ta = thumbnail_analysis
        lines.append(f"텍스트: {'있음' if ta.get('has_text') else '없음'} ({ta.get('text_count', 0)}자)")
        lines.append(f"인물: {'있음' if ta.get('has_person') else '없음'}")
        lines.append(f"감정 표현: {ta.get('emotion_level', 'N/A')}")
        lines.append(f"클릭 요소: {ta.get('click_factors', 'N/A')}")
        for imp in ta.get('improvements', []):
            lines.append(f"  • {imp}")

    return "\n".join(lines)
