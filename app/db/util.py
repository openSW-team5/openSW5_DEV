# app/db/util.py
import sqlite3
from contextlib import contextmanager

DB_PATH = "app/db/ledger.db"


@contextmanager
def get_conn():
    """
    SQLite connection context manager
    - check_same_thread=False: FastAPI/uvicorn 환경에서 안전성 ↑
    - row_factory=sqlite3.Row: dict처럼 접근 가능
    - foreign_keys ON
    - 자동 commit / rollback / close
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()