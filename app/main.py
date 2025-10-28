# app/main.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sqlite3
from app.routers import health  # ← API 라우터만 분리

app = FastAPI(title="OpenSW5")

# 정적/템플릿 경로는 app/ 하위로 고정
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# 기본 페이지 (Jinja2 템플릿)
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Home", "msg": "Hello FastAPI + Jinja2!"}
    )

app.include_router(health.router)
