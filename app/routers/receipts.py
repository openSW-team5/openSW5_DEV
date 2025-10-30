# app/routers/receipts.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import os

# OCR 파서 (mock/live 자동 분기)
from app.services.parse_ocr import parse_receipt_bytes

# .env에서 업로드 제한 등 읽기 (이미 main.py에서 load_dotenv() 했다면 생략 가능)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

router = APIRouter(prefix="/receipts", tags=["receipts"])

# ---- 업로드 제한/형식 ----
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_MIMES = {"image/jpeg", "image/png", "image/heic", "image/heif"}


# ========== 스키마 ==========
class ReceiptItemIn(BaseModel):
    name: str
    qty: int = Field(gt=0, description="수량(>0)")
    price: int = Field(ge=0, description="단가(>=0)")
    category: Optional[str] = None


class ReceiptConfirmIn(BaseModel):
    user_id: int = 1
    merchant: str
    purchased_at: str  # 'YYYY-MM-DD' (간단히 문자열로)
    items: List[ReceiptItemIn]
    total: int = Field(ge=0)
    status: str = Field(default="CONFIRMED")
    image_path: Optional[str] = None  # '/static/uploads/xxx.jpg' 같이 저장한 경로(선택)


# ========== 목록 조회 ==========
@router.get("")
def list_receipts(limit: int = 50, offset: int = 0):
    """
    최근 영수증 목록 조회 (페이징)
    """
    from app.db.util import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, user_id, merchant, total, purchased_at, status, image_path, created_at
            FROM receipts
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

        data = [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "merchant": r["merchant"],
                "total": r["total"],
                "purchased_at": r["purchased_at"],
                "status": r["status"],
                "image_path": r["image_path"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        return {"status": "ok", "count": len(data), "data": data}
    finally:
        conn.close()


# ========== 상세 조회 ==========
@router.get("/{receipt_id}")
def get_receipt_detail(receipt_id: int = Path(..., ge=1)):
    """
    영수증 단건 상세 (품목 포함)
    """
    from app.db.util import get_conn
    conn = get_conn()
    try:
        r = conn.execute(
            """
            SELECT id, user_id, merchant, total, purchased_at, status, image_path, created_at, updated_at
            FROM receipts
            WHERE id = ?
            """,
            (receipt_id,),
        ).fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="receipt not found")

        items = conn.execute(
            """
            SELECT id, name, qty, price, category, (qty * price) AS subtotal
            FROM receipt_items
            WHERE receipt_id = ?
            ORDER BY id ASC
            """,
            (receipt_id,),
        ).fetchall()

        items_payload = [
            {
                "id": it["id"],
                "name": it["name"],
                "qty": it["qty"],
                "price": it["price"],
                "category": it["category"],
                "subtotal": it["subtotal"],
            }
            for it in items
        ]

        return {
            "status": "ok",
            "data": {
                "id": r["id"],
                "user_id": r["user_id"],
                "merchant": r["merchant"],
                "total": r["total"],
                "purchased_at": r["purchased_at"],
                "status": r["status"],
                "image_path": r["image_path"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "items": items_payload,
            },
        }
    finally:
        conn.close()


# ========== 이미지 업로드 → OCR(JSON) 반환 ==========
@router.post("/upload")
async def upload_receipt(file: UploadFile = File(...)):
    """
    1) 파일 형식/용량 검증
    2) OCR 호출 (mock/live 자동)
    3) 원본 OCR JSON을 그대로 반환 (초기 단계)
       이후 /confirm 으로 클라이언트가 정제/확인한 값을 저장
    """
    # 형식 검사
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 파일 형식: {file.content_type}")

    # 용량 검사
    raw = await file.read()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(status_code=400, detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_MB}MB 허용")

    try:
        ocr_json = parse_receipt_bytes(
            file_bytes=raw,
            filename=file.filename or "receipt.jpg",
            content_type=file.content_type or "image/jpeg",
        )
        return JSONResponse({"status": "ok", "ocr_raw": ocr_json})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR 처리 실패: {e}")


# ========== OCR 결과 확정 저장 ==========
@router.post("/confirm")
def confirm_receipt(payload: ReceiptConfirmIn):
    """
    OCR 결과를 사용자가 확인한 뒤 최종 저장.
    - receipts / receipt_items 에 트랜잭션으로 insert
    - total 불일치 시 items 합계를 우선(저장 값은 items 합)
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="items 최소 1개 필요")

    calc_total = sum(it.qty * it.price for it in payload.items)

    from app.db.util import get_conn
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO receipts (user_id, merchant, total, purchased_at, status, image_path)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.user_id,
                payload.merchant.strip(),
                calc_total,  # 합계는 품목합 기준으로 저장
                payload.purchased_at.strip(),
                payload.status.strip() if payload.status else "CONFIRMED",
                payload.image_path.strip() if payload.image_path else None,
            ),
        )
        receipt_id = cur.lastrowid

        items_saved = 0
        for it in payload.items:
            cur.execute(
                """
                INSERT INTO receipt_items (receipt_id, name, qty, price, category)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    receipt_id,
                    it.name.strip(),
                    it.qty,
                    it.price,
                    it.category.strip() if it.category else None,
                ),
            )
            items_saved += 1

        conn.commit()
        return {"status": "ok", "receipt_id": receipt_id, "saved_total": calc_total, "items_saved": items_saved}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {e}")
    finally:
        conn.close()