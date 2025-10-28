# app/db/init_db.py
import sqlite3

def init_db():
    db_path = "app/db/ledger.db"      # 생성할 DB 파일 경로
    schema_path = "app/db/schema.sql" # 방금 만든 스키마 파일 경로

    conn = sqlite3.connect(db_path)
    with open(schema_path, "r", encoding="utf-8") as f:
        sql_script = f.read()
        conn.executescript(sql_script)
    conn.close()
    print("✅ DB initialized successfully at", db_path)

if __name__ == "__main__":
    init_db()
