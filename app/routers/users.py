# app/routers/users.py
from fastapi import APIRouter, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import os
import sqlite3
import secrets
import hashlib
import hmac

from app.db.util import get_conn
from app.services.session import create_session_token, COOKIE_NAME, DEBUG  # ✅ 세션 유틸

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

# ==========================
#   비밀번호 해시 유틸
# ==========================
PBKDF2_ALG = "pbkdf2_sha256"
PBKDF2_ITER = int(os.getenv("PWD_ITERATIONS", "240000"))  # 배포 시 더 크게 잡아도 됨
PBKDF2_SALT_BYTES = 16
PBKDF2_HASH_BYTES = 32


def _hash_password(plain: str) -> str:
    if not isinstance(plain, str) or len(plain) < 8:
        raise ValueError("password too short")
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    # ✅ 오타 수정: pbkdfdf2_hmac → pbkdf2_hmac
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        plain.encode("utf-8"),
        salt,
        PBKDF2_ITER,
        dklen=PBKDF2_HASH_BYTES,
    )
    return f"{PBKDF2_ALG}${PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def _verify_password(plain: str, stored: str) -> bool:
    try:
        alg, iter_s, salt_hex, hash_hex = stored.split("$", 3)
        if alg != PBKDF2_ALG:
            return False
        iters = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            plain.encode("utf-8"),
            salt,
            iters,
            dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ==========================
#   내부 검증용 모델
# ==========================
class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=50)
    email: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    birthdate: Optional[str] = None  # 'YYYY-MM-DD'

    @field_validator("username")
    @classmethod
    def _v_username(cls, v: str) -> str:
        v = v.strip()
        if not v.isascii():
            raise ValueError("username must be ASCII")
        return v

    @field_validator("email")
    @classmethod
    def _v_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()

        if not v:  # 빈 문자열이면 None으로 처리
            return None
        if "@" not in v or "." not in v:
            raise ValueError("invalid email format")
        return v

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v

    @field_validator("birthdate")
    @classmethod
    def _v_birthdate(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return v
        datetime.strptime(v, "%Y-%m-%d")  # 형식 오류 시 ValueError
        return v


class RegisterOut(BaseModel):
    id: int
    username: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    birthdate: Optional[str] = None
    created_at: Optional[str] = None


class LoginOut(BaseModel):
    user_id: int
    username: str
    name: str


# ==========================
#   DB 헬퍼
# ==========================
def _exists_username(cur: sqlite3.Cursor, username: str) -> bool:
    return bool(cur.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone())


def _exists_email(cur: sqlite3.Cursor, email: str) -> bool:
    if not email:
        return False
    return bool(cur.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone())


# ==========================
#   페이지 렌더 (GET)
# ==========================

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None},
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None},
    )


# ==========================
#   회원가입 처리 (POST)
# ==========================

@router.post("/register", response_class=HTMLResponse)
def register_user_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    birthdate: Optional[str] = Form(None),
):
    # 1) Pydantic으로 1차 검증
    try:
        reg = RegisterIn(
            username=username,
            password=password,
            name=name,
            email=email,
            phone=phone,
            birthdate=birthdate,
        )
    except Exception as e:
        # 입력값 유효성 에러 → 같은 페이지에 에러 표시
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": f"입력값 오류: {e}"},
            status_code=400,
        )

    # 2) 비밀번호 해시
    try:
        pw_hash = _hash_password(reg.password)
    except ValueError as e:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": str(e)},
            status_code=400,
        )

    # 3) DB 저장
    with get_conn() as conn:
        cur = conn.cursor()

        if _exists_username(cur, reg.username):
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "이미 사용 중인 아이디입니다."},
                status_code=400,
            )
        if reg.email and _exists_email(cur, reg.email):
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": "이미 등록된 이메일입니다."},
                status_code=400,
            )

        cur.execute(
            """
            INSERT INTO users (username, password_hash, name, email, phone, birthdate)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                reg.username.strip(),
                pw_hash,
                reg.name.strip(),
                reg.email.strip() if reg.email else None,
                reg.phone.strip() if reg.phone else None,
                reg.birthdate,
            ),
        )
        user_id = cur.lastrowid
        row = cur.execute(
            "SELECT id, username, name, email, phone, birthdate, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    # 필요하면 여기서 RegisterOut 써서 로그 남길 수 있음
    _ = RegisterOut(
        id=row["id"],
        username=row["username"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        birthdate=row["birthdate"],
        created_at=row["created_at"],
    )

    # 가입 성공 → 로그인 페이지로 리다이렉트
    return RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)


# ==========================
#   로그인 처리 (POST) + 세션
# ==========================

@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    u = username.strip()

    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, username, name, password_hash FROM users WHERE username = ?",
            (u,),
        ).fetchone()

    if not row or not _verify_password(password, row["password_hash"]):
        # 인증 실패 → 다시 로그인 페이지 렌더 + 에러 메시지
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "아이디 또는 비밀번호가 올바르지 않습니다."},
            status_code=401,
        )

    # 로그인 성공 → 세션 토큰 발급
    _ = LoginOut(user_id=row["id"], username=row["username"], name=row["name"])
    token = create_session_token(row["id"])

    # 대시보드로 이동 (원하면 "/"로 바꿔도 됨)
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not DEBUG,          # DEBUG=true면 secure=False → 로컬에서 쿠키 저장됨
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7일
        path="/",                  # 모든 경로에서 쿠키 전송    
    )
    return response


# ==========================
#   마이페이지
# ==========================

@router.get("/user", response_class=HTMLResponse)
async def user_page(request: Request):

    return templates.TemplateResponse("pages/user.html", {"request": request})

    # 세션에서 user_id 가져오기
    user_id = getattr(request.state, "user_id", None)

    # 로그인 안 되어 있으면 로그인 페이지로 보내기
    if not user_id:
        return RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)

    # 로그인 된 경우 → DB에서 현재 유저 정보 가져오기
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            """
            SELECT id, username, name, email, phone, birthdate, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if not row:
        # 이례적 상황(세션은 있는데 유저가 없음) → 강제 로그아웃 후 다시 로그인 유도
        resp = RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)
        resp.delete_cookie(COOKIE_NAME)
        return resp

    user = {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "email": row["email"],
        "phone": row["phone"],
        "birthdate": row["birthdate"],
        "created_at": row["created_at"],
    }

    return templates.TemplateResponse(
        "pages/user.html",
        {
            "request": request,
            "user": user,
        },
    )



@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    user_id = getattr(request.state, "user_id", None)

    if not user_id:
        return RedirectResponse("/users/login", status_code=303)

    with get_conn() as conn:
        alerts = conn.execute(
            """
            SELECT type, message, created_at
            FROM alerts
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()

    return templates.TemplateResponse(
        "pages/notifications.html",
        {
            "request": request,
            "title": "알림",
            "alerts": alerts,
        },
    )


# ==========================
#   로그아웃
# ==========================

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",     # ✅ 로그인 때와 동일하게 명시
    )
    return response

@router.get("/me-test")
def me_test(request: Request):
    return {"user_id": getattr(request.state, "user_id", None)}


