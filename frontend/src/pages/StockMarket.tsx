import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { Button, Input, Select, Space, Switch, Tag, Tooltip, Typography } from 'antd';
import { PageContainer, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import type { Rating, StockMarketItem, StockMarketResponse } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

type SortKey =
  | 'ai_score'
  | 'pct_chg'
  | 'pct_chg_20'
  | 'pct_chg_60'
  | 'turnover_rate'
  | 'volume_ratio'
  | 'total_mv'
  | 'pe_ttm'
  | 'roe'
  | 'sentiment_score';

const ratingColor: Record<Rating, string> = {
  A: 'green',
  B: 'blue',
  C: 'gold',
  D: 'red'
};

const sortOptions: Array<{ label: string; value: `${SortKey}:asc` | `${SortKey}:desc` }> = [
  { label: 'AI评分降序', value: 'ai_score:desc' },
  { label: '涨跌幅降序', value: 'pct_chg:desc' },
  { label: '20日涨幅降序', value: 'pct_chg_20:desc' },
  { label: '换手率降序', value: 'turnover_rate:desc' },
  { label: '量比降序', value: 'volume_ratio:desc' },
  { label: '总市值降序', value: 'total_mv:desc' },
  { label: 'PE升序', value: 'pe_ttm:asc' },
  { label: 'ROE降序', value: 'roe:desc' },
  { label: '舆情分降序', value: 'sentiment_score:desc' }
];

function formatNumber(value?: number | null, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '-';
}

function pctText(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-';
}

const StockMarket = () => {
  const navigate = useNavigate();
  const [market, setMarket] = useState<StockMarketResponse | null>(null);
  const [keywordInput, setKeywordInput] = useState('');
  const [query, setQuery] = useState('');
  const [industry, setIndustry] = useState<string | undefined>();
  const [rating, setRating] = useState<string | undefined>();
  const [includeSt, setIncludeSt] = useState(false);
  const [includePaused, setIncludePaused] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortBy, setSortBy] = useState<SortKey>('ai_score');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
  const [selectedCodes, setSelectedCodes] = useState<string[]>([]);

  const rows = market?.rows ?? [];
  const industryOptions = useMemo(
    () => [
      { label: '全部行业', value: '全部' },
      ...(market?.industries ?? []).map((item) => ({ label: item, value: item }))
    ],
    [market?.industries]
  );

  async function loadMarket(): Promise<void> {
    const data = await api.listStockMarket({
      q: query,
      industry,
      rating,
      include_st: includeSt,
      include_paused: includePaused,
      page,
      page_size: pageSize,
      sort_by: sortBy,
      sort_order: sortOrder
    });
    setMarket(data);
    setSelectedCodes([]);
  }

  useEffect(() => {
    runSafely(loadMarket());
  }, [query, industry, rating, includeSt, includePaused, page, pageSize, sortBy, sortOrder]);

  function handleSearch(value: string): void {
    setPage(1);
    setQuery(value.trim());
  }

  function handleSortChange(value: string): void {
    const [nextSortBy, nextSortOrder] = value.split(':') as [SortKey, 'asc' | 'desc'];
    setPage(1);
    setSortBy(nextSortBy);
    setSortOrder(nextSortOrder);
  }

  async function addToWatchlist(record: StockMarketItem): Promise<void> {
    await api.addWatchlistItem({
      ts_code: record.ts_code,
      group_name: '观察池',
      reason: `来自行情选择：AI评分${record.ai_score.toFixed(1)}，涨跌幅${pctText(record.pct_chg)}`,
      tags: [record.industry ?? '未分类'],
      priority: record.rating === 'A' ? 5 : record.rating === 'B' ? 4 : 3,
      risk_level: record.sentiment_score < 45 ? 'high' : 'medium'
    });
    notifySuccess(`${record.name} 已加入自选股`);
  }

  async function batchAddToWatchlist(): Promise<void> {
    const selectedRows = rows.filter((row) => selectedCodes.includes(row.ts_code));
    for (const row of selectedRows) {
      await addToWatchlist(row);
    }
    setSelectedCodes([]);
  }

  const columns: ProColumns<StockMarketItem>[] = [
    {
      title: '代码',
      dataIndex: 'ts_code',
      width: 116,
      fixed: 'left',
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          {record.ts_code}
        </Button>
      )
    },
    {
      title: '名称',
      dataIndex: 'name',
      width: 108,
      fixed: 'left',
      render: (_, record) => (
        <Space size={4}>
          <Typography.Text strong>{record.name}</Typography.Text>
          {record.is_st ? <Tag color="red">ST</Tag> : null}
          {record.is_paused ? <Tag>停牌</Tag> : null}
        </Space>
      )
    },
    { title: '行业', dataIndex: 'industry', width: 110, ellipsis: true },
    { title: '交易日', dataIndex: 'trade_date', width: 104 },
    { title: '收盘', dataIndex: 'close', width: 82, render: (_, record) => formatNumber(record.close) },
    {
      title: '涨跌幅',
      dataIndex: 'pct_chg',
      width: 92,
      render: (_, record) => <Typography.Text type={Number(record.pct_chg ?? 0) >= 0 ? 'danger' : 'success'}>{pctText(record.pct_chg)}</Typography.Text>
    },
    { title: '20日', dataIndex: 'pct_chg_20', width: 82, render: (_, record) => pctText(record.pct_chg_20) },
    { title: '60日', dataIndex: 'pct_chg_60', width: 82, render: (_, record) => pctText(record.pct_chg_60) },
    { title: '换手率', dataIndex: 'turnover_rate', width: 86, render: (_, record) => pctText(record.turnover_rate) },
    { title: '量比', dataIndex: 'volume_ratio', width: 76, render: (_, record) => formatNumber(record.volume_ratio) },
    { title: 'PE', dataIndex: 'pe_ttm', width: 76, render: (_, record) => formatNumber(record.pe_ttm) },
    { title: 'PB', dataIndex: 'pb', width: 76, render: (_, record) => formatNumber(record.pb) },
    { title: 'ROE', dataIndex: 'roe', width: 82, render: (_, record) => pctText(record.roe) },
    { title: '流通市值', dataIndex: 'circ_mv', width: 104, render: (_, record) => formatNumber(record.circ_mv, 0) },
    {
      title: '舆情',
      dataIndex: 'sentiment_score',
      width: 112,
      render: (_, record) => <Tag color={record.sentiment_score >= 60 ? 'green' : record.sentiment_score >= 40 ? 'gold' : 'red'}>{record.sentiment_label} {record.sentiment_score.toFixed(0)}</Tag>
    },
    {
      title: 'AI评分',
      dataIndex: 'ai_score',
      width: 98,
      fixed: 'right',
      render: (_, record) => <Tag color={ratingColor[record.rating]} className="score-badge">{record.rating} {record.ai_score.toFixed(1)}</Tag>
    },
    {
      title: '操作',
      valueType: 'option',
      width: 132,
      fixed: 'right',
      render: (_, record) => [
        <Button key="detail" type="link" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          详情
        </Button>,
        <Button key="add" type="link" icon={<PlusOutlined />} onClick={() => runSafely(addToWatchlist(record))}>
          自选
        </Button>
      ]
    }
  ];

  return (
    <PageContainer
      title="股票行情选择"
      extra={[
        <Button key="batch" type="primary" disabled={!selectedCodes.length} icon={<PlusOutlined />} onClick={() => runSafely(batchAddToWatchlist())}>
          批量加入自选
        </Button>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(loadMarket())}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <div className="market-toolbar">
          <Input.Search
            allowClear
            enterButton={<SearchOutlined />}
            value={keywordInput}
            onChange={(event) => setKeywordInput(event.target.value)}
            onSearch={handleSearch}
            placeholder="搜索股票代码、名称、拼音代码或行业"
            style={{ width: 360, maxWidth: '100%' }}
          />
          <Select
            value={industry ?? '全部'}
            onChange={(value) => {
              setPage(1);
              setIndustry(value === '全部' ? undefined : value);
            }}
            options={industryOptions}
            showSearch
            style={{ width: 180 }}
          />
          <Select
            value={rating ?? '全部'}
            onChange={(value) => {
              setPage(1);
              setRating(value === '全部' ? undefined : value);
            }}
            options={[
              { label: '全部评级', value: '全部' },
              { label: 'A', value: 'A' },
              { label: 'B', value: 'B' },
              { label: 'C', value: 'C' },
              { label: 'D', value: 'D' }
            ]}
            style={{ width: 120 }}
          />
          <Select value={`${sortBy}:${sortOrder}`} onChange={handleSortChange} options={sortOptions} style={{ width: 160 }} />
          <Space size={6}>
            <Typography.Text type="secondary">含ST</Typography.Text>
            <Switch checked={includeSt} onChange={(checked) => { setPage(1); setIncludeSt(checked); }} />
          </Space>
          <Space size={6}>
            <Typography.Text type="secondary">含停牌</Typography.Text>
            <Switch checked={includePaused} onChange={(checked) => { setPage(1); setIncludePaused(checked); }} />
          </Space>
        </div>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '匹配股票', value: market?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '因子缓存', value: market?.factor_universe_count ?? 0 }} />
          <StatisticCard statistic={{ title: '最新交易日', value: market?.latest_trade_date ?? '-' }} />
          <StatisticCard statistic={{ title: '本页选择', value: selectedCodes.length }} />
        </StatisticCard.Group>
        <ProTable<StockMarketItem>
          rowKey="ts_code"
          cardBordered
          search={false}
          options={false}
          columns={columns}
          dataSource={rows}
          scroll={{ x: 1580 }}
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
          rowSelection={{
            selectedRowKeys: selectedCodes,
            onChange: (keys) => setSelectedCodes(keys.map(String))
          }}
          onRow={(record) => ({
            onDoubleClick: () => navigate(`/stock/${record.ts_code}`)
          })}
        />
      </Space>
    </PageContainer>
  );
};

export default StockMarket;
