from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RangeFilter(BaseModel):
    min: float | None = None
    max: float | None = None


class IndexConditions(BaseModel):
    index_codes: list[str] = Field(default_factory=list)
    require_member: bool = True
    excess_return_days: int | None = 20
    min_excess_return: float | None = None
    max_pe_percentile: float | None = None
    max_pb_percentile: float | None = None
    track_momentum_top_n: int | None = None


class FundamentalConditions(BaseModel):
    pe_ttm: RangeFilter | None = None
    pb: RangeFilter | None = None
    peg: RangeFilter | None = None
    roe: RangeFilter | None = None
    gross_margin: RangeFilter | None = None
    netprofit_margin: RangeFilter | None = None
    revenue_yoy: RangeFilter | None = None
    deduct_profit_yoy: RangeFilter | None = None
    debt_to_assets: RangeFilter | None = None
    dividend_yield: RangeFilter | None = None
    total_mv: RangeFilter | None = None
    circ_mv: RangeFilter | None = None
    goodwill_ratio: RangeFilter | None = None
    industry_percentile_top: float | None = None


class TechnicalConditions(BaseModel):
    above_ma: list[int] = Field(default_factory=list)
    macd_cross: Literal["golden", "dead"] | None = None
    kdj_cross: Literal["golden", "dead"] | None = None
    rsi: RangeFilter | None = None
    pct_chg_n: RangeFilter | None = None
    pct_chg_days: int = 20
    turnover_rate: RangeFilter | None = None
    volume_ratio: RangeFilter | None = None
    breakout_days: int | None = None
    limit_up_days_min: int | None = None


class CapitalConditions(BaseModel):
    north_inflow_min: float | None = None
    main_net_inflow_min: float | None = None
    margin_balance_delta_min: float | None = None
    institution_holding_ratio_min: float | None = None
    top_list_score_min: float | None = None


class SentimentConditions(BaseModel):
    days: int = 7
    min_avg_score: float | None = None
    include_labels: list[str] = Field(default_factory=list)
    whitelist_keywords: list[str] = Field(default_factory=list)
    blacklist_keywords: list[str] = Field(default_factory=list)
    max_negative_ratio: float | None = None


class FilterOptions(BaseModel):
    exclude_st: bool | None = None
    exclude_paused: bool | None = None
    new_stock_days: int | None = None
    min_market_cap: float | None = None


class WeightOptions(BaseModel):
    fundamental: float = 35
    technical: float = 30
    capital: float = 20
    sentiment: float = 15


class ScreeningRequest(BaseModel):
    logic: Literal["and", "or"] = "and"
    index: IndexConditions = Field(default_factory=IndexConditions)
    fundamental: FundamentalConditions = Field(default_factory=FundamentalConditions)
    technical: TechnicalConditions = Field(default_factory=TechnicalConditions)
    capital: CapitalConditions = Field(default_factory=CapitalConditions)
    sentiment: SentimentConditions = Field(default_factory=SentimentConditions)
    filters: FilterOptions = Field(default_factory=FilterOptions)
    weights: WeightOptions = Field(default_factory=WeightOptions)
    limit: int = 200


class StockScore(BaseModel):
    ts_code: str
    symbol: str
    name: str
    industry: str | None = None
    index_names: list[str] = Field(default_factory=list)
    close: float | None = None
    pct_chg: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    roe: float | None = None
    revenue_yoy: float | None = None
    circ_mv: float | None = None
    main_net_inflow: float | None = None
    sentiment_score: float = 50
    sentiment_label: str = "中性"
    fundamental_score: float = 0
    technical_score: float = 0
    capital_score: float = 0
    sentiment_factor_score: float = 0
    ai_score: float = 0
    rating: Literal["A", "B", "C", "D"] = "C"
    metrics: dict[str, float | str | None] = Field(default_factory=dict)


class StockMarketItem(StockScore):
    trade_date: str | None = None
    total_mv: float | None = None
    turnover_rate: float | None = None
    volume_ratio: float | None = None
    pct_chg_20: float | None = None
    pct_chg_60: float | None = None
    is_st: bool = False
    is_paused: bool = False


class StockMarketResponse(BaseModel):
    total: int
    page: int
    page_size: int
    rows: list[StockMarketItem]
    latest_trade_date: str | None = None
    industries: list[str] = Field(default_factory=list)
    factor_universe_count: int = 0


class ScreeningDiagnostics(BaseModel):
    stock_universe_count: int = 0
    factor_universe_count: int = 0
    base_universe_count: int = 0
    condition_count: int = 0
    matched_count: int = 0
    returned_count: int = 0
    excluded_counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ScreeningResult(BaseModel):
    total: int
    rows: list[StockScore]
    industry_distribution: dict[str, int]
    sentiment_distribution: dict[str, int]
    factor_distribution: dict[str, list[float]]
    latest_trade_date: str | None = None
    diagnostics: ScreeningDiagnostics = Field(default_factory=ScreeningDiagnostics)


class NewsAnalyzeRequest(BaseModel):
    ts_code: str
    title: str
    content: str
    source: str = "manual"
    publish_time: str | None = None


class NewsSentiment(BaseModel):
    score: float
    label: str
    keywords: list[str] = Field(default_factory=list)
    reason: str = ""


class NaturalLanguageRequest(BaseModel):
    text: str


class WorkflowRunRequest(BaseModel):
    text: str
    workflow_path: str | None = None


class WebSearchRequest(BaseModel):
    query: str | None = None
    queries: list[str] = Field(default_factory=list)
    count: int | None = None
    time_range: str | None = None
    search_type: Literal["web", "image", "web_summary"] | None = None
    need_summary: bool | None = None
    need_content: bool | None = None
    sites: str | None = None


class WebSearchItem(BaseModel):
    type: Literal["web", "image"] = "web"
    query: str
    title: str
    url: str
    site_name: str | None = None
    snippet: str = ""
    summary: str = ""
    content: str = ""
    publish_time: str | None = None
    rank_score: float | None = None
    image_url: str | None = None
    image_width: int | None = None
    image_height: int | None = None


class WebSearchResponse(BaseModel):
    provider: str = "volc-search"
    search_type: str
    queries: list[str]
    total: int
    items: list[WebSearchItem]
    rag: str | None = None
    request_ids: list[str] = Field(default_factory=list)
    time_cost_ms: int | None = None


class OneClickRecommendRequest(BaseModel):
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"
    limit: int = Field(default=8, ge=1, le=30)
    include_search: bool = True
    focus_themes: list[str] = Field(default_factory=list)


class StockRecommendationItem(BaseModel):
    ts_code: str
    name: str
    industry: str | None = None
    rating: str
    ai_score: float
    action: str
    reason: str
    risk: str
    confidence: float
    source: Literal["llm", "fallback"] = "fallback"
    stock: StockScore | None = None


class OneClickRecommendResponse(BaseModel):
    market_view: str
    strategy: str
    risk_preference: str
    recommendations: list[StockRecommendationItem]
    risk_notes: list[str] = Field(default_factory=list)
    search_context: list[dict[str, object]] = Field(default_factory=list)
    disclaimer: str = "本功能仅基于公开数据做统计研究，不构成任何投资建议。"


class WorkflowStepTrace(BaseModel):
    id: str
    name: str
    type: str
    status: Literal["success", "skipped", "failed", "fallback"]
    started_at: str
    finished_at: str
    summary: str = ""
    output_preview: dict[str, object] = Field(default_factory=dict)


class StockSelectionWorkflowResult(BaseModel):
    workflow_name: str
    workflow_path: str
    parsed_request: ScreeningRequest
    screening_result: ScreeningResult | None = None
    llm_analysis: dict[str, object] = Field(default_factory=dict)
    raw_conditions: dict[str, object] = Field(default_factory=dict)
    steps: list[WorkflowStepTrace] = Field(default_factory=list)


class StrategyCreate(BaseModel):
    name: str
    remark: str = ""
    conditions: ScreeningRequest
    schedule_enabled: bool = False
    schedule_cron: str = ""


class StrategyUpdate(BaseModel):
    name: str | None = None
    remark: str | None = None
    conditions: ScreeningRequest | None = None
    schedule_enabled: bool | None = None
    schedule_cron: str | None = None


class StrategyOut(BaseModel):
    id: int
    name: str
    remark: str
    conditions: ScreeningRequest
    result_count: int
    avg_score: float
    avg_pct_chg: float
    schedule_enabled: bool
    schedule_cron: str
    created_at: str
    updated_at: str


class KLinePoint(BaseModel):
    trade_date: str
    open: float
    close: float
    low: float
    high: float
    volume: float
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None


class StockNewsItem(BaseModel):
    id: int
    title: str
    content: str
    source: str | None
    publish_time: str
    sentiment_score: float
    sentiment_label: str
    keywords: list[str]


class StockDetail(BaseModel):
    base: StockScore
    kline: list[KLinePoint]
    news: list[StockNewsItem]
    radar: dict[str, float]
    rating: str


class WatchlistGroupCreate(BaseModel):
    name: str
    description: str = ""
    color: str = "blue"
    sort_order: int = 0


class WatchlistGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    sort_order: int | None = None


class WatchlistGroupOut(BaseModel):
    id: int
    name: str
    description: str
    color: str
    sort_order: int
    item_count: int = 0
    created_at: str
    updated_at: str


class WatchlistItemCreate(BaseModel):
    ts_code: str
    group_id: int | None = None
    group_name: str | None = None
    reason: str = ""
    tags: list[str] = Field(default_factory=list)
    priority: int = Field(default=3, ge=1, le=5)
    risk_level: Literal["low", "medium", "high"] = "medium"
    status: Literal["active", "paused", "closed"] = "active"
    cost_price: float | None = None
    target_price: float | None = None
    stop_loss_price: float | None = None
    review_interval_days: int = Field(default=7, ge=1, le=365)
    next_review_date: str | None = None


class WatchlistItemUpdate(BaseModel):
    group_id: int | None = None
    reason: str | None = None
    tags: list[str] | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    risk_level: Literal["low", "medium", "high"] | None = None
    status: Literal["active", "paused", "closed"] | None = None
    cost_price: float | None = None
    target_price: float | None = None
    stop_loss_price: float | None = None
    review_interval_days: int | None = Field(default=None, ge=1, le=365)
    next_review_date: str | None = None


class WatchlistItemOut(BaseModel):
    id: int
    group_id: int
    group_name: str
    ts_code: str
    reason: str
    tags: list[str]
    priority: int
    risk_level: str
    status: str
    cost_price: float | None = None
    target_price: float | None = None
    stop_loss_price: float | None = None
    review_interval_days: int
    next_review_date: str | None = None
    created_at: str
    updated_at: str
    stock: StockScore | None = None


class WatchlistNoteCreate(BaseModel):
    item_id: int | None = None
    note_type: Literal["manual", "review", "ai_review"] = "manual"
    content: str


class WatchlistNoteOut(BaseModel):
    id: int
    item_id: int | None = None
    note_type: str
    content: str
    ai_payload: dict[str, object] = Field(default_factory=dict)
    created_at: str


class WatchlistAskRequest(BaseModel):
    question: str
    group_id: int | None = None
    item_id: int | None = None
    include_search: bool = True


class WatchlistAskResponse(BaseModel):
    answer: str
    action_items: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)
    focus_symbols: list[str] = Field(default_factory=list)
    source: Literal["llm", "fallback"] = "fallback"
    snapshot: list[dict[str, object]] = Field(default_factory=list)


class SyncRequest(BaseModel):
    provider: Literal["auto", "akshare", "tushare", "demo"] | None = None
    trade_date: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    sync_news: bool = True
    sync_fundamentals: bool = True
    sync_indices: bool = True
