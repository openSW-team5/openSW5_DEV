# app/services/clova_client.py
"""
CLOVA Document OCR(영수증) 호출 전용 클라이언트.
- .env에서 CLOVA_OCR_URL, CLOVA_OCR_SECRET 읽어 multipart 업로드
- 반환: CLOVA 원본 JSON
"""
import json
import os
from uuid import uuid4
from time import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ✅ 프로젝트 루트의 .env를 "강제로" 로드 (중복 .env 문제 방지)
ROOT = Path(__file__).resolve().parents[2]  # openSW5_DEV
ENV_PATH = ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

CLOVA_OCR_URL = os.getenv("CLOVA_OCR_URL", "").strip()
CLOVA_OCR_SECRET = os.getenv("CLOVA_OCR_SECRET", "").strip()

print("[clova_client] LOADED CLOVA_OCR_URL =", CLOVA_OCR_URL)
print("[clova_client] LOADED CLOVA_OCR_SECRET exists? =", bool(CLOVA_OCR_SECRET))


def _build_message(filename: str, fmt: str = "jpg", lang: str = "ko") -> str:
    message = {
        "version": "V2",
        "requestId": str(uuid4()),
        "timestamp": int(time() * 1000),
        "lang": lang,
        "images": [{"format": fmt, "name": filename}],
    }
    return json.dumps(message, ensure_ascii=False)


def request_clova_ocr_bytes(file_bytes: bytes, filename: str = "receipt.jpg", content_type: str = "image/jpeg"):
    if not CLOVA_OCR_URL or not CLOVA_OCR_SECRET:
        raise RuntimeError(f"CLOVA_OCR_URL / CLOVA_OCR_SECRET not configured (.env path={ENV_PATH})")

    # ✅ 콘솔에서 http로 보여도 실제 호출은 https로 붙는 경우가 많아서 자동 보정
    url = CLOVA_OCR_URL
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
        print("[clova_client] INFO: Auto-fixed URL to HTTPS:", url)

    fmt = (filename.split(".")[-1] or "jpg").lower()
    message = _build_message(filename=filename, fmt=fmt)

    files = {
        "file": (filename, file_bytes, content_type),
        "message": (None, message, "application/json; charset=UTF-8"),
    }
    headers = {"X-OCR-SECRET": CLOVA_OCR_SECRET}

    resp = requests.post(url, headers=headers, files=files, timeout=30)
    resp.raise_for_status()
    return resp.json()