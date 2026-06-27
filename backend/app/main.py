from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import load_settings
from app.core.rate_limit import SimpleRateLimitMiddleware
from app.db.database import get_connection, init_db
from app.db.seed import ensure_demo_data
from app.routers import ai, config, factors, health, meta, screener, stocks, strategies, sync, watchlists
from app.services.factor_engine import FactorEngine
from app.services.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with get_connection() as conn:
        ensure_demo_data(conn)
        existing = conn.execute("SELECT COUNT(*) FROM computed_factors").fetchone()[0]
        stock_count = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        if existing < stock_count:
            FactorEngine(conn).calculate_all(force=True)
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
app.include_router(strategies.router)
app.include_router(stocks.router)
app.include_router(watchlists.router)


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": 400, "message": str(exc), "data": None})


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"code": 500, "message": str(exc), "data": None})
