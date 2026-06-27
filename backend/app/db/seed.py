from __future__ import annotations

import math
import random
import sqlite3
from datetime import datetime, timedelta


DEMO_STOCKS = [
    ("600519.SH", "600519", "贵州茅台", "贵州", "食品饮料", "主板", "SSE", "20010827", "H"),
    ("300750.SZ", "300750", "宁德时代", "福建", "电力设备", "创业板", "SZSE", "20180611", "S"),
    ("002475.SZ", "002475", "立讯精密", "广东", "电子", "主板", "SZSE", "20100915", "S"),
    ("000858.SZ", "000858", "五粮液", "四川", "食品饮料", "主板", "SZSE", "19980427", "S"),
    ("601318.SH", "601318", "中国平安", "广东", "非银金融", "主板", "SSE", "20070301", "H"),
    ("600036.SH", "600036", "招商银行", "广东", "银行", "主板", "SSE", "20020409", "H"),
    ("000333.SZ", "000333", "美的集团", "广东", "家用电器", "主板", "SZSE", "20130918", "S"),
    ("002230.SZ", "002230", "科大讯飞", "安徽", "计算机", "主板", "SZSE", "20080512", "S"),
    ("688981.SH", "688981", "中芯国际", "上海", "电子", "科创板", "SSE", "20200716", "H"),
    ("601012.SH", "601012", "隆基绿能", "陕西", "电力设备", "主板", "SSE", "20120411", "H"),
    ("600276.SH", "600276", "恒瑞医药", "江苏", "医药生物", "主板", "SSE", "20001018", "H"),
    ("002594.SZ", "002594", "比亚迪", "广东", "汽车", "主板", "SZSE", "20110630", "S"),
    ("000001.SZ", "000001", "平安银行", "广东", "银行", "主板", "SZSE", "19910403", "S"),
    ("300760.SZ", "300760", "迈瑞医疗", "广东", "医药生物", "创业板", "SZSE", "20181016", "S"),
    ("688111.SH", "688111", "金山办公", "北京", "计算机", "科创板", "SSE", "20191118", "H"),
    ("600900.SH", "600900", "长江电力", "北京", "公用事业", "主板", "SSE", "20031118", "H"),
]

DEMO_INDICES = [
    ("000300.SH", "沪深300", "宽基"),
    ("000905.SH", "中证500", "宽基"),
    ("000852.SH", "中证1000", "宽基"),
    ("000016.SH", "上证50", "宽基"),
    ("399006.SZ", "创业板指", "宽基"),
    ("000688.SH", "科创50", "宽基"),
    ("899050.BJ", "北证50", "宽基"),
    ("801080.SI", "电子申万一级", "申万行业"),
    ("801120.SI", "食品饮料申万一级", "申万行业"),
    ("801790.SI", "非银金融申万一级", "申万行业"),
    ("801780.SI", "银行申万一级", "申万行业"),
    ("CONCEPT_AI", "AI算力概念", "热门赛道"),
    ("CONCEPT_SEMI", "半导体国产替代", "热门赛道"),
    ("CONCEPT_STORAGE", "储能新能源", "热门赛道"),
    ("CONCEPT_DEFENSE", "军工安全", "热门赛道"),
    ("CONCEPT_MEDICAL", "创新医药", "热门赛道"),
]

INDEX_MEMBERS = {
    "000300.SH": ["600519.SH", "300750.SZ", "000858.SZ", "601318.SH", "600036.SH", "000333.SZ", "002594.SZ", "600900.SH", "300760.SZ"],
    "000905.SH": ["002475.SZ", "002230.SZ", "601012.SH", "600276.SH", "000001.SZ"],
    "000852.SH": ["688111.SH", "688981.SH"],
    "000016.SH": ["600519.SH", "601318.SH", "600036.SH", "600900.SH"],
    "399006.SZ": ["300750.SZ", "300760.SZ"],
    "000688.SH": ["688981.SH", "688111.SH"],
    "801080.SI": ["002475.SZ", "688981.SH"],
    "801120.SI": ["600519.SH", "000858.SZ"],
    "801790.SI": ["601318.SH"],
    "801780.SI": ["600036.SH", "000001.SZ"],
    "CONCEPT_AI": ["002230.SZ", "688111.SH", "688981.SH"],
    "CONCEPT_SEMI": ["688981.SH", "002475.SZ"],
    "CONCEPT_STORAGE": ["300750.SZ", "601012.SH", "002594.SZ"],
    "CONCEPT_MEDICAL": ["600276.SH", "300760.SZ"],
}

POSITIVE_NEWS = [
    ("签署大额订单，业绩增长确定性提升", "公司公告获得核心客户长期订单，预计带动未来收入和现金流改善，机构关注度上升。", 86, "重大利好", "大额订单,业绩增长"),
    ("发布新产品并推进国产替代", "新产品在算力、效率和成本上具备竞争力，政策扶持与国产替代需求形成共振。", 78, "普通利好", "国产替代,政策扶持"),
]
NEUTRAL_NEWS = ("召开投资者交流会，经营保持稳健", "公司回应市场关注问题，未披露重大未公开事项，基本面节奏平稳。", 56, "中性", "交流会,稳健经营")
NEGATIVE_NEWS = ("股东计划减持，短期情绪承压", "部分股东披露减持计划，市场短期风险偏好下降，需关注成交量与价格波动。", 28, "普通利空", "减持,情绪承压")


def _trade_dates(days: int = 180) -> list[str]:
    today = datetime.now().date()
    result: list[str] = []
    current = today
    while len(result) < days:
        if current.weekday() < 5:
            result.append(current.strftime("%Y%m%d"))
        current -= timedelta(days=1)
    return list(reversed(result))


def ensure_demo_data(conn: sqlite3.Connection) -> None:
    """初始化可运行演示数据；真实环境配置Tushare token后可覆盖增量同步。"""
    existing = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
    if existing:
        return

    random.seed(20260627)
    dates = _trade_dates()
    latest_date = dates[-1]

    conn.executemany(
        """
        INSERT OR REPLACE INTO stocks
        (ts_code, symbol, name, area, industry, market, exchange, list_date, is_hs, is_st, is_paused)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)
        """,
        DEMO_STOCKS,
    )
    conn.executemany("INSERT OR REPLACE INTO index_info(index_code, name, category) VALUES (?, ?, ?)", DEMO_INDICES)

    for index_code, members in INDEX_MEMBERS.items():
        for order, ts_code in enumerate(members, start=1):
            conn.execute(
                "INSERT OR REPLACE INTO index_members(index_code, ts_code, weight, in_date, out_date) VALUES (?, ?, ?, ?, '')",
                (index_code, ts_code, max(0.5, 12 - order), dates[0]),
            )

    for stock_idx, stock in enumerate(DEMO_STOCKS):
        ts_code = stock[0]
        base = 18 + stock_idx * 6 + (90 if ts_code == "600519.SH" else 0)
        trend = 0.015 * ((stock_idx % 5) - 1)
        previous = base
        for i, trade_date in enumerate(dates):
            cycle = math.sin(i / 7 + stock_idx) * (1.5 + stock_idx % 3)
            close = max(2, base + trend * i + cycle + random.uniform(-0.8, 0.8))
            open_price = max(1, previous * (1 + random.uniform(-0.015, 0.015)))
            high = max(open_price, close) * (1 + random.uniform(0.002, 0.025))
            low = min(open_price, close) * (1 - random.uniform(0.002, 0.025))
            pct_chg = (close - previous) / previous * 100 if previous else 0
            volume = 80_000 + stock_idx * 9_000 + random.randint(0, 60_000)
            amount = volume * close / 10
            turnover = max(0.2, 1.2 + math.sin(i / 11 + stock_idx) + random.uniform(-0.25, 0.25))
            volume_ratio = max(0.3, 1 + math.sin(i / 5 + stock_idx) * 0.35 + random.uniform(-0.15, 0.15))
            conn.execute(
                """
                INSERT OR REPLACE INTO stock_daily
                (ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount, turnover_rate, volume_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_code,
                    trade_date,
                    round(open_price, 2),
                    round(high, 2),
                    round(low, 2),
                    round(close, 2),
                    round(previous, 2),
                    round(close - previous, 2),
                    round(pct_chg, 2),
                    round(volume, 2),
                    round(amount, 2),
                    round(turnover, 2),
                    round(volume_ratio, 2),
                ),
            )
            main_flow = math.sin(i / 9 + stock_idx) * 6500 + random.uniform(-1500, 1500)
            conn.execute(
                """
                INSERT OR REPLACE INTO capital_flows
                (ts_code, trade_date, north_inflow, main_net_inflow, margin_balance_delta, institution_holding_ratio, top_list_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_code,
                    trade_date,
                    round(math.sin(i / 13 + stock_idx) * 2500, 2),
                    round(main_flow, 2),
                    round(math.cos(i / 15 + stock_idx) * 1800, 2),
                    round(4 + stock_idx % 7 + abs(math.sin(i / 31)) * 18, 2),
                    round(max(0, min(100, 55 + main_flow / 250)), 2),
                ),
            )
            previous = close

        valuation_bias = stock_idx % 6
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals
            (ts_code, trade_date, pe_ttm, pb, peg, roe, gross_margin, netprofit_margin, revenue_yoy,
             deduct_profit_yoy, debt_to_assets, ocf, dividend_yield, total_mv, circ_mv, goodwill_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ts_code,
                latest_date,
                round(12 + valuation_bias * 5 + random.uniform(-2, 2), 2),
                round(1.1 + valuation_bias * 0.45 + random.uniform(-0.1, 0.2), 2),
                round(0.6 + valuation_bias * 0.22 + random.uniform(-0.05, 0.15), 2),
                round(8 + (stock_idx % 8) * 3.2 + random.uniform(-1, 2), 2),
                round(22 + (stock_idx % 6) * 7 + random.uniform(-2, 3), 2),
                round(8 + (stock_idx % 5) * 4 + random.uniform(-1, 2), 2),
                round(-4 + (stock_idx % 9) * 5 + random.uniform(-3, 3), 2),
                round(-8 + (stock_idx % 8) * 6 + random.uniform(-2, 4), 2),
                round(28 + (stock_idx % 6) * 7 + random.uniform(-4, 5), 2),
                round(20_000 + stock_idx * 2_700 + random.uniform(-2000, 3000), 2),
                round(0.5 + (stock_idx % 5) * 0.55, 2),
                round(650 + stock_idx * 260 + (9000 if ts_code == "600519.SH" else 0), 2),
                round(380 + stock_idx * 160 + (8200 if ts_code == "600519.SH" else 0), 2),
                round(max(0, (stock_idx % 4) * 1.8 + random.uniform(-0.5, 0.8)), 2),
            ),
        )

        news_rows = [POSITIVE_NEWS[stock_idx % 2], NEUTRAL_NEWS]
        if stock_idx % 5 == 0:
            news_rows.append(NEGATIVE_NEWS)
        for news_idx, news in enumerate(news_rows):
            publish_time = (datetime.now() - timedelta(days=news_idx * 3 + stock_idx % 4)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO stock_news
                (ts_code, title, content, source, publish_time, sentiment_score, sentiment_label, keywords)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts_code, news[0], news[1], "demo", publish_time, news[2], news[3], news[4]),
            )

    for index_idx, index in enumerate(DEMO_INDICES):
        code = index[0]
        close = 3000 + index_idx * 80
        for i, trade_date in enumerate(dates):
            next_close = close * (1 + math.sin(i / 17 + index_idx) * 0.002 + random.uniform(-0.006, 0.006))
            pct_chg = (next_close - close) / close * 100
            momentum = math.sin(i / 19 + index_idx) * 8 + index_idx
            conn.execute(
                "INSERT OR REPLACE INTO index_daily(index_code, trade_date, close, pct_chg, momentum_20) VALUES (?, ?, ?, ?, ?)",
                (code, trade_date, round(next_close, 2), round(pct_chg, 2), round(momentum, 2)),
            )
            close = next_close
        conn.execute(
            """
            INSERT OR REPLACE INTO index_valuation(index_code, trade_date, pe, pb, pe_percentile, pb_percentile)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                code,
                latest_date,
                round(11 + index_idx * 1.8, 2),
                round(1.0 + index_idx * 0.12, 2),
                round(min(95, 18 + index_idx * 5.5), 2),
                round(min(95, 22 + index_idx * 4.5), 2),
            ),
        )
    conn.commit()
