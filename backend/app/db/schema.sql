PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS stocks (
    ts_code TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    area TEXT,
    industry TEXT,
    market TEXT,
    exchange TEXT,
    list_date TEXT,
    is_hs TEXT,
    is_st INTEGER DEFAULT 0,
    is_paused INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_daily (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    pre_close REAL,
    change REAL,
    pct_chg REAL,
    vol REAL,
    amount REAL,
    turnover_rate REAL,
    volume_ratio REAL,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS fundamentals (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    pe_ttm REAL,
    pb REAL,
    peg REAL,
    roe REAL,
    gross_margin REAL,
    netprofit_margin REAL,
    revenue_yoy REAL,
    deduct_profit_yoy REAL,
    debt_to_assets REAL,
    ocf REAL,
    dividend_yield REAL,
    total_mv REAL,
    circ_mv REAL,
    goodwill_ratio REAL,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS capital_flows (
    ts_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    north_inflow REAL,
    main_net_inflow REAL,
    margin_balance_delta REAL,
    institution_holding_ratio REAL,
    top_list_score REAL,
    PRIMARY KEY (ts_code, trade_date)
);

CREATE TABLE IF NOT EXISTS stock_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_code TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source TEXT,
    publish_time TEXT NOT NULL,
    sentiment_score REAL DEFAULT 50,
    sentiment_label TEXT DEFAULT '中性',
    keywords TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS index_info (
    index_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS index_members (
    index_code TEXT NOT NULL,
    ts_code TEXT NOT NULL,
    weight REAL DEFAULT 0,
    in_date TEXT,
    out_date TEXT,
    PRIMARY KEY (index_code, ts_code)
);

CREATE TABLE IF NOT EXISTS index_daily (
    index_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    close REAL,
    pct_chg REAL,
    momentum_20 REAL,
    PRIMARY KEY (index_code, trade_date)
);

CREATE TABLE IF NOT EXISTS index_valuation (
    index_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    pe REAL,
    pb REAL,
    pe_percentile REAL,
    pb_percentile REAL,
    PRIMARY KEY (index_code, trade_date)
);

CREATE TABLE IF NOT EXISTS computed_factors (
    ts_code TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    remark TEXT DEFAULT '',
    conditions_json TEXT NOT NULL,
    result_count INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0,
    avg_pct_chg REAL DEFAULT 0,
    schedule_enabled INTEGER DEFAULT 0,
    schedule_cron TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT DEFAULT '',
    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);
