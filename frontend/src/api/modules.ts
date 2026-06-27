import { clearRequestCache, request } from './http';
import type {
  AppConfig,
  AnalysisReportOut,
  BackgroundJobResponse,
  DataHealthResponse,
  DecisionDashboardResponse,
  EtfDetail,
  EtfMarketResponse,
  IndexMeta,
  MarketPromptRequest,
  MarketPromptResponse,
  PatternRadarResponse,
  ScreeningRequest,
  ScreeningResult,
  OneClickRecommendJob,
  OneClickRecommendResponse,
  StockSelectionWorkflowResult,
  StockSelectionWorkflowJob,
  StockDetail,
  StockLlmAnalysisResponse,
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
  WatchlistNoteType,
  WorkflowInfo
} from '../types';

type ApiRequestOptions = { forceRefresh?: boolean };

const META_CACHE_TTL_MS = 5 * 60 * 1000;
const PAGE_CACHE_TTL_MS = 60 * 1000;
const MARKET_CACHE_TTL_MS = 30 * 1000;

function cacheOptions(ttlMs: number, options?: ApiRequestOptions): { cacheTtlMs: number; forceRefresh?: boolean } {
  return { cacheTtlMs: ttlMs, forceRefresh: options?.forceRefresh };
}

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
  getDataHealth: () => request<DataHealthResponse>({ url: '/system/data-health', method: 'GET', skipGlobalLoading: true }),
  listSyncJobs: () => request<SyncJobOut[]>({ url: '/sync/jobs', method: 'GET', skipGlobalLoading: true }),
  getSyncJob: (jobId: number) => request<SyncJobOut>({ url: `/sync/jobs/${jobId}`, method: 'GET', skipGlobalLoading: true }),
  getActiveSyncJob: () => request<SyncJobOut | null>({ url: '/sync/jobs/active', method: 'GET', skipGlobalLoading: true }),
  cancelSyncJob: (jobId: number) => request<BackgroundJobResponse>({ url: `/sync/jobs/${jobId}/cancel`, method: 'POST' }),
  listIndices: (options?: ApiRequestOptions) =>
    request<IndexMeta[]>({ url: '/meta/indices', method: 'GET', skipGlobalLoading: true, ...cacheOptions(META_CACHE_TTL_MS, options) }),
  getDecisionDashboard: (limit = 8, options?: ApiRequestOptions) =>
    request<DecisionDashboardResponse>({ url: '/analysis/dashboard', method: 'GET', params: { limit }, ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  listBuiltInStrategies: (options?: ApiRequestOptions) =>
    request<StrategyDefinition[]>({ url: '/analysis/strategies', method: 'GET', skipGlobalLoading: true, ...cacheOptions(META_CACHE_TTL_MS, options) }),
  scanBuiltInStrategy: (strategyKey: string, params?: { limit?: number; holding_days?: number }, options?: ApiRequestOptions) =>
    request<StrategyScanResponse>({ url: `/analysis/strategies/${encodeURIComponent(strategyKey)}`, method: 'GET', params, ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  getPatternRadar: (params?: { limit?: number; signal?: 'bullish' | 'bearish' | 'neutral' | 'all' }, options?: ApiRequestOptions) =>
    request<PatternRadarResponse>({ url: '/analysis/patterns', method: 'GET', params, ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  listReports: (limit = 30, options?: ApiRequestOptions) =>
    request<AnalysisReportOut[]>({ url: '/reports', method: 'GET', params: { limit }, ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  generateDailyReport: async () => {
    clearRequestCache('/reports');
    const report = await request<AnalysisReportOut>({ url: '/reports/daily', method: 'POST' });
    clearRequestCache('/reports');
    return report;
  },
  getReport: (id: number) => request<AnalysisReportOut>({ url: `/reports/${id}`, method: 'GET' }),
  runScreener: (data: ScreeningRequest) => request<ScreeningResult>({ url: '/screener/run', method: 'POST', data }),
  parseText: (text: string) => request<ScreeningRequest>({ url: '/ai/parse', method: 'POST', data: { text } }),
  oneClickRecommend: (data: { risk_preference: 'conservative' | 'balanced' | 'aggressive'; limit?: number; include_search?: boolean; focus_themes?: string[] }) =>
    request<BackgroundJobResponse>({ url: '/ai/recommendations/one-click', method: 'POST', data, skipGlobalLoading: true }),
  listOneClickRecommendJobs: (limit = 20) =>
    request<OneClickRecommendJob[]>({ url: '/ai/recommendations/one-click/jobs', method: 'GET', params: { limit }, skipGlobalLoading: true }),
  getOneClickRecommendJob: (jobId: number) =>
    request<OneClickRecommendJob>({ url: `/ai/recommendations/one-click/jobs/${jobId}`, method: 'GET', skipGlobalLoading: true }),
  runSelectionWorkflow: (text: string, workflowPath?: string) =>
    request<StockSelectionWorkflowResult>({
      url: '/ai/stock-selection-workflow',
      method: 'POST',
      data: { text, workflow_path: workflowPath },
      skipGlobalLoading: true
    }),
  submitSelectionWorkflow: (text: string, workflowPath?: string) =>
    request<BackgroundJobResponse>({
      url: '/ai/stock-selection-workflow/jobs',
      method: 'POST',
      data: { text, workflow_path: workflowPath },
      skipGlobalLoading: true
    }),
  listSelectionWorkflowJobs: (limit = 20) =>
    request<StockSelectionWorkflowJob[]>({ url: '/ai/stock-selection-workflow/jobs', method: 'GET', params: { limit }, skipGlobalLoading: true }),
  getSelectionWorkflowJob: (jobId: number) =>
    request<StockSelectionWorkflowJob>({ url: `/ai/stock-selection-workflow/jobs/${jobId}`, method: 'GET', skipGlobalLoading: true }),
  listWorkflows: (options?: ApiRequestOptions) =>
    request<WorkflowInfo[]>({ url: '/ai/workflows', method: 'GET', skipGlobalLoading: true, ...cacheOptions(META_CACHE_TTL_MS, options) }),
  searchWeb: (data: WebSearchRequest) => request<WebSearchResponse>({ url: '/ai/search', method: 'POST', data }),
  generateMarketPrompts: (data: MarketPromptRequest) => request<MarketPromptResponse>({ url: '/ai/market-prompts', method: 'POST', data }),
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
  }, options?: ApiRequestOptions) => request<StockMarketResponse>({ url: '/stocks', method: 'GET', params, ...cacheOptions(MARKET_CACHE_TTL_MS, options) }),
  getStockDetail: (tsCode: string, options?: ApiRequestOptions) =>
    request<StockDetail>({ url: `/stocks/${encodeURIComponent(tsCode)}`, method: 'GET', skipGlobalLoading: true, ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  analyzeStock: (tsCode: string) =>
    request<StockLlmAnalysisResponse>({ url: `/stocks/${encodeURIComponent(tsCode)}/llm-analysis`, method: 'POST', skipGlobalLoading: true }),
  refreshStockDetail: async (tsCode: string) => {
    clearRequestCache(`/stocks/${encodeURIComponent(tsCode)}`);
    const job = await request<BackgroundJobResponse>({ url: `/stocks/${encodeURIComponent(tsCode)}/refresh`, method: 'POST', skipGlobalLoading: true });
    clearRequestCache(`/stocks/${encodeURIComponent(tsCode)}`);
    return job;
  },
  syncStockHistory: (tsCode: string) =>
    request<BackgroundJobResponse>({ url: `/stocks/${encodeURIComponent(tsCode)}/history/sync`, method: 'POST' }),
  listEtfs: (params: {
    q?: string;
    category?: string;
    page?: number;
    page_size?: number;
    sort_by?: string;
    sort_order?: 'asc' | 'desc';
  }, options?: ApiRequestOptions) => request<EtfMarketResponse>({ url: '/etfs', method: 'GET', params, ...cacheOptions(MARKET_CACHE_TTL_MS, options) }),
  getEtfDetail: (etfCode: string, options?: ApiRequestOptions) =>
    request<EtfDetail>({ url: `/etfs/${encodeURIComponent(etfCode)}`, method: 'GET', ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  syncEtfs: async (historyLimit = 0) => {
    clearRequestCache('/etfs');
    const job = await request<BackgroundJobResponse>({ url: '/etfs/sync', method: 'POST', params: { history_limit: historyLimit } });
    clearRequestCache('/etfs');
    return job;
  },
  listStrategies: () => request<StrategyOut[]>({ url: '/strategies', method: 'GET' }),
  createStrategy: (data: { name: string; remark: string; conditions: ScreeningRequest; schedule_enabled: boolean; schedule_cron: string }) =>
    request<StrategyOut>({ url: '/strategies', method: 'POST', data }),
  updateStrategy: (
    id: number,
    data: { name?: string; remark?: string; conditions?: ScreeningRequest; schedule_enabled?: boolean; schedule_cron?: string }
  ) => request<StrategyOut>({ url: `/strategies/${id}`, method: 'PUT', data }),
  deleteStrategy: (id: number) => request<{ deleted: number }>({ url: `/strategies/${id}`, method: 'DELETE' }),
  getConfig: (options?: ApiRequestOptions) =>
    request<AppConfig>({ url: '/config', method: 'GET', skipGlobalLoading: true, ...cacheOptions(PAGE_CACHE_TTL_MS, options) }),
  updateConfig: async (data: Partial<AppConfig>) => {
    clearRequestCache('/config');
    const nextConfig = await request<AppConfig>({ url: '/config', method: 'PUT', data });
    clearRequestCache('/config');
    return nextConfig;
  },
  syncData: async (provider?: AppConfig['market_data']['provider']) => {
    clearRequestCache('/analysis');
    clearRequestCache('/stocks');
    clearRequestCache('/etfs');
    const job = await request<BackgroundJobResponse>({
      url: '/sync/run',
      method: 'POST',
      data: { provider, sync_news: true, sync_fundamentals: true, sync_indices: true }
    });
    return job;
  },
  syncAllStockHistory: async () => {
    clearRequestCache('/stocks');
    return request<BackgroundJobResponse>({ url: '/sync/history/all', method: 'POST' });
  },
  calculateFactors: async () => {
    clearRequestCache('/analysis');
    clearRequestCache('/stocks');
    return request<BackgroundJobResponse>({ url: '/factors/calculate', method: 'POST' });
  },
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
  createWatchlistNote: (data: { item_id?: number | null; note_type?: WatchlistNoteType; content: string }) =>
    request<WatchlistNote>({ url: '/watchlists/notes', method: 'POST', data })
};
