"""화면 캡처에서 노출 후보를 찾는다: OCR → 규칙 후보 → (선택) LLM 문맥 판정."""

import re
from dataclasses import dataclass, field

from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

_engine: RapidOCR | None = None


def engine() -> RapidOCR:
    global _engine
    if _engine is None:
        _engine = RapidOCR(
            params={
                "Rec.lang_type": LangRec.KOREAN,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_type": ModelType.MOBILE,
                # 기본 검출 모델(PP-OCRv6 small)은 표 속 짧은 한글을 자주 놓쳐 v5 모바일을 쓴다
                "Det.ocr_version": OCRVersion.PPOCRV5,
                "Det.model_type": ModelType.MOBILE,
                "Global.text_score": 0.3,
                "Global.log_level": "warning",
            }
        )
    return _engine


@dataclass
class Line:
    index: int
    text: str
    box: tuple[float, float, float, float]  # x0, y0, x1, y1
    # text의 각 글자 위치. 공백 등 OCR이 상자를 주지 않은 글자는 None
    char_boxes: list[tuple[float, float, float, float] | None] = field(default_factory=list)

    def span_box(self, start: int, end: int) -> tuple[float, float, float, float]:
        boxes = [b for b in self.char_boxes[start:end] if b]
        if boxes:
            return (
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            )
        # 글자 상자가 없으면 줄 상자를 글자 수 비율로 나눈다
        x0, y0, x1, y1 = self.box
        n = max(len(self.text), 1)
        w = (x1 - x0) / n
        return (x0 + w * start, y0, x0 + w * end, y1)


def _rect(quad) -> tuple[float, float, float, float]:
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return (float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys)))


def ocr(image_bytes: bytes) -> list[Line]:
    r = engine()(image_bytes, return_word_box=True, return_single_char_box=True)
    if r.boxes is None:
        return []
    lines = []
    words = r.word_results or [()] * len(r.txts)
    for i, (quad, text, chars) in enumerate(zip(r.boxes, r.txts, words)):
        # OCR 글자 목록에는 공백이 빠져 있으므로 text의 공백이 아닌 글자에 차례로 맞춘다
        queue = [(c, _rect(b)) for c, _, b in chars]
        char_boxes: list = []
        for ch in text:
            if ch.isspace() or not queue:
                char_boxes.append(None)
                continue
            c, b = queue[0]
            if len(c) > 1:  # 여러 글자가 한 상자로 온 경우, 상자를 글자 수로 나눈다
                w = (b[2] - b[0]) / len(c)
                char_boxes.append((b[0], b[1], b[0] + w, b[3]))
                queue[0] = (c[1:], (b[0] + w, b[1], b[2], b[3]))
            else:
                char_boxes.append(b)
                queue.pop(0)
        lines.append(Line(i, text, _rect(quad), char_boxes))
    return _merge_fragments(lines)


def _merge_fragments(lines: list[Line]) -> list[Line]:
    """같은 줄에서 바짝 붙은 조각을 합친다. OCR은 밑줄(_) 같은 곳에서 한 줄을 자주 끊는다.
    표의 칸 사이처럼 글자 높이보다 넓게 떨어진 조각은 합치지 않는다."""
    def same_row(a, b) -> bool:
        h = min(a[3] - a[1], b[3] - b[1])
        return min(a[3], b[3]) - max(a[1], b[1]) > 0.5 * h

    rows: list[list[Line]] = []
    for line in sorted(lines, key=lambda l: l.box[1]):
        row = next((r for r in rows if same_row(r[0].box, line.box)), None)
        if row is None:
            rows.append([line])
        else:
            row.append(line)

    merged: list[Line] = []
    for row in rows:
        row.sort(key=lambda l: l.box[0])
        current = row[0]
        for line in row[1:]:
            h = min(current.box[3] - current.box[1], line.box[3] - line.box[1])
            # 조각 상자는 밑줄 한두 글자만큼 겹치기도 한다
            if -0.6 * h <= line.box[0] - current.box[2] < 0.6 * h:
                current.text += " " + line.text
                current.char_boxes += [None] + line.char_boxes
                current.box = (current.box[0], min(current.box[1], line.box[1]),
                               line.box[2], max(current.box[3], line.box[3]))
            else:
                merged.append(current)
                current = line
        merged.append(current)
    for i, line in enumerate(merged):
        line.index = i
    return merged


# ---- 규칙 후보 ----------------------------------------------------------------

LABELS = {
    "email": "이메일",
    "phone": "전화번호",
    "rrn": "주민등록번호",
    "card": "카드번호",
    "secret": "API 키·토큰",
    "url_token": "URL 속 토큰",
    "name": "이름",
    "student_id": "학번·사번",
    "address": "주소",
    "other": "기타 민감 정보",
}

EXAMPLE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "domain.com", "email.com"}
# 공백·밑줄·하이픈을 지운 값에 맞춘다
PLACEHOLDER = re.compile(r"(?i)^(your|my)(api)?(key|token|secret|password)?(here)?$|^(api)?(key|token)here$|^[x*.<>]+$|^<.*>$|^(changeme|todo|none|null)$")

RULES: list[tuple[str, re.Pattern, int]] = [
    # (분류, 패턴, 가릴 그룹 번호)
    # OCR이 @ 앞뒤에 공백을 넣는 경우가 있다
    ("email", re.compile(r"[A-Za-z0-9._%+-]+ ?@ ?[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), 0),
    ("phone", re.compile(r"(?<!\d)01[016789][-. ]?\d{3,4}[-. ]?\d{4}(?!\d)"), 0),
    ("phone", re.compile(r"(?<!\d)0(?:2|[3-6]\d)-\d{3,4}-\d{4}(?!\d)"), 0),
    ("rrn", re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)"), 0),
    ("card", re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)"), 0),
    ("secret", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})"), 0),
    ("url_token", re.compile(r"(?i)[?&](?:token|access_token|key|sig|signature|code|session|sid)=([^&\s]{6,})"), 1),
    # OPENAI_API_KEY=… 처럼 키 이름이 밑줄로 이어져도 잡고, 값은 줄 끝까지 본다(OCR이 값 중간에 공백을 넣기도 한다)
    ("secret", re.compile(r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd)\w*\s*[:=]\s*[\"']?(\S.{3,}?)[\"']?\s*$"), 1),
    ("address", re.compile(r"(?:서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)[가-힣]*\s+[가-힣]+(?:시|군|구)\s+\S+.*"), 0),
    ("student_id", re.compile(r"(?:학번|사번|수험번호)\s*[:：]?\s*(\d{6,10})"), 1),
    ("name", re.compile(r"(?:이름|성명|담당자|학생명|보호자)\s*[:：]?\s*([가-힣]{2,4})"), 1),
]

SURNAMES = set("김이박최정강조윤장임한오서신권황안송류전홍고문양손배백허유남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경")
# 이메일·전화번호 바로 앞의 한글 2~4자는 그 사람의 이름일 가능성이 높다
NAME_BEFORE_CONTACT = re.compile(r"([가-힣]{2,4})\s+(?=[A-Za-z0-9._%+-]+@|01[016789])")


@dataclass
class Candidate:
    id: str
    category: str
    text: str
    box: tuple[float, float, float, float]
    selected: bool
    source: str  # rule / llm
    reason: str
    line: int = -1
    start: int = -1
    end: int = -1

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "label": LABELS.get(self.category, self.category),
            "text": self.text,
            "box": [round(v, 1) for v in self.box],
            "selected": self.selected,
            "source": self.source,
            "reason": self.reason,
        }


def rule_candidates(lines: list[Line]) -> list[Candidate]:
    found: list[Candidate] = []
    taken: dict[int, list[tuple[int, int]]] = {}

    def add(line: Line, cat: str, start: int, end: int, selected: bool, reason: str):
        spans = taken.setdefault(line.index, [])
        if any(s < end and start < e for s, e in spans):
            return
        spans.append((start, end))
        found.append(
            Candidate(f"c{len(found)}", cat, line.text[start:end], line.span_box(start, end),
                      selected, "rule", reason, line.index, start, end)
        )

    for line in lines:
        for cat, pat, group in RULES:
            for m in pat.finditer(line.text):
                s, e = m.span(group)
                value = m.group(group)
                selected, reason = True, f"{LABELS[cat]} 형식"
                if cat == "email" and value.split("@")[-1].strip().lower() in EXAMPLE_EMAIL_DOMAINS:
                    selected, reason = False, "예시용 주소로 보임"
                if cat == "secret" and PLACEHOLDER.match(re.sub(r"[\s_-]", "", value)):
                    selected, reason = False, "자리표시자로 보임"
                add(line, cat, s, e, selected, reason)
        for m in NAME_BEFORE_CONTACT.finditer(line.text):
            if m.group(1)[0] in SURNAMES:
                add(line, "name", *m.span(1), True, "연락처 앞의 이름")
    return found
