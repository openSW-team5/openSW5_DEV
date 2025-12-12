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
from app.services.session import create_session_token, COOKIE_NAME, DEBUG

router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

PBKDF2_ALG = "pbkdf2_sha256"
PBKDF2_ITER = int(os.getenv("PWD_ITERATIONS", "240000"))
PBKDF2_SALT_BYTES = 16
PBKDF2_HASH_BYTES = 32


def _hash_password(plain: str) -> str:
    if not isinstance(plain, str) or len(plain) < 8:
        raise ValueError("password too short")
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
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


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=50)
    email: Optional[str] = Field(default=None, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    birthdate: Optional[str] = None

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
        if not v:
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
        datetime.strptime(v, "%Y-%m-%d")
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


def _exists_username(cur: sqlite3.Cursor, username: str) -> bool:
    return bool(cur.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone())


def _exists_email(cur: sqlite3.Cursor, email: str) -> bool:
    if not email:
        return False
    return bool(cur.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone())


def _redirect_if_logged_in(request: Request) -> Optional[RedirectResponse]:
    """로그인 상태면 login/register 접근을 막고 무조건 /dashboard로 보냄"""
    if getattr(request.state, "user_id", None):
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return None


# ==========================
#   페이지 렌더 (GET)
# ==========================
@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    r = _redirect_if_logged_in(request)
    if r:
        return r

    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    r = _redirect_if_logged_in(request)
    if r:
        return r

    return templates.TemplateResponse("login.html", {"request": request, "error": None})


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
    r = _redirect_if_logged_in(request)
    if r:
        return r

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
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": f"입력값 오류: {e}"},
            status_code=400,
        )

    try:
        pw_hash = _hash_password(reg.password)
    except ValueError as e:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": str(e)},
            status_code=400,
        )

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
    r = _redirect_if_logged_in(request)
    if r:
        return r

    u = username.strip()

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, name, password_hash FROM users WHERE username = ?",
            (u,),
        ).fetchone()

    if not row or not _verify_password(password, row["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "아이디 또는 비밀번호가 올바르지 않습니다."},
            status_code=401,
        )

    _ = LoginOut(user_id=row["id"], username=row["username"], name=row["name"])
    token = create_session_token(row["id"])

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=not DEBUG,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )
    return response


# ==========================
#   마이페이지
# ==========================
@router.get("/user", response_class=HTMLResponse)
async def user_page(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)

    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, username, name, email, phone, birthdate, created_at
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

    if not row:
        resp = RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)
        resp.delete_cookie(key=COOKIE_NAME, path="/")
        return resp

    return templates.TemplateResponse("pages/user.html", {"request": request, "user": dict(row)})


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)

    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    user = dict(row) if row else None
    return templates.TemplateResponse(
        "pages/notifications.html",
        {"request": request, "title": "알림", "user": user},
    )


# ==========================
#   로그아웃
# ==========================
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/users/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return response


@router.get("/me-test")
def me_test(request: Request):
    return {"user_id": getattr(request.state, "user_id", None)}