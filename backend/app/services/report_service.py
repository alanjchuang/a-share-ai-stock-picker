from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.models.schemas import AnalysisReportOut, StockScore
from app.services.analysis_service import AnalysisService


class ReportService:
    """生成和保存本地复盘报告。

    报告是公开数据统计摘要，不调用交易接口，也不输出买卖指令。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.analysis = AnalysisService(conn)

    def list_reports(self, limit: int = 30) -> list[AnalysisReportOut]:
        rows = self.conn.execute(
            """
            SELECT id, report_type, title, content, source, created_at
            FROM analysis_reports
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
        return [AnalysisReportOut.model_validate(dict(row)) for row in rows]

    def generate_daily_report(self) -> AnalysisReportOut:
        dashboard = self.analysis.dashboard(limit=8)
        strategies = [self.analysis.scan_strategy(item.key, limit=6, holding_days=10) for item in self.analysis.strategy_definitions()[:5]]
        content = self._daily_markdown(dashboard, strategies)
        title = f"{dashboard.latest_trade_date or 'latest'} A股决策复盘"
        cursor = self.conn.execute(
            """
            INSERT INTO analysis_reports(report_type, title, content, payload_json, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "daily",
                title,
                content,
                json.dumps(
                    {
                        "dashboard": dashboard.model_dump(mode="json"),
                        "strategies": [item.model_dump(mode="json") for item in strategies],
                    },
                    ensure_ascii=False,
                ),
                "deterministic",
            ),
        )
        self.conn.commit()
        return self.get_report(int(cursor.lastrowid))

    def get_report(self, report_id: int) -> AnalysisReportOut:
        row = self.conn.execute(
            """
            SELECT id, report_type, title, content, source, created_at
            FROM analysis_reports
            WHERE id = ?
            """,
            (report_id,),
        ).fetchone()
        if not row:
            raise ValueError("报告不存在")
        return AnalysisReportOut.model_validate(dict(row))

    def _daily_markdown(self, dashboard: Any, strategies: list[Any]) -> str:
        lines: list[str] = [
            f"# {dashboard.latest_trade_date or '最新'} A股决策复盘",
            "",
            "## 市场概况",
            "",
            f"- 股票池：{dashboard.total} 只",
            f"- 上涨/下跌/平盘：{dashboard.up_count}/{dashboard.down_count}/{dashboard.flat_count}",
            f"- 涨停/跌停：{dashboard.limit_up_count}/{dashboard.limit_down_count}",
            f"- 平均涨跌幅：{dashboard.avg_pct_chg:.2f}%",
            f"- 平均AI评分：{dashboard.avg_ai_score:.1f}",
            f"- 平均舆情分：{dashboard.avg_sentiment_score:.1f}",
            "",
            f"> {dashboard.market_view}",
            "",
            "## 风险警报",
            "",
            *[f"- {item}" for item in dashboard.risk_alerts],
            "",
            "## 行业热度",
            "",
            "| 行业 | 数量 | 平均涨跌幅 | 上涨占比 | 平均AI评分 |",
            "| --- | ---: | ---: | ---: | ---: |",
            *[
                f"| {item.industry} | {item.count} | {item.avg_pct_chg:.2f}% | {item.up_ratio:.2f}% | {item.avg_ai_score:.1f} |"
                for item in dashboard.industry_heat[:10]
            ],
            "",
            "## AI评分靠前",
            "",
            self._stock_table(dashboard.top_ai),
            "",
            "## 涨幅靠前",
            "",
            self._stock_table(dashboard.top_gainers),
            "",
            "## 风险复核",
            "",
            self._stock_table(dashboard.high_risk),
            "",
            "## 策略信号",
            "",
        ]
        for strategy in strategies:
            lines.extend(
                [
                    f"### {strategy.strategy.name}",
                    "",
                    f"- 命中数量：{strategy.total}",
                    f"- 10日回测样本：{strategy.backtest.sample_count}",
                    f"- 胜率：{strategy.backtest.win_rate:.2f}%",
                    f"- 平均收益：{strategy.backtest.avg_return:.2f}%",
                    "",
                    self._strategy_table(strategy.rows[:6]),
                    "",
                ]
            )
        lines.extend(["---", "本报告仅基于公开数据做统计研究，不构成任何投资建议。"])
        return "\n".join(lines)

    @staticmethod
    def _stock_table(rows: list[StockScore]) -> str:
        if not rows:
            return "暂无。"
        lines = ["| 股票 | 行业 | 涨跌幅 | 舆情 | AI评分 |", "| --- | --- | ---: | --- | ---: |"]
        for row in rows:
            lines.append(
                f"| {row.name}({row.ts_code}) | {row.industry or '-'} | {(row.pct_chg or 0):.2f}% | {row.sentiment_label} {row.sentiment_score:.0f} | {row.rating} {row.ai_score:.1f} |"
            )
        return "\n".join(lines)

    @staticmethod
    def _strategy_table(rows: list[Any]) -> str:
        if not rows:
            return "暂无。"
        lines = ["| 股票 | 行业 | 信号分 | 理由 |", "| --- | --- | ---: | --- |"]
        for row in rows:
            lines.append(f"| {row.name}({row.ts_code}) | {row.industry or '-'} | {row.signal_score:.1f} | {row.reason} |")
        return "\n".join(lines)
