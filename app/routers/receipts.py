from fastapi import APIRouter

# 라우터 객체 생성
router = APIRouter(prefix="/receipts", tags=["receipts"])

@router.get("")
def list_receipts():
    return {"status": "ok", "data": []}