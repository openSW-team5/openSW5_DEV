# app/routers/exports.py
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from datetime import datetime
import csv
import io

from app.db.util import get_conn
from app.services.auth import require_user_id  # 세션에서 user_id 확인

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/receipts.csv")
def export_receipts_csv(request: Request):
    """
    로그인한 사용자의 영수증 + 품목을 CSV로 내보내기

    파일명 예시:
      smartledger_receipts_2025-12-09.csv
    컬럼 헤더(엑셀에서 보이는 이름):
      영수증ID, 날짜, 상호명, 상태, 품목명, 수량, 단가, 금액, 총합계
    """
    user_id = require_user_id(request)

    today_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"smartledger_receipts_{today_str}.csv"

    def iter_rows():
        # StringIO 에 쓰고 조금씩 스트리밍
        output = io.StringIO()
        writer = csv.writer(output)

        # 엑셀 한글 깨짐 방지용 BOM
        output.write("\ufeff")

        # 👉 사용자 친화적인 한글 헤더
        writer.writerow([
            "영수증ID",
            "날짜",
            "상호명",
            "상태",
            "품목명",
            "수량",
            "단가",
            "금액",
            "총합계",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        with get_conn() as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT
                  r.id                AS receipt_id,
                  r.purchased_at      AS date,
                  r.merchant          AS merchant,
                  r.status            AS status,
                  ri.name             AS item_name,
                  ri.qty              AS qty,
                  ri.price            AS price,
                  (ri.qty * ri.price) AS subtotal,
                  r.total             AS receipt_total
                FROM receipts r
                JOIN receipt_items ri ON ri.receipt_id = r.id
                WHERE r.user_id    = ?
                  AND r.is_deleted = 0
                  AND r.status     = 'CONFIRMED'
                ORDER BY r.purchased_at ASC, r.id ASC, ri.id ASC
                """,
                (user_id,),
            )

            for row in rows:
                writer.writerow([
                    row["receipt_id"],
                    row["date"],
                    row["merchant"],
                    row["status"],
                    row["item_name"],
                    row["qty"],
                    row["price"],
                    row["subtotal"],
                    row["receipt_total"],
                ])
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

    return StreamingResponse(
        iter_rows(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )