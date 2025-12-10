# app/services/auth.py
from fastapi import Request, HTTPException, status
from typing import Optional


def require_user_id(request: Request) -> int:
    """
    세션에서 user_id를 꺼내고,
    없으면 401 에러를 던지는 공통 헬퍼.
    """
    user_id: Optional[int] = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )
    return int(user_id)