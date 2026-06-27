from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import load_settings
from app.core.rate_limit import SimpleRateLimitMiddleware
from app.db.database import get_connection, init_db
from app.db.seed import ensure_demo_data
from app.services.background_jobs import mark_interrupted_jobs
from app.services.data_quality_service import DataQualityService
from app.routers import ai, analysis, config, factors, health, meta, reports, screener, stocks, strategies, sync, watchlists
from app.services.factor_engine import FactorEngine
from app.services.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    conn = get_connection()
    try:
        mark_interrupted_jobs(conn)
        ensure_demo_data(conn)
        quality_result = DataQualityService(conn).clean_mixed_demo_rows()
        existing = conn.execute("SELECT COUNT(*) FROM computed_factors").fetchone()[0]
        stock_count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        if existing < stock_count or quality_result.get("deleted_daily"):
            FactorEngine(conn).calculate_all(force=True)
    finally:
        conn.close()
    start_scheduler()
    yield
    shutdown_scheduler()


settings = load_settings()
app = FastAPI(
    title="A股多因子智能选股Web系统",
    description="本工具仅基于公开数据做AI量化统计，不构成任何投资建议。",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SimpleRateLimitMiddleware)

app.include_router(health.router)
app.include_router(meta.router)
app.include_router(config.router)
app.include_router(sync.router)
app.include_router(factors.router)
app.include_router(screener.router)
app.include_router(ai.router)
app.include_router(analysis.router)
app.include_router(reports.router)
app.include_router(strategies.router)
app.include_router(stocks.router)
app.include_router(watchlists.router)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": 400, "message": str(exc), "data": None})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(_: Request, exc: RuntimeError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": 400, "message": str(exc), "data": None})


@app.exception_handler(sqlite3.OperationalError)
async def sqlite_error_handler(_: Request, exc: sqlite3.OperationalError) -> JSONResponse:
    message = str(exc)
    if "database is locked" in message.lower():
        return JSONResponse(
            status_code=503,
            content={
                "code": 503,
                "message": "数据库正在后台刷新缓存，请稍后重试；选股和详情会优先读取上一版缓存。",
                "data": None,
            },
        )
    return JSONResponse(status_code=500, content={"code": 500, "message": message, "data": None})


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
    return JSONResponse(status_code=exc.status_code, content={"code": exc.status_code, "message": message, "data": None})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(item) for item in first_error.get("loc", []) if item != "body")
    detail = str(first_error.get("msg") or "请求参数校验失败")
    message = f"{loc}: {detail}" if loc else detail
    return JSONResponse(status_code=422, content={"code": 422, "message": message, "data": None})


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"code": 500, "message": str(exc), "data": None})
