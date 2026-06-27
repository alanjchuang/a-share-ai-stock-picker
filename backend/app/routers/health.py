import sqlite3

from fastapi import APIRouter, Depends

from app.core.config import load_settings
from app.core.response import ApiResponse, ok
from app.db.database import get_db
from app.models.schemas import DataHealthResponse, DataTableStatus

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=ApiResponse[dict[str, str]])
def health() -> ApiResponse[dict[str, str]]:
    return ok({"status": "ok"})


def _scalar(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[object, ...] = (),
    default: int | float | str | None = 0,
) -> int | float | str | None:
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return default
    return row[0] if row[0] is not None else default


def _table_status(
    conn: sqlite3.Connection,
    key: str,
    name: str,
    table: str,
    date_column: str | None = None,
    note: str = "",
) -> DataTableStatus:
    row_count = int(_scalar(conn, f"SELECT COUNT(*) FROM {table}", default=0) or 0)
    latest_date = None
    coverage_count: int | None = None
    if date_column:
        latest_date = str(_scalar(conn, f"SELECT MAX({date_column}) FROM {table}", default=None) or "") or None
        if latest_date and table in {"stock_daily", "fundamentals", "capital_flows"}:
            coverage_count = int(
                _scalar(
                    conn,
                    f"SELECT COUNT(DISTINCT ts_code) FROM {table} WHERE {date_column} = ?",
                    (latest_date,),
                    0,
                )
                or 0
            )
    return DataTableStatus(key=key, name=name, row_count=row_count, latest_date=latest_date, coverage_count=coverage_count, note=note)


def _stock_daily_status(conn: sqlite3.Connection, min_rows: int) -> DataTableStatus:
    row_count = int(_scalar(conn, "SELECT COUNT(*) FROM stock_daily", default=0) or 0)
    latest_date = str(_scalar(conn, "SELECT MAX(trade_date) FROM stock_daily", default=None) or "") or None
    coverage_count = int(
        _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM (
                SELECT ts_code, COUNT(*) AS rows_count
                FROM stock_daily
                GROUP BY ts_code
                HAVING rows_count >= ?
            )
            """,
            (min_rows,),
            0,
        )
        or 0
    )
    return DataTableStatus(
        key="stock_daily",
        name="日线行情",
        row_count=row_count,
        latest_date=latest_date,
        coverage_count=coverage_count,
        note=f"行情选择、K线和技术因子；覆盖按至少{min_rows}条K线统计",
    )


@router.get("/system/data-health", response_model=ApiResponse[DataHealthResponse])
def data_health(conn=Depends(get_db)) -> ApiResponse[DataHealthResponse]:
    settings = load_settings()
    db_path = settings.db_path
    history_min_rows = max(int(settings.akshare.history_min_rows or 120), 1)
    tables = [
        _table_status(conn, "stocks", "股票基础信息", "stocks", note="用于搜索、详情和筛选池"),
        _stock_daily_status(conn, history_min_rows),
        _table_status(conn, "fundamentals", "财务估值", "fundamentals", "trade_date", "PE/PB/ROE/成长因子"),
        _table_status(conn, "capital_flows", "资金流", "capital_flows", "trade_date", "主力、北向、融资和龙虎榜因子"),
        _table_status(conn, "computed_factors", "因子缓存", "computed_factors", "trade_date", "页面优先读取该缓存，减少即时重算"),
        _table_status(conn, "stock_news", "新闻舆情", "stock_news", "publish_time", "公告、资讯和舆情评分"),
        _table_status(conn, "index_members", "指数成分", "index_members", note="指数池筛选和赛道过滤"),
        _table_status(conn, "analysis_reports", "复盘报告", "analysis_reports", "created_at", "本地历史复盘"),
    ]
    latest_trade_date = next((item.latest_date for item in tables if item.key == "stock_daily"), None)
    stock_count = next((item.row_count for item in tables if item.key == "stocks"), 0)
    history_count = next((item.coverage_count or 0 for item in tables if item.key == "stock_daily"), 0)
    factor_count = next((item.row_count for item in tables if item.key == "computed_factors"), 0)
    warnings: list[str] = []
    if stock_count == 0:
        warnings.append("股票基础信息为空，请先在系统配置或数据中心触发一次同步。")
    if factor_count < stock_count:
        warnings.append(f"因子缓存覆盖 {factor_count}/{stock_count}，建议等待后台预热或手动重算缓存。")
    if stock_count and history_count < stock_count:
        warnings.append(f"历史K线深度覆盖 {history_count}/{stock_count}（至少{history_min_rows}条），选股技术因子会偏弱，请在数据中心执行全市场历史K线补齐。")
    if settings.market_data.provider == "demo":
        warnings.append("当前处于 DEMO 数据源，真实荐股和 AI 解析会要求切换真实数据源。")
    if settings.market_data.fallback_to_demo:
        warnings.append("当前允许失败回退演示数据，线上使用建议关闭兜底后观察数据源错误。")
    if not latest_trade_date:
        warnings.append("暂无最新交易日缓存，行情选择页会缺少排序和涨跌幅依据。")

    payload = DataHealthResponse(
        provider=settings.market_data.provider,
        fallback_to_demo=settings.market_data.fallback_to_demo,
        db_path=str(db_path),
        db_size_mb=round(db_path.stat().st_size / 1024 / 1024, 2) if db_path.exists() else 0,
        scheduler_enabled=settings.scheduler.enabled,
        daily_sync_cron=settings.scheduler.daily_sync_cron,
        factor_cache_refresh_minutes=settings.scheduler.factor_cache_refresh_minutes,
        latest_trade_date=latest_trade_date,
        tables=tables,
        warnings=warnings,
    )
    return ok(payload)
