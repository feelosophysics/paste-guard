"""시험용 화면 캡처를 만든다. 모든 이름·번호·키는 가짜다.

uv run python make_samples.py  →  ../demo/samples/*.png
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "demo" / "samples"

FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]
MONO_CANDIDATES = ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/System/Library/Fonts/Menlo.ttc"]


def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    for path in (MONO_CANDIDATES if mono else []) + FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("한글 글꼴을 찾지 못했습니다. FONT_CANDIDATES에 경로를 추가하세요.")


def lms_grades() -> Image.Image:
    """수업 관리 화면: 학생 이름·학번·메일·점수 표와 구석의 메신저 알림."""
    im = Image.new("RGB", (900, 520), "#f5f6f8")
    d = ImageDraw.Draw(im)
    f, fb, fs = font(17), font(22), font(15)
    d.rectangle((0, 0, 900, 56), fill="#2b3a55")
    d.text((24, 15), "과제 제출 현황 · 3주차 실습", font=fb, fill="white")
    rows = [
        ("학생명", "학번", "이메일", "점수"),
        ("김민지", "20231457", "minji.kim22@snu.ac.kr", "92"),
        ("이도윤", "20231502", "doyoon0612@naver.com", "78"),
        ("박서연", "20231633", "seoyeon.p@gmail.com", "85"),
        ("최하준", "20231711", "hajun.choi@korea.ac.kr", "64"),
    ]
    xs = [40, 170, 320, 640]
    for r, row in enumerate(rows):
        y = 90 + r * 48
        d.rectangle((24, y - 10, 720, y + 34), fill="white" if r else "#e4e8ef")
        for x, cell in zip(xs, row):
            d.text((x, y), cell, font=f, fill="#222")
    # 화면 오른쪽 아래 메신저 알림
    d.rounded_rectangle((560, 380, 880, 500), 12, fill="#ffffff", outline="#cfd5df")
    d.text((580, 395), "메신저 · 방금", font=fs, fill="#888")
    d.text((580, 422), "정유나 (학부모)", font=f, fill="#222")
    d.text((580, 452), "선생님, 유나 내일 병원 때문에 결석해요", font=fs, fill="#444")
    return im


def dev_env() -> Image.Image:
    """개발 튜토리얼 화면: 진짜 키와 예시 키가 섞인 설정 파일."""
    im = Image.new("RGB", (900, 420), "#1e1e1e")
    d = ImageDraw.Draw(im)
    f = font(18, mono=True)
    d.rectangle((0, 0, 900, 36), fill="#2d2d2d")
    d.text((16, 8), ".env", font=font(15, mono=True), fill="#ccc")
    lines = [
        ("# 실습용 설정", "#6a9955"),
        ("OPENAI_API_KEY=sk-demo-4fQ9xLm2Vb7Rt1ZpK8sW3nYd", "#9cdcfe"),
        ("ANTHROPIC_API_KEY=your_api_key_here", "#9cdcfe"),
        ("DB_PASSWORD=Tiger!2026blue", "#9cdcfe"),
        ("ADMIN_EMAIL=admin@example.com", "#9cdcfe"),
        ("CALLBACK=https://lab.internal.mycorp.kr/auth?token=eyJhbGciOiJIUzI1", "#9cdcfe"),
        ("GITHUB_TOKEN=ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4", "#9cdcfe"),
    ]
    for i, (text, color) in enumerate(lines):
        d.text((24, 60 + i * 44), text, font=f, fill=color)
    return im


def chat_share() -> Image.Image:
    """단체방 공지 캡처: 연락처와 주소가 대화 속에 섞여 있다."""
    im = Image.new("RGB", (720, 460), "#b2c7d9")
    d = ImageDraw.Draw(im)
    f, fs = font(17), font(14)
    bubbles = [
        ("운영진 한지수", "이번 주 모임 장소 공지드립니다"),
        ("운영진 한지수", "서울 마포구 월드컵북로 12길 34, 3층"),
        ("운영진 한지수", "늦으시면 010-4821-9375 로 연락 주세요"),
        ("문의", "공식 문의: help@example.org / 1588-0000"),
    ]
    y = 24
    for who, msg in bubbles:
        d.text((24, y), who, font=fs, fill="#333")
        w = d.textlength(msg, font=f) + 32
        d.rounded_rectangle((24, y + 22, 24 + w, y + 66), 10, fill="white")
        d.text((40, y + 32), msg, font=f, fill="#111")
        y += 100
    return im


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in [("lms_grades", lms_grades), ("dev_env", dev_env), ("chat_share", chat_share)]:
        make().save(OUT / f"{name}.png")
        print(OUT / f"{name}.png")
