"""OCR 줄과 규칙 후보를 LLM에 보여 주고 문맥 판정을 받는다.

OpenAI 호환 API(vLLM·Ollama·외부 API)를 쓴다. LLM_BASE_URL이 없으면 판정을 건너뛴다.
"""

import json
import os
import re

import httpx

from detect import LABELS, Candidate, Line

BASE_URL = os.environ.get("LLM_BASE_URL", "").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "")
API_KEY = os.environ.get("LLM_API_KEY", "none")
TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "20"))

PROMPT = """너는 화면 캡처를 공유하기 전에 개인정보·보안 정보 노출을 점검한다.
아래는 캡처를 OCR로 읽은 줄(번호: 내용)과, 규칙이 미리 찾은 후보다.

할 일:
1. 규칙 후보마다 실제로 가려야 하는지 판단한다. 예시·더미 값(example.com, 홍길동 샘플, your_api_key 등)이나 공개된 정보(회사 대표번호, 공식 문의 메일)는 가리지 않아도 된다.
2. 규칙이 놓친 노출을 찾는다. 예: 표 속 학생·고객 이름, 성적·점수와 함께 나온 이름, 메신저 알림 속 보낸 사람과 내용, 집 주소, 계좌번호, 내부 URL·사내 도메인, 비밀번호로 보이는 문자열.
3. 가릴 부분의 text는 그 줄에 나온 글자 그대로, 가능한 한 짧게(값만) 적는다.

분류: {categories}

OCR 줄:
{lines}

규칙 후보:
{candidates}

JSON 하나로만 답한다:
{{"decisions": [{{"id": "c0", "selected": true, "reason": "짧은 이유"}}],
  "additions": [{{"line": 0, "text": "가릴 글자", "category": "name", "reason": "짧은 이유"}}]}}"""


def enabled() -> bool:
    return bool(BASE_URL and MODEL)


def judge(lines: list[Line], candidates: list[Candidate]) -> list[Candidate]:
    prompt = PROMPT.format(
        categories=", ".join(f"{k}({v})" for k, v in LABELS.items()),
        lines="\n".join(f"{l.index}: {l.text}" for l in lines),
        candidates="\n".join(f"{c.id}: [{c.category}] {c.text} (줄 {c.line})" for c in candidates) or "(없음)",
    )
    resp = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": MODEL, "temperature": 0, "messages": [{"role": "user", "content": prompt}]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", content, re.S)
    data = json.loads(m.group(0)) if m else {}

    by_id = {c.id: c for c in candidates}
    for d in data.get("decisions", []):
        c = by_id.get(d.get("id"))
        if c is not None and isinstance(d.get("selected"), bool):
            c.selected = d["selected"]
            c.reason = f"AI: {d.get('reason', '')}".strip()

    by_line = {l.index: l for l in lines}
    result = list(candidates)
    for a in data.get("additions", []):
        line, text = by_line.get(a.get("line")), (a.get("text") or "").strip()
        if line is None or not text:
            continue
        start = line.text.find(text)
        if start < 0:
            continue
        end = start + len(text)
        if any(c.line == line.index and c.start < end and start < c.end for c in result):
            continue
        category = a.get("category") if a.get("category") in LABELS else "other"
        result.append(
            Candidate(f"c{len(result)}", category, text, line.span_box(start, end), True, "llm",
                      f"AI: {a.get('reason', '')}".strip(), line.index, start, end)
        )
    return result
