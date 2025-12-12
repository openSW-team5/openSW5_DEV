# app/routers/alerts.py
from fastapi import APIRouter, Request, HTTPException
from app.services.auth import require_user_id
from app.db.util import get_conn

router = APIRouter(
    prefix="/users/alerts",
    tags=["alerts"],
)

# 🔹 알림 읽음 처리
@router.post("/{alert_id}/read")
def mark_alert_read(request: Request, alert_id: int):
    user_id = require_user_id(request)

    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE alerts
            SET is_read = 1
            WHERE id = ? AND user_id = ?
            """,
            (alert_id, user_id),
        )

        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="alert not found")

    return {"status": "ok", "alert_id": alert_id}


# 🔹 (추가) 전체 알림 읽음 처리
@router.post("/read-all")
def mark_all_alerts_read(request: Request):
    user_id = require_user_id(request)

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE alerts
            SET is_read = 1
            WHERE user_id = ?
              AND is_read = 0
            """,
            (user_id,),
        )

    return {"status": "ok", "message": "all alerts marked as read"}


@router.get("/unread-count")
def unread_alert_count(request: Request):
    user_id = require_user_id(request)

    with get_conn() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM alerts
            WHERE user_id = ? AND is_read = 0
            """,
            (user_id,),
        ).fetchone()[0]

    return {"count": count}

@router.post("/read-all")
def mark_all_alerts_read(request: Request):
    user_id = require_user_id(request)
    print("🟢 read-all called, user_id =", user_id)

    with get_conn() as conn:
        cur = conn.execute(
            """
            UPDATE alerts
            SET is_read = 1
            WHERE user_id = ?
              AND is_read = 0
            """,
            (user_id,),
        )
        print("🟢 rows updated =", cur.rowcount)

    return {"status": "ok", "updated": cur.rowcount}

