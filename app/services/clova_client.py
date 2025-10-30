# app/services/clova_client.py
"""
CLOVA Document OCR(영수증) 호출 전용 클라이언트.
- .env에서 CLOVA_OCR_URL, CLOVA_OCR_SECRET 읽어 multipart 업로드
- 파일 바이트/경로 모두 지원
- 반환: CLOVA 원본 JSON (파싱은 parse_ocr.py에서)
"""
import json
import os
from uuid import uuid4
from time import time

import requests
from dotenv import load_dotenv

load_dotenv()

CLOVA_OCR_URL = os.getenv("CLOVA_OCR_URL", "")        # API Gateway URL
CLOVA_OCR_SECRET = os.getenv("CLOVA_OCR_SECRET", "")  # X-OCR-SECRET

if not CLOVA_OCR_URL:
    # 운영에서 빈 값이면 에러가 나도록 명확히
    print("[clova_client] WARN: CLOVA_OCR_URL is empty. Set in .env")
if not CLOVA_OCR_SECRET:
    print("[clova_client] WARN: CLOVA_OCR_SECRET is empty. Set in .env")


def _build_message(filename: str, fmt: str = "jpg", lang: str = "ko") -> str:
    """
    CLOVA OCR이 요구하는 message(JSON string) 구성
    - images[].name 값은 files 의 필드명과 매칭
    """
    message = {
        "version": "V2",
        "requestId": str(uuid4()),
        "timestamp": int(time() * 1000),
        "lang": lang,
        "images": [
            {"format": fmt, "name": filename}
        ],
    }
    return json.dumps(message, ensure_ascii=False)


def request_clova_ocr_bytes(file_bytes: bytes, filename: str = "receipt.jpg", content_type: str = "image/jpeg"):
    """
    파일 바이트로 CLOVA OCR 호출 (권장)
    """
    if not CLOVA_OCR_URL or not CLOVA_OCR_SECRET:
        raise RuntimeError("CLOVA_OCR_URL / CLOVA_OCR_SECRET not configured")

    message = _build_message(filename=filename, fmt=filename.split(".")[-1].lower())

    files = {
        # 'file' 키 이름은 API 설정에 따라 'file', 'files' 등일 수 있음(일반적으로 'file')
        'file': (filename, file_bytes, content_type),
        'message': (None, message, 'application/json; charset=UTF-8'),
    }
    headers = {
        "X-OCR-SECRET": CLOVA_OCR_SECRET
    }

    resp = requests.post(CLOVA_OCR_URL, headers=headers, files=files, timeout=30)
    resp.raise_for_status()
    return resp.json()


def request_clova_ocr(path: str):
    """
    파일 경로로 CLOVA OCR 호출 (임시파일 저장이 쉬울 때)
    """
    with open(path, "rb") as f:
        data = f.read()
    # 간단 매핑
    name = os.path.basename(path) or "receipt.jpg"
    ctype = "image/jpeg"
    if name.lower().endswith(".png"):
        ctype = "image/png"
    return request_clova_ocr_bytes(data, filename=name, content_type=ctype)