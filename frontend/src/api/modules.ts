import { request } from './http';
import type {
  AppConfig,
  AnalysisReportOut,
  BackgroundJobResponse,
  DataHealthResponse,
  DecisionDashboardResponse,
  IndexMeta,
  PatternRadarResponse,
  ScreeningRequest,
  ScreeningResult,
  OneClickRecommendResponse,
  StockSelectionWorkflowResult,
  StockDetail,
  StockMarketResponse,
  StrategyDefinition,
  StrategyScanResponse,
  StrategyOut,
  SyncJobOut,
  WebSearchRequest,
  WebSearchResponse,
  WatchlistAskResponse,
  WatchlistGroup,
  WatchlistItem,
  WatchlistItemCreate,
  WatchlistNote,
  WorkflowInfo
} from '../types';

export const defaultScreeningRequest: ScreeningRequest = {
  logic: 'and',
  index: {
    index_codes: [],
    require_member: false,
    excess_return_days: 20,
    min_excess_return: null,
    max_pe_percentile: null,
    max_pb_percentile: null,
    track_momentum_top_n: null
  },
  fundamental: {
    pe_ttm: null,
    pb: { min: null, max: null },
    peg: null,
    roe: null,
    gross_margin: null,
    netprofit_margin: null,
    revenue_yoy: null,
    deduct_profit_yoy: null,
    debt_to_assets: null,
    dividend_yield: null,
    total_mv: null,
    circ_mv: null,
    goodwill_ratio: null,
    industry_percentile_top: null
  },
  technical: {
    above_ma: [],
    macd_cross: null,
    kdj_cross: null,
    rsi: null,
    pct_chg_n: null,
    pct_chg_days: 20,
    turnover_rate: null,
    volume_ratio: null,
    breakout_days: null,
    limit_up_days_min: null
  },
  capital: {
    north_inflow_min: null,
    main_net_inflow_min: null,
    margin_balance_delta_min: null,
    institution_holding_ratio_min: null,
    top_list_score_min: null
  },
  sentiment: {
    days: 7,
    min_avg_score: null,
    include_labels: [],
    whitelist_keywords: [],
    blacklist_keywords: [],
    max_negative_ratio: null
  },
  filters: {
    exclude_st: true,
    exclude_paused: true,
    new_stock_days: 180,
    min_market_cap: 0
  },
  weights: {
    fundamental: 35,
    technical: 30,
    capital: 20,
    sentiment: 15
  },
  limit: 200
};

export const api = {
  health: () => request<{ status: string }>({ url: '/health', method: 'GET' }),
  getDataHealth: () => request<DataHealthResponse>({ url: '/system/data-health', method: 'GET' }),
  listSyncJobs: () => request<SyncJobOut[]>({ url: '/sync/jobs', method: 'GET' }),
  listIndices: () => request<IndexMeta[]>({ url: '/meta/indices', method: 'GET' }),
  getDecisionDashboard: (limit = 8) => request<DecisionDashboardResponse>({ url: '/analysis/dashboard', method: 'GET', params: { limit } }),
  listBuiltInStrategies: () => request<StrategyDefinition[]>({ url: '/analysis/strategies', method: 'GET' }),
  scanBuiltInStrategy: (strategyKey: string, params?: { limit?: number; holding_days?: number }) =>
    request<StrategyScanResponse>({ url: `/analysis/strategies/${encodeURIComponent(strategyKey)}`, method: 'GET', params }),
  getPatternRadar: (params?: { limit?: number; signal?: 'bullish' | 'bearish' | 'neutral' | 'all' }) =>
    request<PatternRadarResponse>({ url: '/analysis/patterns', method: 'GET', params }),
  listReports: (limit = 30) => request<AnalysisReportOut[]>({ url: '/reports', method: 'GET', params: { limit } }),
  generateDailyReport: () => request<AnalysisReportOut>({ url: '/reports/daily', method: 'POST' }),
  getReport: (id: number) => request<AnalysisReportOut>({ url: `/reports/${id}`, method: 'GET' }),
  runScreener: (data: ScreeningRequest) => request<ScreeningResult>({ url: '/screener/run', method: 'POST', data }),
  parseText: (text: string) => request<ScreeningRequest>({ url: '/ai/parse', method: 'POST', data: { text } }),
  oneClickRecommend: (data: { risk_preference: 'conservative' | 'balanced' | 'aggressive'; limit?: number; include_search?: boolean; focus_themes?: string[] }) =>
    request<OneClickRecommendResponse>({ url: '/ai/recommendations/one-click', method: 'POST', data }),
  runSelectionWorkflow: (text: string, workflowPath?: string) =>
    request<StockSelectionWorkflowResult>({
      url: '/ai/stock-selection-workflow',
      method: 'POST',
      data: { text, workflow_path: workflowPath }
    }),
  listWorkflows: () => request<WorkflowInfo[]>({ url: '/ai/workflows', method: 'GET' }),
  searchWeb: (data: WebSearchRequest) => request<WebSearchResponse>({ url: '/ai/search', method: 'POST', data }),
  listStockMarket: (params: {
    q?: string;
    industry?: string;
    rating?: string;
    include_st?: boolean;
    include_paused?: boolean;
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: 'asc' | 'desc';
  }) => request<StockMarketResponse>({ url: '/stocks', method: 'GET', params }),
  getStockDetail: (tsCode: string) => request<StockDetail>({ url: `/stocks/${encodeURIComponent(tsCode)}`, method: 'GET' }),
  listStrategies: () => request<StrategyOut[]>({ url: '/strategies', method: 'GET' }),
  createStrategy: (data: { name: string; remark: string; conditions: ScreeningRequest; schedule_enabled: boolean; schedule_cron: string }) =>
    request<StrategyOut>({ url: '/strategies', method: 'POST', data }),
  updateStrategy: (
    id: number,
    data: { name?: string; remark?: string; conditions?: ScreeningRequest; schedule_enabled?: boolean; schedule_cron?: string }
  ) => request<StrategyOut>({ url: `/strategies/${id}`, method: 'PUT', data }),
  deleteStrategy: (id: number) => request<{ deleted: number }>({ url: `/strategies/${id}`, method: 'DELETE' }),
  getConfig: () => request<AppConfig>({ url: '/config', method: 'GET' }),
  updateConfig: (data: Partial<AppConfig>) => request<AppConfig>({ url: '/config', method: 'PUT', data }),
  syncData: (provider?: AppConfig['market_data']['provider']) =>
    request<BackgroundJobResponse>({
      url: '/sync/run',
      method: 'POST',
      data: { provider, sync_news: true, sync_fundamentals: true, sync_indices: true }
    }),
  calculateFactors: () => request<BackgroundJobResponse>({ url: '/factors/calculate', method: 'POST' }),
  listWatchlistGroups: () => request<WatchlistGroup[]>({ url: '/watchlists/groups', method: 'GET' }),
  createWatchlistGroup: (data: { name: string; description?: string; color?: string; sort_order?: number }) =>
    request<WatchlistGroup>({ url: '/watchlists/groups', method: 'POST', data }),
  listWatchlistItems: (params?: { group_id?: number; status?: string }) =>
    request<WatchlistItem[]>({ url: '/watchlists/items', method: 'GET', params }),
  addWatchlistItem: (data: WatchlistItemCreate) => request<WatchlistItem>({ url: '/watchlists/items', method: 'POST', data }),
  updateWatchlistItem: (id: number, data: Partial<WatchlistItemCreate>) =>
    request<WatchlistItem>({ url: `/watchlists/items/${id}`, method: 'PUT', data }),
  deleteWatchlistItem: (id: number) => request<{ deleted: number }>({ url: `/watchlists/items/${id}`, method: 'DELETE' }),
  askWatchlist: (data: { question: string; group_id?: number | null; item_id?: number | null; include_search?: boolean }) =>
    request<WatchlistAskResponse>({ url: '/watchlists/ask', method: 'POST', data }),
  listWatchlistNotes: (itemId?: number) => request<WatchlistNote[]>({ url: '/watchlists/notes', method: 'GET', params: { item_id: itemId } }),
  createWatchlistNote: (data: { item_id?: number | null; note_type?: string; content: string }) =>
    request<WatchlistNote>({ url: '/watchlists/notes', method: 'POST', data })
};
