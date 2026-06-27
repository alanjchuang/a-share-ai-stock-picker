import { CloudDownloadOutlined, LineChartOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Alert, Button, Drawer, Empty, Input, Select, Space, Tag, Typography } from 'antd';
import { PageContainer, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/modules';
import type { EtfDetail, EtfMarketItem, EtfMarketResponse, SyncJobOut } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

type EtfSortKey = 'amount' | 'pct_chg' | 'pct_chg_20' | 'pct_chg_60' | 'pct_chg_120' | 'turnover_rate' | 'total_mv' | 'discount_rate' | 'volatility_60' | 'max_drawdown_120';

const sortOptions: Array<{ label: string; value: `${EtfSortKey}:asc` | `${EtfSortKey}:desc` }> = [
  { label: '成交额降序', value: 'amount:desc' },
  { label: '涨跌幅降序', value: 'pct_chg:desc' },
  { label: '20日涨幅降序', value: 'pct_chg_20:desc' },
  { label: '60日涨幅降序', value: 'pct_chg_60:desc' },
  { label: '规模降序', value: 'total_mv:desc' },
  { label: '折价率升序', value: 'discount_rate:asc' },
  { label: '波动率升序', value: 'volatility_60:asc' },
  { label: '回撤较小优先', value: 'max_drawdown_120:desc' }
];

const categoryColor: Record<string, string> = {
  宽基指数: 'blue',
  行业主题: 'purple',
  跨境: 'cyan',
  债券: 'green',
  商品: 'gold',
  货币: 'lime'
};

function formatNumber(value?: number | null, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '-';
}

function amountText(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-';
  return `${(value / 100000000).toFixed(2)}亿`;
}

function pctText(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-';
}

function klineOption(detail: EtfDetail | null): EChartsOption {
  const kline = detail?.kline ?? [];
  const dates = kline.map((item) => item.trade_date);
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['K线', 'MA5', 'MA20', 'MA60', '成交额'] },
    grid: [
      { left: 48, right: 28, top: 42, height: 260 },
      { left: 48, right: 28, top: 328, height: 72 }
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: false },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } }
    ],
    yAxis: [{ scale: true }, { gridIndex: 1 }],
    dataZoom: [{ type: 'inside' }, { show: true, bottom: 2, height: 18 }],
    series: [
      { name: 'K线', type: 'candlestick', data: kline.map((item) => [item.open, item.close, item.low, item.high]) },
      { name: 'MA5', type: 'line', data: kline.map((item) => item.ma5), showSymbol: false },
      { name: 'MA20', type: 'line', data: kline.map((item) => item.ma20), showSymbol: false },
      { name: 'MA60', type: 'line', data: kline.map((item) => item.ma60), showSymbol: false },
      { name: '成交额', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: kline.map((item) => item.amount), itemStyle: { color: '#6b7280' } }
    ]
  };
}

const EtfCenter = () => {
  const [market, setMarket] = useState<EtfMarketResponse | null>(null);
  const [detail, setDetail] = useState<EtfDetail | null>(null);
  const [keywordInput, setKeywordInput] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortBy, setSortBy] = useState<EtfSortKey>('amount');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [syncing, setSyncing] = useState(false);
  const [activeJob, setActiveJob] = useState<SyncJobOut | null>(null);
  const [lastEtfJobId, setLastEtfJobId] = useState<number | null>(null);

  const rows = market?.rows ?? [];
  const categoryOptions = useMemo(
    () => [
      { label: '全部类型', value: '全部' },
      ...(market?.categories ?? []).map((item) => ({ label: item, value: item }))
    ],
    [market?.categories]
  );

  async function load(forceRefresh = false): Promise<void> {
    const data = await api.listEtfs({
      q: query,
      category,
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_order: sortOrder
    }, { forceRefresh });
    setMarket(data);
  }

  async function loadActiveJob(): Promise<void> {
    const job = await api.getActiveSyncJob();
    setActiveJob(job);
    if (!job && lastEtfJobId) {
      setLastEtfJobId(null);
      await load(true);
    }
  }

  async function openDetail(record: EtfMarketItem): Promise<void> {
    const data = await api.getEtfDetail(record.etf_code);
    setDetail(data);
  }

  async function syncEtfs(): Promise<void> {
    setSyncing(true);
    try {
      const job = await api.syncEtfs(0);
      notifySuccess(job.message);
      setLastEtfJobId(job.job_id ?? null);
      await loadActiveJob();
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    runSafely(load());
  }, [query, category, page, pageSize, sortBy, sortOrder]);

  useEffect(() => {
    runSafely(loadActiveJob());
  }, []);

  useEffect(() => {
    if (!activeJob && !lastEtfJobId) return undefined;
    const timer = window.setInterval(() => runSafely(loadActiveJob()), 3000);
    return () => window.clearInterval(timer);
  }, [activeJob?.id, activeJob?.status, lastEtfJobId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1);
      setQuery(keywordInput.trim());
    }, 350);
    return () => window.clearTimeout(timer);
  }, [keywordInput]);

  function handleSortChange(value: string): void {
    const [nextSortBy, nextSortOrder] = value.split(':') as [EtfSortKey, 'asc' | 'desc'];
    setPage(1);
    setSortBy(nextSortBy);
    setSortOrder(nextSortOrder);
  }

  const columns: ProColumns<EtfMarketItem>[] = [
    {
      title: '代码',
      dataIndex: 'etf_code',
      width: 116,
      fixed: 'left',
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => runSafely(openDetail(record))}>
          {record.etf_code}
        </Button>
      )
    },
    { title: '名称', dataIndex: 'name', width: 180, fixed: 'left', ellipsis: true },
    {
      title: '类型',
      dataIndex: 'category',
      width: 96,
      render: (_, record) => <Tag color={categoryColor[record.category] ?? 'default'}>{record.category}</Tag>
    },
    { title: '交易日', dataIndex: 'trade_date', width: 104 },
    { title: '收盘', dataIndex: 'close', width: 82, render: (_, record) => formatNumber(record.close, 3) },
    {
      title: '涨跌幅',
      dataIndex: 'pct_chg',
      width: 92,
      render: (_, record) => <Typography.Text type={Number(record.pct_chg ?? 0) >= 0 ? 'danger' : 'success'}>{pctText(record.pct_chg)}</Typography.Text>
    },
    { title: '20日', dataIndex: 'pct_chg_20', width: 82, render: (_, record) => pctText(record.pct_chg_20) },
    { title: '60日', dataIndex: 'pct_chg_60', width: 82, render: (_, record) => pctText(record.pct_chg_60) },
    { title: '120日', dataIndex: 'pct_chg_120', width: 88, render: (_, record) => pctText(record.pct_chg_120) },
    { title: '成交额', dataIndex: 'amount', width: 96, render: (_, record) => amountText(record.amount) },
    { title: '换手率', dataIndex: 'turnover_rate', width: 86, render: (_, record) => pctText(record.turnover_rate) },
    { title: '折价率', dataIndex: 'discount_rate', width: 86, render: (_, record) => pctText(record.discount_rate) },
    { title: '60日波动', dataIndex: 'volatility_60', width: 96, render: (_, record) => pctText(record.volatility_60) },
    { title: '120日回撤', dataIndex: 'max_drawdown_120', width: 104, render: (_, record) => pctText(record.max_drawdown_120) },
    { title: '规模', dataIndex: 'total_mv', width: 92, render: (_, record) => (record.total_mv ? `${record.total_mv.toFixed(1)}亿` : '-') },
    {
      title: '操作',
      valueType: 'option',
      width: 88,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" icon={<LineChartOutlined />} onClick={() => runSafely(openDetail(record))}>
          K线
        </Button>
      )
    }
  ];

  return (
    <PageContainer
      title="ETF中心"
      extra={[
        <Button key="sync" type="primary" icon={<CloudDownloadOutlined />} loading={syncing || activeJob?.job_type === 'etf_sync'} disabled={Boolean(activeJob && activeJob.job_type !== 'etf_sync')} onClick={() => runSafely(syncEtfs())}>
          同步ETF数据
        </Button>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(load(true))}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {activeJob ? (
          <Alert
            showIcon
            type={activeJob.job_type === 'etf_sync' ? 'info' : 'warning'}
            message={activeJob.job_type === 'etf_sync' ? 'ETF数据正在后台同步' : '后台数据任务正在运行'}
            description={activeJob.message}
          />
        ) : null}
        {market?.total ? null : (
          <Alert showIcon type="info" message="ETF数据尚未同步" description="点击右上角“同步ETF数据”后，会从 AKShare 拉取ETF实时行情、分类净值和历史K线。ETF不会混入股票多因子选股池。" />
        )}
        <div className="market-toolbar">
          <Input.Search
            allowClear
            enterButton={<SearchOutlined />}
            value={keywordInput}
            onChange={(event) => setKeywordInput(event.target.value)}
            onSearch={(value) => {
              setPage(1);
              setQuery(value.trim());
            }}
            placeholder="搜索ETF代码、名称或类型，例如 沪深300 / 510300"
            style={{ width: 360, maxWidth: '100%' }}
          />
          <Select
            value={category ?? '全部'}
            onChange={(value) => {
              setPage(1);
              setCategory(value === '全部' ? undefined : value);
            }}
            options={categoryOptions}
            style={{ width: 140 }}
          />
          <Select value={`${sortBy}:${sortOrder}`} onChange={handleSortChange} options={sortOptions} style={{ width: 160 }} />
        </div>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '匹配ETF', value: market?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '最新交易日', value: market?.latest_trade_date ?? '-' }} />
          <StatisticCard statistic={{ title: '分类数量', value: market?.categories.length ?? 0 }} />
          <StatisticCard statistic={{ title: '当前页', value: rows.length }} />
        </StatisticCard.Group>
        <ProTable<EtfMarketItem>
          rowKey="etf_code"
          cardBordered
          search={false}
          options={false}
          columns={columns}
          dataSource={rows}
          scroll={{ x: 1500 }}
          pagination={{
            current: page,
            pageSize,
            total: market?.total ?? 0,
            showSizeChanger: true,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage);
              setPageSize(nextPageSize);
            }
          }}
          onRow={(record) => ({
            onDoubleClick: () => runSafely(openDetail(record))
          })}
        />
      </Space>
      <Drawer width={920} open={Boolean(detail)} onClose={() => setDetail(null)} title={detail ? `${detail.base.name}（${detail.base.etf_code}）` : 'ETF详情'}>
        {detail ? (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {detail.data_warnings.length ? <Alert showIcon type="warning" message={detail.data_warnings.join('；')} /> : null}
            <StatisticCard.Group>
              <StatisticCard statistic={{ title: '收盘', value: formatNumber(detail.base.close, 3) }} />
              <StatisticCard statistic={{ title: '涨跌幅', value: pctText(detail.base.pct_chg) }} />
              <StatisticCard statistic={{ title: '成交额', value: amountText(detail.base.amount) }} />
              <StatisticCard statistic={{ title: '折价率', value: pctText(detail.base.discount_rate) }} />
            </StatisticCard.Group>
            {detail.kline.length ? <ReactECharts option={klineOption(detail)} style={{ height: 430 }} notMerge /> : <Empty description="暂无ETF K线" />}
          </Space>
        ) : null}
      </Drawer>
    </PageContainer>
  );
};

export default EtfCenter;
