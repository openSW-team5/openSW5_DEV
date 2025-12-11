# app/routers/reports.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from app.db.util import get_conn
from app.services.auth import require_user_id  # ✅ 세션 기반 user_id

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
def card_settings_page(request: Request):
    """카드 설정 페이지"""
    return templates.TemplateResponse(
        "pages/card_settings.html",
        {"request": request, "title": "카드 설정"}
    )


# ---------- Pydantic Schemas (대시보드용) ----------

class CategorySummary(BaseModel):
    category: str
    amount: int
    ratio: float  # 전체 합 대비 비율 (0.0 ~ 1.0)


class RecentReceipt(BaseModel):
    id: int
    merchant: str
    total: int
    purchased_at: str
    status: str


class DashboardOverview(BaseModel):
    month: str              # "YYYY-MM"
    total: int              # 해당 월 총 지출
    categories: List[CategorySummary]
    recent: List[RecentReceipt]


# =========================
# 1. /reports/monthly (사용자별)
# =========================

@router.get("/monthly", response_model=dict)
def monthly_report(
    request: Request,
    month: Optional[str] = Query(
        None,
        description="YYYY-MM (예: 2025-09)"
    ),
):
    """
    로그인한 사용자 기준 월별 합계/카테고리 합계
    - month가 없으면: 최근 6개월치 한꺼번에 반환
    - month가 있으면: 해당 월만 상세 반환
    """
    user_id = require_user_id(request)

    with get_conn() as conn:
        cur = conn.cursor()

        if month:
            # 1) 해당 월 총합
            total = cur.execute(
                """
                SELECT
                  substr(purchased_at, 1, 7) AS month,
                  SUM(total) AS month_total
                FROM receipts
                WHERE user_id = ?
                  AND status = 'CONFIRMED'
                  AND is_deleted = 0
                  AND substr(purchased_at, 1, 7) = ?
                GROUP BY substr(purchased_at, 1, 7)
                """,
                (user_id, month),
            ).fetchone()

            # 2) 해당 월 카테고리별 합계
            cats = cur.execute(
                """
                SELECT
                  substr(r.purchased_at, 1, 7) AS month,
                  COALESCE(ri.category, '미분류') AS category,
                  SUM(ri.qty * ri.price) AS category_total
                FROM receipts r
                JOIN receipt_items ri ON ri.receipt_id = r.id
                WHERE r.user_id = ?
                  AND r.status = 'CONFIRMED'
                  AND r.is_deleted = 0
                  AND substr(r.purchased_at, 1, 7) = ?
                GROUP BY substr(r.purchased_at, 1, 7),
                         COALESCE(ri.category, '미분류')
                ORDER BY category_total DESC
                """,
                (user_id, month),
            ).fetchall()

            return {
                "status": "ok",
                "month": month,
                "total": (total["month_total"] if total else 0),
                "by_category": [
                    {"category": r["category"], "total": r["category_total"]}
                    for r in cats
                ],
            }

        # month가 없는 경우 → 최근 6개월
        totals = cur.execute(
            """
            SELECT
              substr(purchased_at, 1, 7) AS month,
              SUM(total) AS month_total
            FROM receipts
            WHERE user_id = ?
              AND status = 'CONFIRMED'
              AND is_deleted = 0
            GROUP BY substr(purchased_at, 1, 7)
            ORDER BY month DESC
            LIMIT 6
            """,
            (user_id,),
        ).fetchall()

        months = [r["month"] for r in totals]

        if months:
            cats = cur.execute(
                """
                SELECT
                  substr(r.purchased_at, 1, 7) AS month,
                  COALESCE(ri.category, '미분류') AS category,
                  SUM(ri.qty * ri.price) AS category_total
                FROM receipts r
                JOIN receipt_items ri ON ri.receipt_id = r.id
                WHERE r.user_id = ?
                  AND r.status = 'CONFIRMED'
                  AND r.is_deleted = 0
                  AND substr(r.purchased_at, 1, 7) IN ({})
                GROUP BY substr(r.purchased_at, 1, 7),
                         COALESCE(ri.category, '미분류')
                ORDER BY month DESC, category_total DESC
                """.format(",".join("?" * len(months))),
                (user_id, *months),
            ).fetchall()
        else:
            cats = []

        by_month = {m: {"total": 0, "by_category": []} for m in months}
        for r in totals:
            by_month[r["month"]]["total"] = r["month_total"]
        for r in cats:
            by_month[r["month"]]["by_category"].append(
                {
                    "category": r["category"],
                    "total": r["category_total"],
                }
            )

        return {"status": "ok", "months": by_month}


# =========================
# 2. /reports/overview (대시보드용, 사용자별)
# =========================

@router.get("/overview", response_model=dict)
def get_overview(
    request: Request,
    month: Optional[str] = Query(
        default=None,
        description="조회할 월 (YYYY-MM). 비우면 이번 달."
    ),
):
    """
    로그인한 사용자 기준 대시보드용 개요 데이터:
    - 해당 월 총 지출
    - 카테고리별 합계 + 비율
    - 최근 5건 영수증
    """
    user_id = require_user_id(request)

    # month 파라미터 없으면 현재 월로
    if not month:
        month = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        cur = conn.cursor()

        # 1) 해당 월 총 지출 (소프트 삭제 제외)
        row_total = cur.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS total
            FROM receipts
            WHERE user_id = ?
              AND status = 'CONFIRMED'
              AND is_deleted = 0
              AND substr(purchased_at, 1, 7) = ?
            """,
            (user_id, month),
        ).fetchone()
        month_total = row_total["total"] if row_total and row_total["total"] is not None else 0

        # 2) 카테고리별 합계
        rows_cat = cur.execute(
            """
            SELECT
              COALESCE(ri.category, '미분류') AS category,
              SUM(ri.qty * ri.price) AS amount
            FROM receipts r
            JOIN receipt_items ri ON ri.receipt_id = r.id
            WHERE r.user_id = ?
              AND r.status = 'CONFIRMED'
              AND r.is_deleted = 0
              AND substr(r.purchased_at, 1, 7) = ?
            GROUP BY COALESCE(ri.category, '미분류')
            ORDER BY amount DESC
            """,
            (user_id, month),
        ).fetchall()

        categories: List[CategorySummary] = []
        for r in rows_cat:
            amount = r["amount"] or 0
            ratio = (amount / month_total) if month_total > 0 else 0.0
            categories.append(
                CategorySummary(
                    category=r["category"],
                    amount=amount,
                    ratio=ratio,
                )
            )

        # 3) 최근 5건 영수증
        rows_recent = cur.execute(
            """
            SELECT
              id, merchant, total, purchased_at, status
            FROM receipts
            WHERE user_id = ?
              AND status = 'CONFIRMED'
              AND is_deleted = 0
              AND substr(purchased_at, 1, 7) = ?
            ORDER BY purchased_at DESC, id DESC
            LIMIT 5
            """,
            (user_id, month),
        ).fetchall()

        recent_list: List[RecentReceipt] = [
            RecentReceipt(
                id=r["id"],
                merchant=r["merchant"],
                total=r["total"],
                purchased_at=r["purchased_at"],
                status=r["status"],
            )
            for r in rows_recent
        ]

    overview = DashboardOverview(
        month=month,
        total=month_total,
        categories=categories,
        recent=recent_list,
    )

    return {
        "status": "ok",
        "data": overview.model_dump(),
    }