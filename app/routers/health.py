# app/routers/health.py
from fastapi import APIRouter
from app.db.util import get_conn  # ✅ util.py에서 가져옴

router = APIRouter()

@router.get("/health")
def health_check():
    try:
        conn = get_conn()  # ✅ util.py 함수 사용
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "OK", "db": "Connected"}
    except Exception as e:
        return {"status": "Error", "db_error": str(e)}