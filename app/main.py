# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3

app = FastAPI(title="OpenSW5")

# 정적/템플릿 경로는 app/ 하위로 고정
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# SQLite 연결 함수
def get_connection():
    return sqlite3.connect("app/db/ledger.db")

# 기본 페이지 (Jinja2 템플릿)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Home", "msg": "Hello FastAPI + Jinja2!"}
    )

# ✅ DB 연결 확인용 라우트
@app.get("/healthz")
def health_check():
    try:
        conn = get_connection()
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "OK", "db": "Connected"}
    except Exception as e:
        return {"status": "Error", "db_error": str(e)}
