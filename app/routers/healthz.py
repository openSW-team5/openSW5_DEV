# app/routers/health.py
from fastapi import APIRouter
import sqlite3

router = APIRouter()

def get_connection():
    return sqlite3.connect("app/db/ledger.db")

@router.get("/healthz")
def health_check():
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "OK", "db": "Connected"}
    except Exception as e:
        return {"status": "Error", "db_error": str(e)}
