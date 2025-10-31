# app/routers/receipts.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic import field_validator  # pydantic v2
from typing import List, Optional, Literal
from datetime import datetime
import os
import sqlite3

from app.services.parse_ocr import parse_receipt_bytes

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

router = APIRouter(prefix="/receipts", tags=["receipts"])

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_MIMES = {
    "image/jpeg", "image/png", "image/heic", "image/heif", "application/octet-stream",
}

# ---------- Schemas ----------
class ReceiptItemIn(BaseModel):
    name: str
    qty: int = Field(gt=0)
    price: int = Field(ge=0)
    category: Optional[str] = None

class ReceiptConfirmIn(BaseModel):
    user_id: int = 1
    merchant: str
    purchased_at: str  # YYYY-MM-DD
    items: List[ReceiptItemIn]
    total: int = Field(ge=0)
    status: Literal["PENDING", "CONFIRMED"] = "CONFIRMED"
    image_path: Optional[str] = None

    @field_validator("purchased_at")
    @classmethod
    def _v_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("purchased_at must be YYYY-MM-DD")
        return v

class ReceiptUpdateIn(BaseModel):
    merchant: str
    purchased_at: str
    items: List[ReceiptItemIn]
    total: int = Field(ge=0)
    status: Literal["PENDING", "CONFIRMED"] = "CONFIRMED"
    image_path: Optional[str] = None

    @field_validator("purchased_at")
    @classmethod
    def _v_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("purchased_at must be YYYY-MM-DD")
        return v

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

# ---------- Endpoints ----------

@router.get("", response_model=dict)
def list_receipts(limit: int = 50, offset: int = 0):
    from app.db.util import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, merchant, total, purchased_at, status, image_path, created_at
            FROM receipts
            WHERE is_deleted = 0
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
    from app.db.util import get_conn
    with get_conn() as conn:
        r = conn.execute(
            """
            SELECT id, user_id, merchant, total, purchased_at, status, image_path, created_at, updated_at, is_deleted
            FROM receipts
            WHERE id = ?
            """,
            (receipt_id,),
        ).fetchone()

        if not r or r["is_deleted"] == 1:
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
    if file.content_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 파일 형식: {file.content_type}")

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
                    calc_total,
                    payload.purchased_at.strip(),
                    payload.status,
                    payload.image_path.strip() if payload.image_path else None,
                ),
            )
            receipt_id = cur.lastrowid

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

            return {"status": "ok", "receipt_id": receipt_id, "saved_total": calc_total, "items_saved": len(payload.items)}
    except sqlite3.IntegrityError as e:
        if "uq_receipt_dedup" in str(e) or "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="이미 저장된 영수증일 수 있어요(중복 가능성).")
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {e}")


# --------- 기존 PATCH 대체: 명시적 Update (POST) ---------
@router.post("/{receipt_id}/update", response_model=dict)
def update_receipt(receipt_id: int, payload: ReceiptUpdateIn):
    if not payload.items:
        raise HTTPException(status_code=400, detail="items 최소 1개 필요")
    calc_total = sum(it.qty * it.price for it in payload.items)

    from app.db.util import get_conn
    with get_conn() as conn:
        cur = conn.cursor()

        # 존재/삭제 여부 체크
        row = cur.execute(
            "SELECT id, is_deleted FROM receipts WHERE id = ?",
            (receipt_id,),
        ).fetchone()
        if not row or row["is_deleted"] == 1:
            raise HTTPException(status_code=404, detail="receipt not found")

        # 본문 업데이트
        cur.execute(
            """
            UPDATE receipts
               SET merchant = ?, total = ?, purchased_at = ?, status = ?, image_path = ?, updated_at = datetime('now')
             WHERE id = ? AND is_deleted = 0
            """,
            (
                payload.merchant.strip(),
                calc_total,
                payload.purchased_at.strip(),
                payload.status,
                payload.image_path.strip() if payload.image_path else None,
                receipt_id,
            ),
        )

        # 품목 전량 삭제 후 재입력(간단/안전)
        cur.execute("DELETE FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
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

        return {"status": "ok", "receipt_id": receipt_id, "saved_total": calc_total, "items_saved": len(payload.items)}


# --------- 기존 DELETE 대체: Soft Delete (POST) ---------
@router.post("/{receipt_id}/delete", response_model=dict)
def soft_delete_receipt(receipt_id: int):
    from app.db.util import get_conn
    with get_conn() as conn:
        cur = conn.cursor()
        # 이미 삭제됐거나 없는 경우 처리
        cur.execute(
            "UPDATE receipts SET is_deleted = 1, updated_at = datetime('now') WHERE id = ? AND is_deleted = 0",
            (receipt_id,),
        )
        if cur.rowcount == 0:
            # 없는 ID이거나 이미 삭제됨
            raise HTTPException(status_code=404, detail="receipt not found or already deleted")
        return {"status": "ok", "receipt_id": receipt_id, "deleted": True}