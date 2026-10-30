"""Paste Guard 점검 서버. 이미지를 받아 노출 후보와 위치를 돌려준다."""

import io
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

import detect
import llm

ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    detect.engine()  # 첫 요청이 느리지 않게 OCR 모델을 미리 올린다
    yield


app = FastAPI(title="Paste Guard", lifespan=lifespan)
# 데모 페이지에서 확장 없이 바로 부를 수 있게 연다. 확장은 백그라운드에서 호출하므로 CORS와 무관하다
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    return {"ok": True, "llm": llm.MODEL if llm.enabled() else None}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), use_llm: bool = True) -> dict:
    data = await file.read()
    with Image.open(io.BytesIO(data)) as im:
        width, height = im.size

    t0 = time.perf_counter()
    lines = detect.ocr(data)
    t1 = time.perf_counter()
    candidates = detect.rule_candidates(lines)

    llm_status = "off"
    if use_llm and llm.enabled():
        try:
            candidates = llm.judge(lines, candidates)
            llm_status = "ok"
        except Exception as e:  # LLM이 실패해도 규칙 후보로 계속 쓸 수 있게 한다
            llm_status = f"error: {e.__class__.__name__}"
    t2 = time.perf_counter()

    return {
        "width": width,
        "height": height,
        "candidates": [c.as_dict() for c in candidates],
        "lines": [{"text": l.text, "box": [round(v, 1) for v in l.box]} for l in lines],
        "llm": llm_status,
        "timing_ms": {"ocr": round((t1 - t0) * 1000), "judge": round((t2 - t1) * 1000)},
    }


app.mount("/ext", StaticFiles(directory=ROOT / "extension"), name="ext")
app.mount("/demo", StaticFiles(directory=ROOT / "demo", html=True), name="demo")


@app.get("/")
def index() -> RedirectResponse:
    return RedirectResponse("/demo/")
