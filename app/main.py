# app/main.py
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import health, receipts, users, reports, exports
# ✅ 세션 유틸 임포트
from app.services.session import verify_session_token, COOKIE_NAME

app = FastAPI(title="OpenSW5")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# ✅ 모든 요청에서 user_id를 request.state에 심어주는 미들웨어
@app.middleware("http")
async def add_session_to_request(request: Request, call_next):
    token = request.cookies.get(COOKIE_NAME)
    session_data = verify_session_token(token) if token else None

    if session_data:
        request.state.user_id = session_data.get("uid")
    else:
        request.state.user_id = None

    response = await call_next(request)
    return response

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        "splash.html",
        {"request": request}
    )

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "pages/dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            # 나중에 템플릿에서 로그인 여부를 쓰고 싶으면 이 값 사용 가능
            "user_id": getattr(request.state, "user_id", None),
        },
    )

# 나머지 페이지 라우트들 그대로 ...
@app.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request):
    return templates.TemplateResponse(
        "pages/transactions.html",
        {"request": request, "title": "거래내역"}
    )

@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request):
    return templates.TemplateResponse(
        "pages/search.html",
        {"request": request, "title": "검색"}
    )

@app.get("/notification-settings", response_class=HTMLResponse)
def notification_settings_page(request: Request):
    return templates.TemplateResponse(
        "pages/notification_settings.html",
        {"request": request, "title": "알림설정"}
    )

@app.get("/data-export", response_class=HTMLResponse)
def data_export_page(request: Request):
    return templates.TemplateResponse(
        "pages/data_export.html",
        {"request": request, "title": "데이터 내보내기"}
    )

@app.get("/category-edit", response_class=HTMLResponse)
def category_edit_page(request: Request):
    return templates.TemplateResponse(
        "pages/category_edit.html",
        {"request": request, "title": "카테고리 편집"}
    )

@app.get("/category-income", response_class=HTMLResponse)
def category_income_page(request: Request):
    return templates.TemplateResponse(
        "pages/category_income.html",
        {"request": request, "title": "카테고리 편집"}
    )

@app.get("/category-asset", response_class=HTMLResponse)
def category_asset_page(request: Request):
    return templates.TemplateResponse(
        "pages/category_asset.html",
        {"request": request, "title": "카테고리 편집"}
    )

@app.get("/receipts/confirm", response_class=HTMLResponse)
def receipt_confirm_page(request: Request):
    return templates.TemplateResponse(
        "pages/receipt_confirm.html",
        {"request": request, "title": "영수증 확인"}
    )

# ✅ 라우터 등록

app.include_router(health.router)
app.include_router(receipts.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(exports.router) 