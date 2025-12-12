# app/services/auth.py
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse
from urllib.parse import quote
from typing import Optional, Union


def require_user_id(request: Request) -> int:
    """
    ✅ API(JSON)용
    세션에서 user_id를 꺼내고,
    없으면 401 에러를 던짐.
    """
    user_id: Optional[int] = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인이 필요합니다.",
        )
    return int(user_id)


def require_login_page(request: Request) -> Union[int, RedirectResponse]:
    """
    ✅ HTML 페이지용(선택)
    로그인 안 되어 있으면 /users/login?next=... 로 리다이렉트
    """
    user_id: Optional[int] = getattr(request.state, "user_id", None)
    if not user_id:
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
        next_q = quote(next_path, safe="/?=&")
        return RedirectResponse(
            url=f"/users/login?next={next_q}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return int(user_id)