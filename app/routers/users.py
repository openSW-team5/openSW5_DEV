# app/routers/users.py
from fastapi import APIRouter, Request, Form, status, HTTPException
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


router = APIRouter(prefix="/users", tags=["users"])
templates = Jinja2Templates(directory="app/templates")

PBKDF2_ALG = "pbkdf2_sha256"
PBKDF2_ITER = int(os.getenv("PWD_ITERATIONS", "240000"))  # 배포 시 충분히 크게
PBKDF2_SALT_BYTES = 16
PBKDF2_HASH_BYTES = 32

def _hash_password(plain: str) -> str:
    if not isinstance(plain, str) or len(plain) < 8:
        raise ValueError("password too short")
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, PBKDF2_ITER, dklen=PBKDF2_HASH_BYTES)
    return f"{PBKDF2_ALG}${PBKDF2_ITER}${salt.hex()}${dk.hex()}"

def _verify_password(plain: str, stored: str) -> bool:
    try:
        alg, iter_s, salt_hex, hash_hex = stored.split("$", 3)
        if alg != PBKDF2_ALG:
            return False
        iters = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iters, dklen=len(expected))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False

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
        if "@" not in v or "." not in v:  # 경량 검사
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
        datetime.strptime(v, "%Y-%m-%d")  # 형식오류 시 ValueError
        return v

class RegisterOut(BaseModel):
    id: int
    username: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    birthdate: Optional[str] = None
    created_at: Optional[str] = None

class LoginIn(BaseModel):
    username: str
    password: str

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

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register", response_model=RegisterOut)
def register_user_form(
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(...),
    email: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    birthdate: Optional[str] = Form(None),
):
    # ↓ 기존 register_user() 내부와 동일한 로직
    pw_hash = _hash_password(password)

    with get_conn() as conn:
        cur = conn.cursor()
        if _exists_username(cur, username.strip()):
            raise HTTPException(status_code=409, detail="username already exists")
        if email and _exists_email(cur, email.strip()):
            raise HTTPException(status_code=409, detail="email already exists")

        cur.execute(
            """
            INSERT INTO users (username, password_hash, name, email, phone, birthdate)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username.strip(), pw_hash, name.strip(),
             email.strip() if email else None,
             phone.strip() if phone else None,
             birthdate),
        )
        conn.commit()

    # 저장 후 홈으로 리다이렉트 (플래시용 쿼리 파라미터 추가)
    return RedirectResponse(url="/?registered=1", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # 단순히 로그인 폼 렌더링
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    u = username.strip()

    # DB 조회
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, username, name, password_hash FROM users WHERE username = ?",
            (u,),
        ).fetchone()

    # 인증 실패 → 같은 페이지에 에러 표시
    if not row or not _verify_password(password, row["password_hash"]):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "아이디 또는 비밀번호가 올바르지 않습니다."},
            status_code=401,
        )

    # 인증 성공 → 홈으로 리다이렉트 (세션/쿠키는 이후에 추가)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)