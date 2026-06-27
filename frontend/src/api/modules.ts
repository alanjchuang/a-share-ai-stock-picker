import { request } from './http';
import type {
  AppConfig,
  IndexMeta,
  ScreeningRequest,
  ScreeningResult,
  StockSelectionWorkflowResult,
  StockDetail,
  StrategyOut,
  WebSearchRequest,
  WebSearchResponse,
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
  listIndices: () => request<IndexMeta[]>({ url: '/meta/indices', method: 'GET' }),
  runScreener: (data: ScreeningRequest) => request<ScreeningResult>({ url: '/screener/run', method: 'POST', data }),
  parseText: (text: string) => request<ScreeningRequest>({ url: '/ai/parse', method: 'POST', data: { text } }),
  runSelectionWorkflow: (text: string, workflowPath?: string) =>
    request<StockSelectionWorkflowResult>({
      url: '/ai/stock-selection-workflow',
      method: 'POST',
      data: { text, workflow_path: workflowPath }
    }),
  listWorkflows: () => request<WorkflowInfo[]>({ url: '/ai/workflows', method: 'GET' }),
  searchWeb: (data: WebSearchRequest) => request<WebSearchResponse>({ url: '/ai/search', method: 'POST', data }),
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
    request<Record<string, unknown>>({
      url: '/sync/run',
      method: 'POST',
      data: { provider, sync_news: true, sync_fundamentals: true, sync_indices: true }
    }),
  calculateFactors: () => request<{ count: number }>({ url: '/factors/calculate', method: 'POST' })
};
