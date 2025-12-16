# app/main.py
from dotenv import load_dotenv
load_dotenv()

from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import health, receipts, users, reports, exports, alerts
from app.services.session import verify_session_token, COOKIE_NAME

app = FastAPI(title="OpenSW5")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ✅ 로그인 필요 경로 prefix들 (라우터 포함)
PROTECTED_PREFIXES = (
    "/reports",   # ✅ 로그아웃이면 reports 접근 차단
    # "/exports", # 필요하면 여기도 같이 막기
)

# ✅ 로그인 필요 "단일 페이지" 경로들 (main.py에서 직접 만든 페이지들)
PROTECTED_PATHS = {
    "/dashboard",
    "/transactions",
    "/search",
    "/notification-settings",
    "/data-export",
    "/category-edit",
    "/category-income",
    "/category-asset",
    "/budget-settings",
    "/receipts/confirm",
}

def _is_protected(path: str) -> bool:
    return (path in PROTECTED_PATHS) or any(path.startswith(pfx) for pfx in PROTECTED_PREFIXES)


# ✅ next 만들기 유틸 (request 전체 path+query)
def _build_next(request: Request) -> str:
    next_path = request.url.path
    if request.url.query:
        next_path += "?" + request.url.query
    return quote(next_path, safe="/?=&")


# ✅ 모든 요청에서 user_id를 request.state에 심어주는 미들웨어 + prefix 가드 + no-store
@app.middleware("http")
async def add_session_to_request(request: Request, call_next):
    # ✅ static 파일은 캐시 헤더 건드리지 않음
    if request.url.path.startswith("/static"):
        return await call_next(request)

    token = request.cookies.get(COOKIE_NAME)
    session_data = verify_session_token(token) if token else None
    request.state.user_id = session_data.get("uid") if session_data else None

    # ✅ 라우터(prefix) 단위 접근제어: /reports/* 전부 차단
    if request.state.user_id is None:
        path = request.url.path
        if _is_protected(path):
            next_q = _build_next(request)
            return RedirectResponse(url=f"/users/login?next={next_q}", status_code=303)

    response = await call_next(request)

    # ✅ 로그아웃 후 뒤로가기 방지: 보호 페이지는 캐시 금지
    # (뒤로가면 화면이 잠깐 보이는 BFCache/캐시를 줄여줌)
    if _is_protected(request.url.path):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


# ✅ 공통 로그인 가드 (페이지용: 로그인 안 되어 있으면 login?next=... 로 리다이렉트)
def _require_login(request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        next_q = _build_next(request)
        return RedirectResponse(url=f"/users/login?next={next_q}", status_code=303)
    return int(user_id)


# ✅ 첫 진입: 로그인 안 했으면 로그인으로, 했으면 대시보드로
from fastapi.responses import HTMLResponse, RedirectResponse

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # 스플래시 페이지로 이동 (URL!)
    return RedirectResponse(url="/splash", status_code=303)

@app.get("/splash", response_class=HTMLResponse)
def splash(request: Request):
    # 템플릿 렌더링 (템플릿 경로!)
    return templates.TemplateResponse(
        "splash.html",
        {"request": request, "title": "SmartLedger"},
    )

# ✅ 대시보드: 로그인 필수
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id

    return templates.TemplateResponse(
        "pages/dashboard.html",
        {"request": request, "title": "Dashboard", "user_id": user_id},
    )


# ✅ 아래 페이지들도 전부 로그인 필수
@app.get("/transactions", response_class=HTMLResponse)
def transactions_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/transactions.html",
        {"request": request, "title": "거래내역"},
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/search.html",
        {"request": request, "title": "검색"},
    )


@app.get("/notification-settings", response_class=HTMLResponse)
def notification_settings_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/notification_settings.html",
        {"request": request, "title": "알림설정"},
    )


@app.get("/data-export", response_class=HTMLResponse)
def data_export_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/data_export.html",
        {"request": request, "title": "데이터 내보내기"},
    )


@app.get("/category-edit", response_class=HTMLResponse)
def category_edit_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/category_edit.html",
        {"request": request, "title": "카테고리 편집"},
    )


@app.get("/category-income", response_class=HTMLResponse)
def category_income_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/category_income.html",
        {"request": request, "title": "카테고리 편집"},
    )


@app.get("/category-asset", response_class=HTMLResponse)
def category_asset_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/category_asset.html",
        {"request": request, "title": "카테고리 편집"},
    )


@app.get("/budget-settings", response_class=HTMLResponse)
def budget_settings_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/budget_settings.html",
        {"request": request, "title": "예산 설정"},
    )


@app.get("/receipts/confirm", response_class=HTMLResponse)
def receipt_confirm_page(request: Request):
    user_id = _require_login(request)
    if isinstance(user_id, RedirectResponse):
        return user_id
    return templates.TemplateResponse(
        "pages/receipt_confirm.html",
        {"request": request, "title": "영수증 확인"},
    )


# ✅ 라우터 등록
app.include_router(health.router)
app.include_router(receipts.router)
app.include_router(users.router)
app.include_router(reports.router)   # ✅ /reports 는 미들웨어에서 자동 차단
app.include_router(exports.router)
app.include_router(alerts.router)
