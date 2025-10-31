# app/main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ✅ 한 방식으로만 임포트
from app.routers import health, receipts, users, reports

app = FastAPI(title="OpenSW5")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Home", "msg": "Hello FastAPI + Jinja2!"}
    )

# ✅ 라우터 등록
app.include_router(health.router)
app.include_router(receipts.router)
app.include_router(users.router)
app.include_router(reports.router) 