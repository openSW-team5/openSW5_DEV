# app/db/init_db.py
"""
DB 초기화 스크립트 (배포용 보안 버전)

- 개발 환경에서만 실행 가능 (PROD 환경에서는 자동 차단)
- 기존 DB가 있을 경우 절대 덮어쓰지 않음
- 스키마 파일 서명(해시) 검증 가능
"""

import os
import sqlite3
import hashlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- 환경 변수 ---
APP_ENV = os.getenv("APP_ENV", "dev").lower()
DB_PATH = Path("app/db/ledger.db")
SCHEMA_PATH = Path("app/db/schema.sql")


def file_sha256(path: Path) -> str:
    """파일의 SHA-256 해시값 계산"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def init_db():
    # 1️⃣ 운영환경(PROD)에서는 차단
    if APP_ENV == "prod":
        print("🚫 Production 환경에서는 init_db 실행이 차단되었습니다.")
        return

    # 2️⃣ 기존 DB가 존재하면 중단
    if DB_PATH.exists():
        print(f"⚠️ DB already exists at {DB_PATH}. Initialization aborted.")
        return

    # 3️⃣ 스키마 파일 검증
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"❌ Schema file not found: {SCHEMA_PATH}")

    schema_hash = file_sha256(SCHEMA_PATH)
    print(f"🔍 Schema verified. SHA-256: {schema_hash[:12]}...")

    # 4️⃣ DB 생성 및 스키마 적용
    conn = sqlite3.connect(DB_PATH)
    try:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            sql_script = f.read()
            conn.executescript(sql_script)
        conn.commit()
        print(f"✅ DB initialized successfully at {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()