# app/routers/receipts.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic import field_validator  # Pydantic v2
from typing import List, Optional, Literal
from datetime import datetime
import os
import sqlite3

from app.services.parse_ocr import parse_receipt_bytes

# .env 로드(이미 main에서 했다면 중복 호출 harmless)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

router = APIRouter(prefix="/receipts", tags=["receipts"])

# ---- 업로드 제한/형식 ----
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_MIMES = {
    "image/jpeg",
    "image/png",
    "image/heic",
    "image/heif",
    # iOS/브라우저가 HEIC를 octet-stream으로 넘기는 경우가 흔함
    "application/octet-stream",
}

# ---------------------------
#           Schemas
# ---------------------------

class ReceiptItemIn(BaseModel):
    name: str
    qty: int = Field(gt=0, description="수량(>0)")
    price: int = Field(ge=0, description="단가(>=0)")
    category: Optional[str] = None


class ReceiptConfirmIn(BaseModel):
    user_id: int = 1
    merchant: str
    purchased_at: str  # 'YYYY-MM-DD'
    items: List[ReceiptItemIn]
    total: int = Field(ge=0)
    status: Literal["PENDING", "CONFIRMED"] = "CONFIRMED"
    image_path: Optional[str] = None  # 이미지 경로 저장 안하면 None

    @field_validator("purchased_at")
    @classmethod
    def _v_date(cls, v: str) -> str:
        # YYYY-MM-DD 검증
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("purchased_at must be YYYY-MM-DD")
        return v


# 응답 스키마(가벼운 버전)
class ReceiptRow(BaseModel):
    id: int
    user_id: int
    merchant: str
    total: int
    purchased_at: str
    status: Literal["PENDING", "CONFIRMED"]
    image_path: Optional[str] = None
    created_at: Optional[str] = None


class ReceiptDetailItem(BaseModel):
    id: int
    name: str
    qty: int
    price: int
    category: Optional[str] = None
    subtotal: int


class ReceiptDetail(BaseModel):
    id: int
    user_id: int
    merchant: str
    total: int
    purchased_at: str
    status: Literal["PENDING", "CONFIRMED"]
    image_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items: List[ReceiptDetailItem]


# ---------------------------
#         Endpoints
# ---------------------------

@router.get("", response_model=dict)
def list_receipts(limit: int = 50, offset: int = 0):
    """
    최근 영수증 목록 조회 (페이징)
    """
    from app.db.util import get_conn
    with get_conn() as conn:
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
            ReceiptRow(
                id=r["id"],
                user_id=r["user_id"],
                merchant=r["merchant"],
                total=r["total"],
                purchased_at=r["purchased_at"],
                status=r["status"],
                image_path=r["image_path"],
                created_at=r["created_at"],
            ).model_dump()
            for r in rows
        ]
        return {"status": "ok", "count": len(data), "data": data}


@router.get("/{receipt_id}", response_model=dict)
def get_receipt_detail(receipt_id: int = Path(..., ge=1)):
    """
    영수증 단건 상세 (품목 포함)
    """
    from app.db.util import get_conn
    with get_conn() as conn:
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

        detail = ReceiptDetail(
            id=r["id"],
            user_id=r["user_id"],
            merchant=r["merchant"],
            total=r["total"],
            purchased_at=r["purchased_at"],
            status=r["status"],
            image_path=r["image_path"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            items=[
                ReceiptDetailItem(
                    id=it["id"],
                    name=it["name"],
                    qty=it["qty"],
                    price=it["price"],
                    category=it["category"],
                    subtotal=it["subtotal"],
                )
                for it in items
            ],
        )
        return {"status": "ok", "data": detail.model_dump()}


@router.post("/upload", response_model=dict)
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


@router.post("/confirm", response_model=dict)
def confirm_receipt(payload: ReceiptConfirmIn):
    """
    OCR 결과를 사용자가 확인한 뒤 최종 저장.
    - receipts / receipt_items 에 트랜잭션으로 insert
    - total 불일치 시 items 합계를 우선(저장 값은 items 합)
    - UNIQUE(user_id, merchant, total, purchased_at) 충돌 시 409 반환
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="items 최소 1개 필요")

    calc_total = sum(it.qty * it.price for it in payload.items)

    from app.db.util import get_conn
    try:
        with get_conn() as conn:
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
                    payload.status,
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

            # sqlite3 context manager는 정상 종료 시 자동 commit 함.
            return {"status": "ok", "receipt_id": receipt_id, "saved_total": calc_total, "items_saved": items_saved}

    except sqlite3.IntegrityError as e:
        # UNIQUE(uq_receipt_dedup) 충돌 케이스
        msg = str(e)
        if "uq_receipt_dedup" in msg or "UNIQUE constraint failed" in msg:
            raise HTTPException(status_code=409, detail="이미 저장된 영수증일 수 있어요(중복 가능성).")
        raise
    except Exception as e:
        # with 블록에서 예외 발생 시 자동 rollback
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {e}")