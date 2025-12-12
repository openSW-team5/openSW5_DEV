def check_overspend_alert(conn, user_id: int, receipt_id: int):
    r = conn.execute(
        """
        SELECT total, category
        FROM receipts
        WHERE id = ?
          AND is_deleted = 0
        """,
        (receipt_id,),
    ).fetchone()

    if not r or not r["category"]:
        return

    avg = conn.execute(
        """
        SELECT AVG(total)
        FROM receipts
        WHERE user_id = ?
          AND category = ?
          AND status = 'CONFIRMED'
          AND is_deleted = 0
          AND type = 'expense'
          AND purchased_at >= date('now', '-3 months')
          AND id != ?
        """,
        (user_id, r["category"], receipt_id),
    ).fetchone()[0]

    if avg and r["total"] > avg * 2.5:
        conn.execute(
            """
            INSERT INTO alerts (user_id, type, message, related_receipt_id)
            VALUES (?, 'anomaly', ?, ?)
            """,
            (
                user_id,
                f"{r['category']} 지출이 평소보다 큽니다 ({r['total']:,}원)",
                receipt_id,
            ),
        )

def check_daily_overspend_alert(conn, user_id: int, receipt_id: int):
    # 1) 영수증 날짜 가져오기
    r = conn.execute(
        """
        SELECT purchased_at
        FROM receipts
        WHERE id = ?
          AND is_deleted = 0
          AND status = 'CONFIRMED'
          AND type = 'expense'
        """,
        (receipt_id,),
    ).fetchone()

    if not r:
        return

    day = r["purchased_at"][:10]  # YYYY-MM-DD
    month = r["purchased_at"][:7] # YYYY-MM

    # 2) 해당 월 예산 합계
    budget_row = conn.execute(
        """
        SELECT SUM(amount) AS total_budget
        FROM budgets
        WHERE user_id = ?
          AND month = ?
        """,
        (user_id, month),
    ).fetchone()

    if not budget_row or not budget_row["total_budget"]:
        return

    monthly_budget = budget_row["total_budget"]

    # 3) 월 일수
    days_in_month = conn.execute(
        "SELECT strftime('%d', date(?, '+1 month', '-1 day'))",
        (month + "-01",),
    ).fetchone()[0]

    daily_target = monthly_budget / int(days_in_month)

    # 4) 해당 날짜 총 지출
    day_total = conn.execute(
        """
        SELECT SUM(total) AS day_total
        FROM receipts
        WHERE user_id = ?
          AND status = 'CONFIRMED'
          AND is_deleted = 0
          AND type = 'expense'
          AND substr(purchased_at, 1, 10) = ?
        """,
        (user_id, day),
    ).fetchone()["day_total"] or 0

    if day_total > daily_target * 1.5:
        conn.execute(
            """
            INSERT INTO alerts (user_id, type, message, related_receipt_id)
            VALUES (?, 'overspend', ?, ?)
            """,
            (
                user_id,
                f"{day} 하루 지출이 목표({int(daily_target):,}원)를 초과했습니다 "
                f"({int(day_total):,}원)",
                receipt_id,
            ),
        )


def check_fixed_cost_alert(conn, user_id: int, receipt_id: int):
    # 1️⃣ 기준 영수증 정보
    r = conn.execute(
        """
        SELECT merchant, total, purchased_at
        FROM receipts
        WHERE id = ?
          AND user_id = ?
          AND status = 'CONFIRMED'
          AND is_deleted = 0
          AND type = 'expense'
        """,
        (receipt_id, user_id),
    ).fetchone()

    if not r:
        return

    merchant = r["merchant"]
    total = r["total"]

    lower = total * 0.95
    upper = total * 1.05

    # 2️⃣ 최근 3~4개월 같은 상호 + 유사 금액
    rows = conn.execute(
        """
        SELECT DISTINCT substr(purchased_at, 1, 7) AS month
        FROM receipts
        WHERE user_id = ?
          AND merchant = ?
          AND total BETWEEN ? AND ?
          AND status = 'CONFIRMED'
          AND is_deleted = 0
          AND type = 'expense'
          AND purchased_at >= date('now', '-4 months')
        """,
        (user_id, merchant, lower, upper),
    ).fetchall()

    # 3️⃣ 서로 다른 월이 3개 이상이면 고정비
    if len(rows) >= 3:
        conn.execute(
            """
            INSERT INTO alerts (user_id, type, message, related_receipt_id)
            VALUES (?, 'fixed_detected', ?, ?)
            """,
            (
                user_id,
                f"정기 지출로 보이는 항목이 감지되었습니다 ({merchant})",
                receipt_id,
            ),
        )

def check_monthly_budget_alert(conn, user_id: int, receipt_id: int):
    r = conn.execute(
        """
        SELECT purchased_at
        FROM receipts
        WHERE id = ?
          AND status = 'CONFIRMED'
          AND is_deleted = 0
          AND type = 'expense'
        """,
        (receipt_id,),
    ).fetchone()

    if not r:
        return

    month = r["purchased_at"][:7]

    budget = conn.execute(
        """
        SELECT SUM(amount) AS total_budget
        FROM budgets
        WHERE user_id = ?
          AND month = ?
        """,
        (user_id, month),
    ).fetchone()["total_budget"]

    if not budget:
        return

    spent = conn.execute(
        """
        SELECT SUM(total) AS total_spent
        FROM receipts
        WHERE user_id = ?
          AND status = 'CONFIRMED'
          AND is_deleted = 0
          AND type = 'expense'
          AND substr(purchased_at, 1, 7) = ?
        """,
        (user_id, month),
    ).fetchone()["total_spent"] or 0

    if spent > budget:
        conn.execute(
            """
            INSERT INTO alerts (user_id, type, message)
            VALUES (?, 'budget_exceeded', ?)
            """,
            (
                user_id,
                f"{month} 월 예산을 초과했습니다 ({int(spent):,}원)",
            ),
        )
