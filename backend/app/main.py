from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, ORJSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .api import admin, alerts, analytics, auth, budget, connections, events, health, rules, transactions
from .config import get_settings

settings = get_settings()
base_dir = Path(__file__).resolve().parent

app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    default_response_class=ORJSONResponse,
    docs_url=None,
    redoc_url=None,
)
if settings.trusted_host_list != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(budget.router)
app.include_router(transactions.router)
app.include_router(rules.router)
app.include_router(connections.router)
app.include_router(admin.router)
app.include_router(alerts.router)
app.include_router(analytics.router)
app.include_router(events.router)

app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
templates = Jinja2Templates(directory=base_dir / "templates")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    )
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={"app_name": settings.app_name})


@app.get("/{path:path}", response_class=HTMLResponse)
def spa_fallback(path: str, request: Request):
    if path.startswith(("api/", "health/", "static/")):
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse(request=request, name="index.html", context={"app_name": settings.app_name})
