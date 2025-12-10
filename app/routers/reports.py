# app/routers/reports.py
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
def card_settings_page(request: Request):
    """카드 설정 페이지"""
    return templates.TemplateResponse(
        "pages/card_settings.html",
        {"request": request, "title": "카드 설정"}
    )

@router.get("/monthly", response_model=dict)
def monthly_report(month: Optional[str] = Query(None, description="YYYY-MM (예: 2025-09)")):
    """
    월별 합계/카테고리 합계
    - month가 없으면: 최근 6개월치 한꺼번에 반환
    - month가 있으면: 해당 월만 상세 반환
    """
    from app.db.util import get_conn
    with get_conn() as conn:
        if month:
            total = conn.execute(
                "SELECT month, month_total FROM v_month_totals WHERE month = ?",
                (month,),
            ).fetchone()
            cats = conn.execute(
                """
                SELECT month, category, category_total
                FROM v_month_category_totals
                WHERE month = ?
                ORDER BY category_total DESC
                """,
                (month,),
            ).fetchall()
            return {
                "status": "ok",
                "month": month,
                "total": (total["month_total"] if total else 0),
                "by_category": [
                    {"category": r["category"], "total": r["category_total"]} for r in cats
                ],
            }
        else:
            totals = conn.execute(
                """
                SELECT month, month_total
                FROM v_month_totals
                ORDER BY month DESC
                LIMIT 6
                """
            ).fetchall()
            months = [r["month"] for r in totals]
            cats = conn.execute(
                """
                SELECT month, category, category_total
                FROM v_month_category_totals
                WHERE month IN ({})
                ORDER BY month DESC, category_total DESC
                """.format(",".join("?"*len(months))),
                months,
            ).fetchall() if months else []

            by_month = {m: {"total": 0, "by_category": []} for m in months}
            for r in totals:
                by_month[r["month"]]["total"] = r["month_total"]
            for r in cats:
                by_month[r["month"]]["by_category"].append({
                    "category": r["category"], "total": r["category_total"]
                })

            return {"status": "ok", "months": by_month}