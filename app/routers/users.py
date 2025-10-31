# app/routers/users.py
from fastapi import APIRouter, HTTPException
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

@router.post("/register", response_model=RegisterOut)
def register_user(payload: RegisterIn):
    username = payload.username.strip()
    name = payload.name.strip()
    email = payload.email.strip() if payload.email else None
    phone = payload.phone.strip() if payload.phone else None
    birthdate = payload.birthdate

    pw_hash = _hash_password(payload.password)

    with get_conn() as conn:
        cur = conn.cursor()
        if _exists_username(cur, username):
            raise HTTPException(status_code=409, detail="username already exists")
        if email and _exists_email(cur, email):
            raise HTTPException(status_code=409, detail="email already exists")

        cur.execute(
            """
            INSERT INTO users (username, password_hash, name, email, phone, birthdate)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (username, pw_hash, name, email, phone, birthdate),
        )
        user_id = cur.lastrowid
        row = cur.execute(
            "SELECT id, username, name, email, phone, birthdate, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

    return RegisterOut(
        id=row["id"],
        username=row["username"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        birthdate=row["birthdate"],
        created_at=row["created_at"],
    )

@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn):
    username = payload.username.strip()
    with get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT id, username, name, password_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if not row or not _verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=401, detail="invalid credentials")

        return LoginOut(user_id=row["id"], username=row["username"], name=row["name"])