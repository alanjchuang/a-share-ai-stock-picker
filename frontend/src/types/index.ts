export type LogicMode = 'and' | 'or';
export type Rating = 'A' | 'B' | 'C' | 'D';
export type CrossSignal = 'golden' | 'dead';
export type ThemeMode = 'light' | 'dark';
export type WorkbenchMode = 'beginner' | 'professional';

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

export interface BackgroundJobResponse {
  accepted: boolean;
  job_id?: number | null;
  job_type: string;
  status: string;
  message: string;
}

export interface SyncJobOut {
  id: number;
  job_type: string;
  status: string;
  message: string;
  started_at: string;
  finished_at?: string | null;
}

export interface DataTableStatus {
  key: string;
  name: string;
  row_count: number;
  latest_date?: string | null;
  coverage_count?: number | null;
  note: string;
}

export interface DataHealthResponse {
  provider: AppConfig['market_data']['provider'];
  fallback_to_demo: boolean;
  db_path: string;
  db_size_mb: number;
  scheduler_enabled: boolean;
  daily_sync_cron: string;
  factor_cache_refresh_minutes: number;
  startup_sync_enabled: boolean;
  incremental_sync_minutes: number;
  incremental_sync_lookback_days: number;
  latest_trade_date?: string | null;
  tables: DataTableStatus[];
  warnings: string[];
}

export interface RangeFilter {
  min?: number | null;
  max?: number | null;
}

export interface IndexConditions {
  index_codes: string[];
  require_member: boolean;
  excess_return_days?: number | null;
  min_excess_return?: number | null;
  max_pe_percentile?: number | null;
  max_pb_percentile?: number | null;
  track_momentum_top_n?: number | null;
}

export interface FundamentalConditions {
  pe_ttm?: RangeFilter | null;
  pb?: RangeFilter | null;
  peg?: RangeFilter | null;
  roe?: RangeFilter | null;
  gross_margin?: RangeFilter | null;
  netprofit_margin?: RangeFilter | null;
  revenue_yoy?: RangeFilter | null;
  deduct_profit_yoy?: RangeFilter | null;
  debt_to_assets?: RangeFilter | null;
  dividend_yield?: RangeFilter | null;
  total_mv?: RangeFilter | null;
  circ_mv?: RangeFilter | null;
  goodwill_ratio?: RangeFilter | null;
  industry_percentile_top?: number | null;
}

export interface TechnicalConditions {
  above_ma: number[];
  macd_cross?: CrossSignal | null;
  kdj_cross?: CrossSignal | null;
  rsi?: RangeFilter | null;
  pct_chg_n?: RangeFilter | null;
  pct_chg_days: number;
  turnover_rate?: RangeFilter | null;
  volume_ratio?: RangeFilter | null;
  breakout_days?: number | null;
  limit_up_days_min?: number | null;
}

export interface CapitalConditions {
  north_inflow_min?: number | null;
  main_net_inflow_min?: number | null;
  margin_balance_delta_min?: number | null;
  institution_holding_ratio_min?: number | null;
  top_list_score_min?: number | null;
}

export interface SentimentConditions {
  days: number;
  min_avg_score?: number | null;
  include_labels: string[];
  whitelist_keywords: string[];
  blacklist_keywords: string[];
  max_negative_ratio?: number | null;
}

export interface FilterOptions {
  exclude_st?: boolean | null;
  exclude_paused?: boolean | null;
  new_stock_days?: number | null;
  min_market_cap?: number | null;
}

export interface WeightOptions {
  fundamental: number;
  technical: number;
  capital: number;
  sentiment: number;
}

export interface ScreeningRequest {
  logic: LogicMode;
  index: IndexConditions;
  fundamental: FundamentalConditions;
  technical: TechnicalConditions;
  capital: CapitalConditions;
  sentiment: SentimentConditions;
  filters: FilterOptions;
  weights: WeightOptions;
  limit: number;
}

export interface StockScore {
  ts_code: string;
  symbol: string;
  name: string;
  industry?: string | null;
  index_names: string[];
  close?: number | null;
  pct_chg?: number | null;
  pe_ttm?: number | null;
  pb?: number | null;
  roe?: number | null;
  revenue_yoy?: number | null;
  circ_mv?: number | null;
  main_net_inflow?: number | null;
  sentiment_score: number;
  sentiment_label: string;
  fundamental_score: number;
  technical_score: number;
  capital_score: number;
  sentiment_factor_score: number;
  ai_score: number;
  rating: Rating;
  metrics: Record<string, number | string | null | undefined>;
}

export interface StockMarketItem extends StockScore {
  trade_date?: string | null;
  total_mv?: number | null;
  turnover_rate?: number | null;
  volume_ratio?: number | null;
  pct_chg_20?: number | null;
  pct_chg_60?: number | null;
  is_st: boolean;
  is_paused: boolean;
}

export interface StockMarketResponse {
  total: number;
  page: number;
  page_size: number;
  rows: StockMarketItem[];
  latest_trade_date?: string | null;
  industries: string[];
  factor_universe_count: number;
}

export interface EtfDailyPoint {
  trade_date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
  amount: number;
  ma5?: number | null;
  ma20?: number | null;
  ma60?: number | null;
}

export interface EtfMarketItem {
  etf_code: string;
  symbol: string;
  name: string;
  category: string;
  fund_type: string;
  exchange: string;
  trade_date?: string | null;
  close?: number | null;
  pct_chg?: number | null;
  amount?: number | null;
  turnover_rate?: number | null;
  iopv?: number | null;
  discount_rate?: number | null;
  flow_mv?: number | null;
  total_mv?: number | null;
  pct_chg_20?: number | null;
  pct_chg_60?: number | null;
  pct_chg_120?: number | null;
  volatility_60?: number | null;
  max_drawdown_120?: number | null;
}

export interface EtfMarketResponse {
  total: number;
  page: number;
  page_size: number;
  rows: EtfMarketItem[];
  latest_trade_date?: string | null;
  categories: string[];
}

export interface EtfDetail {
  base: EtfMarketItem;
  kline: EtfDailyPoint[];
  data_source: string;
  data_warnings: string[];
}

export interface IndustryHeatItem {
  industry: string;
  count: number;
  avg_pct_chg: number;
  avg_ai_score: number;
  up_ratio: number;
}

export interface KlinePatternHit {
  ts_code: string;
  name: string;
  industry?: string | null;
  pattern: string;
  signal: 'bullish' | 'bearish' | 'neutral';
  strength: number;
  trade_date?: string | null;
  close?: number | null;
  pct_chg?: number | null;
  reason: string;
  stock?: StockScore | null;
}

export interface StrategyDefinition {
  key: string;
  name: string;
  category: string;
  description: string;
  risk_level: 'low' | 'medium' | 'high';
}

export interface StrategyHit {
  ts_code: string;
  name: string;
  industry?: string | null;
  strategy_key: string;
  strategy_name: string;
  signal_score: number;
  reason: string;
  stock: StockScore;
}

export interface StrategyBacktestSummary {
  sample_count: number;
  win_rate: number;
  avg_return: number;
  median_return: number;
  max_return: number;
  min_return: number;
  holding_days: number;
}

export interface StrategyScanResponse {
  strategy: StrategyDefinition;
  total: number;
  rows: StrategyHit[];
  backtest: StrategyBacktestSummary;
  latest_trade_date?: string | null;
}

export interface DecisionDashboardResponse {
  latest_trade_date?: string | null;
  total: number;
  up_count: number;
  down_count: number;
  flat_count: number;
  limit_up_count: number;
  limit_down_count: number;
  avg_pct_chg: number;
  avg_ai_score: number;
  avg_sentiment_score: number;
  market_view: string;
  risk_alerts: string[];
  industry_heat: IndustryHeatItem[];
  top_ai: StockScore[];
  top_gainers: StockScore[];
  top_losers: StockScore[];
  high_risk: StockScore[];
  strategy_hits: Array<Record<string, unknown>>;
}

export interface PatternRadarResponse {
  total: number;
  rows: KlinePatternHit[];
  latest_trade_date?: string | null;
  distribution: Record<string, number>;
}

export interface AnalysisReportOut {
  id: number;
  report_type: string;
  title: string;
  content: string;
  source: string;
  created_at: string;
}

export interface ScreeningResult {
  total: number;
  rows: StockScore[];
  industry_distribution: Record<string, number>;
  sentiment_distribution: Record<string, number>;
  factor_distribution: Record<string, number[]>;
  latest_trade_date?: string | null;
  diagnostics?: ScreeningDiagnostics;
}

export interface ScreeningDiagnostics {
  stock_universe_count: number;
  factor_universe_count: number;
  base_universe_count: number;
  condition_count: number;
  matched_count: number;
  returned_count: number;
  excluded_counts: Record<string, number>;
  warnings: string[];
}

export interface IndexMeta {
  index_code: string;
  name: string;
  category: string;
  member_count: number;
  pe?: number | null;
  pb?: number | null;
  pe_percentile?: number | null;
  pb_percentile?: number | null;
}

export interface KLinePoint {
  trade_date: string;
  open: number;
  close: number;
  low: number;
  high: number;
  volume: number;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  ma60?: number | null;
}

export interface StockNewsItem {
  id: number;
  title: string;
  content: string;
  source?: string | null;
  publish_time: string;
  sentiment_score: number;
  sentiment_label: string;
  keywords: string[];
}

export interface FinancialSnapshot {
  report_date: string;
  pe_ttm?: number | null;
  pb?: number | null;
  roe?: number | null;
  gross_margin?: number | null;
  netprofit_margin?: number | null;
  revenue_yoy?: number | null;
  deduct_profit_yoy?: number | null;
  debt_to_assets?: number | null;
  ocf?: number | null;
  dividend_yield?: number | null;
  total_mv?: number | null;
  circ_mv?: number | null;
  goodwill_ratio?: number | null;
}

export interface StockDetail {
  base: StockScore;
  kline: KLinePoint[];
  financial_history: FinancialSnapshot[];
  news: StockNewsItem[];
  radar: Record<string, number>;
  rating: string;
  data_source: string;
  data_warnings: string[];
}

export interface StockLlmAnalysisResponse {
  ts_code: string;
  name: string;
  source: 'llm' | 'fallback';
  summary: string;
  key_points: string[];
  risks: string[];
  watch_items: string[];
  questions: string[];
  disclaimer: string;
}

export interface StrategyOut {
  id: number;
  name: string;
  remark: string;
  conditions: ScreeningRequest;
  result_count: number;
  avg_score: number;
  avg_pct_chg: number;
  schedule_enabled: boolean;
  schedule_cron: string;
  created_at: string;
  updated_at: string;
}

export interface WorkflowStepTrace {
  id: string;
  name: string;
  type: string;
  status: 'success' | 'skipped' | 'failed' | 'fallback';
  started_at: string;
  finished_at: string;
  summary: string;
  output_preview: Record<string, unknown>;
}

export interface WorkflowInfo {
  name: string;
  description: string;
  version: string;
  path: string;
  is_default?: boolean;
  error?: string;
  steps: Array<{
    id?: string;
    name?: string;
    type?: string;
    enabled?: boolean;
  }>;
}

export interface StockSelectionWorkflowResult {
  workflow_name: string;
  workflow_path: string;
  parsed_request: ScreeningRequest;
  screening_result?: ScreeningResult | null;
  llm_analysis: Record<string, unknown>;
  raw_conditions: Record<string, unknown>;
  tool_calls: Array<Record<string, unknown>>;
  parse_warnings: string[];
  steps: WorkflowStepTrace[];
}

export interface StockSelectionWorkflowJob {
  id: number;
  job_type: string;
  status: 'queued' | 'running' | 'success' | 'failed' | 'blocked' | string;
  message: string;
  started_at: string;
  finished_at?: string | null;
  result?: StockSelectionWorkflowResult | null;
}

export interface WatchlistGroup {
  id: number;
  name: string;
  description: string;
  color: string;
  sort_order: number;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface WatchlistItem {
  id: number;
  group_id: number;
  group_name: string;
  ts_code: string;
  reason: string;
  tags: string[];
  priority: number;
  risk_level: 'low' | 'medium' | 'high' | string;
  status: 'active' | 'paused' | 'closed' | string;
  cost_price?: number | null;
  target_price?: number | null;
  stop_loss_price?: number | null;
  review_interval_days: number;
  next_review_date?: string | null;
  created_at: string;
  updated_at: string;
  stock?: StockScore | null;
}

export interface WatchlistItemCreate {
  ts_code: string;
  group_id?: number | null;
  group_name?: string | null;
  reason?: string;
  tags?: string[];
  priority?: number;
  risk_level?: 'low' | 'medium' | 'high';
  status?: 'active' | 'paused' | 'closed';
  cost_price?: number | null;
  target_price?: number | null;
  stop_loss_price?: number | null;
  review_interval_days?: number;
  next_review_date?: string | null;
}

export interface WatchlistAskResponse {
  answer: string;
  action_items: string[];
  risk_notes: string[];
  review_questions: string[];
  focus_symbols: string[];
  source: 'llm' | 'fallback';
  snapshot: Array<Record<string, unknown>>;
}

export type WatchlistNoteType = 'manual' | 'review' | 'ai_review';

export interface WatchlistNote {
  id: number;
  item_id?: number | null;
  note_type: WatchlistNoteType;
  content: string;
  ai_payload: Record<string, unknown>;
  created_at: string;
}

export interface StockRecommendationItem {
  ts_code: string;
  name: string;
  industry?: string | null;
  rating: string;
  ai_score: number;
  action: string;
  reason: string;
  risk: string;
  confidence: number;
  source: 'llm' | 'fallback';
  stock?: StockScore | null;
}

export interface OneClickRecommendResponse {
  market_view: string;
  strategy: string;
  risk_preference: string;
  recommendations: StockRecommendationItem[];
  risk_notes: string[];
  search_context: Array<Record<string, unknown>>;
  disclaimer: string;
}

export interface OneClickRecommendJob {
  id: number;
  job_type: string;
  status: 'queued' | 'running' | 'success' | 'failed' | 'blocked' | string;
  message: string;
  started_at: string;
  finished_at?: string | null;
  result?: OneClickRecommendResponse | null;
}

export type SearchType = 'web' | 'image' | 'web_summary';

export interface WebSearchRequest {
  query?: string | null;
  queries?: string[];
  count?: number | null;
  time_range?: string | null;
  search_type?: SearchType | null;
  need_summary?: boolean | null;
  need_content?: boolean | null;
  sites?: string | null;
}

export interface WebSearchItem {
  type: 'web' | 'image';
  query: string;
  title: string;
  url: string;
  site_name?: string | null;
  snippet: string;
  summary: string;
  content: string;
  publish_time?: string | null;
  rank_score?: number | null;
  image_url?: string | null;
  image_width?: number | null;
  image_height?: number | null;
}

export interface WebSearchResponse {
  provider: string;
  search_type: string;
  queries: string[];
  total: number;
  items: WebSearchItem[];
  rag?: string | null;
  request_ids: string[];
  time_cost_ms?: number | null;
}

export interface MarketPromptRequest {
  seed_query: string;
  focus?: string | null;
  count?: number;
}

export interface MarketPromptResponse {
  prompts: string[];
  reason: string;
  source: 'llm';
}

export interface AppConfig {
  server: {
    host: string;
    port: number;
    cors_origins: string[];
  };
  database: {
    path: string;
  };
  market_data: {
    provider: 'auto' | 'akshare' | 'tushare' | 'demo';
    fallback_to_demo: boolean;
    clear_factor_cache_on_sync: boolean;
  };
  akshare: {
    enabled: boolean;
    adjust: string;
    request_interval_seconds: number;
    default_start_date: string;
    default_end_date: string;
    max_history_symbols: number;
    history_min_rows: number;
    max_financial_symbols: number;
    max_news_symbols: number;
    max_metadata_symbols: number;
  };
  tushare: {
    enabled: boolean;
    token: string;
    request_interval_seconds: number;
    default_start_date: string;
    default_trade_date: string;
  };
  llm: {
    provider: string;
    api_base: string;
    api_key: string;
    model: string;
    temperature: number;
    max_tokens: number;
    timeout_seconds: number;
    num_retries: number;
    local_model_path: string;
  };
  search: {
    enabled: boolean;
    base_url: string;
    api_key: string;
    model: string;
    timeout_seconds: number;
    default_count: number;
    max_count: number;
    default_search_type: SearchType;
    need_summary: boolean;
    need_content: boolean;
  };
  workflow: {
    enabled: boolean;
    default_path: string;
    trace_payload_preview: boolean;
  };
  filters: {
    exclude_st: boolean;
    exclude_paused: boolean;
    new_stock_days: number;
    min_market_cap: number;
  };
  weights: WeightOptions;
  scheduler: {
    enabled: boolean;
    daily_sync_cron: string;
    factor_cache_refresh_minutes: number;
    startup_sync_enabled: boolean;
    incremental_sync_minutes: number;
    incremental_sync_lookback_days: number;
  };
}
