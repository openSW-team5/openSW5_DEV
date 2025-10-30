# app/services/parse_ocr.py
import os
import json

# .env 에서 읽은 모드 (기본: mock)
OCR_MODE = os.getenv("OCR_MODE", "mock").lower()

# mock JSON 경로 (.env에서 OCR_MOCK_PATH로 바꿀 수도 있음)
MOCK_PATH = os.getenv("OCR_MOCK_PATH", "app/mock/sample_receipt.json")


def parse_receipt_bytes(file_bytes: bytes, filename: str, content_type: str):
    """
    업로드된 이미지 바이트를 입력으로 받아 OCR 결과 JSON을 반환.
    - mock: 로컬 JSON을 읽어서 그대로 반환
    - live: CLOVA OCR API 호출 (지연 임포트로 순환임포트 방지)
    """
    if OCR_MODE == "mock":
        with open(MOCK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # live 모드일 때만 임포트 (모듈 로드시 순환 임포트 방지)
    from app.services.clova_client import request_clova_ocr_bytes

    return request_clova_ocr_bytes(
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )