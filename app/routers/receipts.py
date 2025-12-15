# app/routers/receipts.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Path, Request, Query
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal, Any
from datetime import datetime
import os
import sqlite3
import logging
import json
from uuid import uuid4

from app.services.parse_ocr import parse_receipt_bytes
from app.services.auth import require_user_id
from app.services.alert_service import (
    check_overspend_alert,
    check_daily_overspend_alert,
    check_fixed_cost_alert,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

router = APIRouter(prefix="/receipts", tags=["receipts"])
templates = Jinja2Templates(directory="app/templates")

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "5"))

ALLOWED_MIMES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/heic",
    "image/heif",
    "application/octet-stream",
}

logger = logging.getLogger(__name__)


# ---------------------------
# Draft storage (SQLite)
# ---------------------------
def _ensure_receipt_drafts_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS receipt_drafts (
            draft_id   TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            ocr_raw    TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
        """
    )


def _commit_if_possible(conn: sqlite3.Connection) -> None:
    # get_conn()이 autocommit일 수도 있지만, 안전하게 커밋 시도
    try:
        conn.commit()
    except Exception:
        pass


def _row_get(row: Any, key: str, default=None):
    # sqlite3.Row / dict / tuple 모두 대비
    if row is None:
        return default
    try:
        return row[key]
    except Exception:
        if isinstance(row, dict):
            return row.get(key, default)
        return default


def _save_draft(conn: sqlite3.Connection, user_id: int, ocr_json: dict) -> str:
    draft_id = str(uuid4())
    _ensure_receipt_drafts_table(conn)

    conn.execute(
        """
        INSERT INTO receipt_drafts (draft_id, user_id, ocr_raw)
        VALUES (?, ?, ?)
        """,
        (draft_id, user_id, json.dumps(ocr_json, ensure_ascii=False)),
    )
    _commit_if_possible(conn)
    return draft_id


def _load_draft(conn: sqlite3.Connection, user_id: int, draft_id: str) -> dict:
    _ensure_receipt_drafts_table(conn)

    row = conn.execute(
        """
        SELECT draft_id, user_id, ocr_raw, created_at
        FROM receipt_drafts
        WHERE draft_id = ?
        """,
        (draft_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="draft not found")

    db_user_id = _row_get(row, "user_id")
    if db_user_id != user_id:
        raise HTTPException(status_code=403, detail="forbidden")

    raw_text = _row_get(row, "ocr_raw")
    try:
        return json.loads(raw_text)
    except Exception:
        raise HTTPException(status_code=500, detail="draft corrupted")


def _delete_draft(conn: sqlite3.Connection, user_id: int, draft_id: str) -> None:
    _ensure_receipt_drafts_table(conn)

    conn.execute(
        "DELETE FROM receipt_drafts WHERE draft_id = ? AND user_id = ?",
        (draft_id, user_id),
    )
    _commit_if_possible(conn)


# ---------- Schemas ----------
class ReceiptItemIn(BaseModel):
    name: str
    qty: int = Field(gt=0)
    price: int = Field(ge=0)
    category: Optional[str] = None


class ReceiptConfirmIn(BaseModel):
    user_id: Optional[int] = None
    merchant: str
    purchased_at: str
    items: List[ReceiptItemIn]
    total: int = Field(ge=0)
    status: Literal["PENDING", "CONFIRMED"] = "CONFIRMED"

    type: Literal["expense", "income", "transfer"] = "expense"
    category: Optional[str] = None
    image_path: Optional[str] = None

    draft_id: Optional[str] = None

    @field_validator("purchased_at")
    @classmethod
    def _v_date(cls, v: str) -> str:
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ]
        for fmt in formats:
            try:
                datetime.strptime(v, fmt)
                return v
            except ValueError:
                continue
        raise ValueError("purchased_at must be YYYY-MM-DD or YYYY-MM-DD HH:MM(:SS) or ISO8601")


class ReceiptUpdateIn(BaseModel):
    merchant: str
    purchased_at: str
    items: List[ReceiptItemIn]
    total: int = Field(ge=0)
    status: Literal["PENDING", "CONFIRMED"] = "CONFIRMED"

    type: Literal["expense", "income", "transfer"] = "expense"
    category: Optional[str] = None
    image_path: Optional[str] = None

    @field_validator("purchased_at")
    @classmethod
    def _v_date(cls, v: str) -> str:
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ]
        for fmt in formats:
            try:
                datetime.strptime(v, fmt)
                return v
            except ValueError:
                continue
        raise ValueError("purchased_at must be YYYY-MM-DD or YYYY-MM-DD HH:MM(:SS) or ISO8601")


class ReceiptRow(BaseModel):
    id: int
    user_id: int
    merchant: str
    total: int
    purchased_at: str
    status: Literal["PENDING", "CONFIRMED"]
    type: Literal["expense", "income", "transfer"] = "expense"
    category: Optional[str] = None
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
    type: Literal["expense", "income", "transfer"] = "expense"
    category: Optional[str] = None
    image_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items: List[ReceiptDetailItem]


# ---------- Endpoints ----------
@router.get("", response_model=dict)
def list_receipts(
    request: Request,
    limit: int = 50,
    offset: int = 0,
):
    user_id = require_user_id(request)

    from app.db.util import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, merchant, total, purchased_at, status, category, image_path, created_at
            FROM receipts
            WHERE is_deleted = 0
              AND user_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()

        data = [
            ReceiptRow(
                id=r["id"],
                user_id=r["user_id"],
                merchant=r["merchant"],
                total=r["total"],
                purchased_at=r["purchased_at"],
                status=r["status"],
                type="expense",
                category=r["category"],
                image_path=r["image_path"],
                created_at=r["created_at"],
            ).model_dump()
            for r in rows
        ]
        return {"status": "ok", "count": len(data), "data": data}


@router.get("/{receipt_id}", response_model=dict)
def get_receipt_detail(
    request: Request,
    receipt_id: int = Path(..., ge=1),
):
    user_id = require_user_id(request)

    from app.db.util import get_conn

    with get_conn() as conn:
        r = conn.execute(
            """
            SELECT id, user_id, merchant, total, purchased_at, status,
                   category, image_path, created_at, updated_at, is_deleted
            FROM receipts
            WHERE id = ?
            """,
            (receipt_id,),
        ).fetchone()

        if (not r) or (r["is_deleted"] == 1) or (r["user_id"] != user_id):
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
            type="expense",
            category=r["category"],
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


# ✅ 핵심: 기존 경로 /receipts/confirm 에서 draft_id 쿼리로 주입
@router.get("/confirm")
def confirm_page(
    request: Request,
    draft_id: Optional[str] = Query(default=None),
):
    """
    /receipts/confirm?draft_id=... 로 들어오면
    DB에서 draft를 읽어서 템플릿에 window.__OCR_RAW__ 형태로 주입할 수 있게 내려준다.
    """
    user_id = require_user_id(request)

    ocr_raw = {}
    ocr_raw_json = "{}"
    did = draft_id

    if draft_id:
        from app.db.util import get_conn
        with get_conn() as conn:
            ocr_raw = _load_draft(conn, user_id, draft_id)
        ocr_raw_json = json.dumps(ocr_raw, ensure_ascii=False)
    else:
        logger.warning("[receipt_confirm] draft_id not provided -> empty OCR")

    return templates.TemplateResponse(
        "pages/receipt_confirm.html",
        {
            "request": request,
            "title": "영수증 확인",
            "draft_id": did,
            "ocr_raw": ocr_raw,
            "ocr_raw_json": ocr_raw_json,
        },
    )


# (옵션) /confirm-draft/{draft_id}도 유지
@router.get("/confirm-draft/{draft_id}")
def confirm_draft_page(request: Request, draft_id: str):
    user_id = require_user_id(request)
    from app.db.util import get_conn
    with get_conn() as conn:
        ocr_raw = _load_draft(conn, user_id, draft_id)

    ocr_raw_json = json.dumps(ocr_raw, ensure_ascii=False)

    return templates.TemplateResponse(
        "pages/receipt_confirm.html",
        {
            "request": request,
            "title": "영수증 확인",
            "draft_id": draft_id,
            "ocr_raw": ocr_raw,
            "ocr_raw_json": ocr_raw_json,
        },
    )


@router.post("/upload", response_model=dict)
async def upload_receipt(
    request: Request,
    file: UploadFile = File(...),
):
    user_id = require_user_id(request)

    content_type = (file.content_type or "").lower().strip()
    filename = file.filename or "receipt.jpg"
    ext = os.path.splitext(filename)[1].lower()

    if not content_type:
        if ext in [".jpg", ".jpeg"]:
            content_type = "image/jpeg"
        elif ext == ".png":
            content_type = "image/png"
        elif ext in [".heic", ".heif"]:
            content_type = "image/heic"
        else:
            content_type = "application/octet-stream"

    if content_type not in ALLOWED_MIMES:
        raise HTTPException(status_code=400, detail=f"허용되지 않은 파일 형식: {content_type}")

    raw = await file.read()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(status_code=400, detail=f"파일이 너무 큽니다. 최대 {MAX_UPLOAD_MB}MB 허용")

    if not raw:
        raise HTTPException(status_code=400, detail="업로드된 파일이 비어있습니다.")

    try:
        ocr_json = parse_receipt_bytes(
            file_bytes=raw,
            filename=filename,
            content_type=content_type,
        )

        from app.db.util import get_conn
        with get_conn() as conn:
            draft_id = _save_draft(conn, user_id, ocr_json)

        # ✅ 기존 네 앱이 /receipts/confirm 으로 이동하는 구조라면, 여기로 맞춰주는 게 제일 확실함
        confirm_url = f"/receipts/confirm?draft_id={draft_id}"

        return JSONResponse(
            {
                "status": "ok",
                "draft_id": draft_id,
                "confirm_url": confirm_url,
                "ocr_raw": ocr_json,
            }
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"OCR 입력 오류: {e}")
    except Exception as e:
        logger.exception("OCR 처리 중 예외 발생: %s", e)
        raise HTTPException(status_code=500, detail=f"OCR 처리 실패(서버): {e}")


@router.post("/confirm", response_model=dict)
def confirm_receipt(
    request: Request,
    payload: ReceiptConfirmIn,
):
    user_id = require_user_id(request)

    if not payload.items:
        raise HTTPException(status_code=400, detail="items 최소 1개 필요")

    calc_total = sum(it.qty * it.price for it in payload.items)

    from app.db.util import get_conn

    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO receipts (user_id, merchant, total, purchased_at, status, category, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    payload.merchant.strip(),
                    calc_total,
                    payload.purchased_at.strip(),
                    payload.status,
                    payload.category.strip() if payload.category else None,
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

            check_overspend_alert(conn, user_id, receipt_id)
            check_daily_overspend_alert(conn, user_id, receipt_id)
            check_fixed_cost_alert(conn, user_id, receipt_id)

            if payload.draft_id:
                try:
                    _delete_draft(conn, user_id, payload.draft_id)
                except Exception:
                    logger.warning("draft delete failed: %s", payload.draft_id)

            return {
                "status": "ok",
                "receipt_id": receipt_id,
                "saved_total": calc_total,
                "items_saved": len(payload.items),
            }

    except sqlite3.IntegrityError as e:
        if "uq_receipt_dedup" in str(e) or "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=409, detail="이미 저장된 영수증일 수 있어요(중복 가능성).")
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB 저장 실패: {e}")


@router.post("/{receipt_id}/update", response_model=dict)
def update_receipt(
    request: Request,
    receipt_id: int = Path(..., ge=1),
    payload: ReceiptUpdateIn = ...,
):
    user_id = require_user_id(request)

    if not payload.items:
        raise HTTPException(status_code=400, detail="items 최소 1개 필요")

    calc_total = sum(it.qty * it.price for it in payload.items)

    from app.db.util import get_conn

    with get_conn() as conn:
        cur = conn.cursor()

        row = cur.execute(
            "SELECT id, user_id, is_deleted FROM receipts WHERE id = ?",
            (receipt_id,),
        ).fetchone()
        if (not row) or (row["is_deleted"] == 1) or (row["user_id"] != user_id):
            raise HTTPException(status_code=404, detail="receipt not found")

        cur.execute(
            """
            UPDATE receipts
               SET merchant = ?,
                   total = ?,
                   purchased_at = ?,
                   status = ?,
                   category = ?,
                   image_path = ?,
                   updated_at = datetime('now')
             WHERE id = ? AND is_deleted = 0
            """,
            (
                payload.merchant.strip(),
                calc_total,
                payload.purchased_at.strip(),
                payload.status,
                payload.category.strip() if payload.category else None,
                payload.image_path.strip() if payload.image_path else None,
                receipt_id,
            ),
        )

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

        check_overspend_alert(conn, user_id, receipt_id)
        check_daily_overspend_alert(conn, user_id, receipt_id)
        check_fixed_cost_alert(conn, user_id, receipt_id)

        return {
            "status": "ok",
            "receipt_id": receipt_id,
            "saved_total": calc_total,
            "items_saved": len(payload.items),
        }


@router.post("/{receipt_id}/delete", response_model=dict)
def soft_delete_receipt(
    request: Request,
    receipt_id: int = Path(..., ge=1),
):
    user_id = require_user_id(request)

    from app.db.util import get_conn

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE receipts
               SET is_deleted = 1,
                   updated_at = datetime('now')
             WHERE id = ?
               AND user_id = ?
               AND is_deleted = 0
            """,
            (receipt_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="receipt not found or already deleted")
        return {"status": "ok", "receipt_id": receipt_id, "deleted": True}