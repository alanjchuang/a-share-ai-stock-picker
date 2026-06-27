import { ArrowLeftOutlined, DatabaseOutlined, ReloadOutlined, StarOutlined } from '@ant-design/icons';
import { Alert, Button, Descriptions, Empty, List, Space, Table, Tag, Typography } from 'antd';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import type { ColumnsType } from 'antd/es/table';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/modules';
import type { FinancialSnapshot, StockDetail as StockDetailType } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

function formatNumber(value?: number | null, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '-';
}

function pctText(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-';
}

function klineOption(detail: StockDetailType): EChartsOption {
  const dates = detail.kline.map((item) => item.trade_date);
  return {
    tooltip: { trigger: 'axis' },
    legend: { data: ['K线', 'MA5', 'MA10', 'MA20', 'MA60', '成交量'] },
    grid: [
      { left: 48, right: 28, top: 40, height: 260 },
      { left: 48, right: 28, top: 328, height: 72 }
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: false },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } }
    ],
    yAxis: [{ scale: true }, { gridIndex: 1 }],
    dataZoom: [{ type: 'inside' }, { show: true, bottom: 2, height: 18 }],
    series: [
      { name: 'K线', type: 'candlestick', data: detail.kline.map((item) => [item.open, item.close, item.low, item.high]) },
      { name: 'MA5', type: 'line', data: detail.kline.map((item) => item.ma5), showSymbol: false },
      { name: 'MA10', type: 'line', data: detail.kline.map((item) => item.ma10), showSymbol: false },
      { name: 'MA20', type: 'line', data: detail.kline.map((item) => item.ma20), showSymbol: false },
      { name: 'MA60', type: 'line', data: detail.kline.map((item) => item.ma60), showSymbol: false },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: detail.kline.map((item) => item.volume), itemStyle: { color: '#5b8c85' } }
    ]
  };
}

function radarOption(detail: StockDetailType): EChartsOption {
  return {
    tooltip: {},
    radar: {
      indicator: Object.keys(detail.radar).map((name) => ({ name, max: 100 })),
      radius: 100
    },
    series: [
      {
        type: 'radar',
        data: [{ name: '四维度评分', value: Object.values(detail.radar).map((value) => Math.max(0, Math.min(100, value))) }],
        areaStyle: { opacity: 0.18 }
      }
    ]
  };
}

function financialOption(history: FinancialSnapshot[]): EChartsOption {
  const rows = history.slice().sort((a, b) => a.report_date.localeCompare(b.report_date));
  const dates = rows.map((item) => item.report_date);
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, type: 'scroll', data: ['市盈率(TTM)', 'ROE', '净利率', '营收同比', '扣非净利同比'] },
    grid: { left: 52, right: 52, top: 42, bottom: 38 },
    xAxis: { type: 'category', data: dates },
    yAxis: [
      { type: 'value', name: '百分比', axisLabel: { formatter: '{value}%' } },
      { type: 'value', name: '倍数', alignTicks: true }
    ],
    series: [
      { name: '市盈率(TTM)', type: 'line', yAxisIndex: 1, smooth: true, data: rows.map((item) => item.pe_ttm ?? null) },
      { name: 'ROE', type: 'line', smooth: true, data: rows.map((item) => item.roe ?? null) },
      { name: '净利率', type: 'line', smooth: true, data: rows.map((item) => item.netprofit_margin ?? null) },
      { name: '营收同比', type: 'line', smooth: true, data: rows.map((item) => item.revenue_yoy ?? null) },
      { name: '扣非净利同比', type: 'line', smooth: true, data: rows.map((item) => item.deduct_profit_yoy ?? null) }
    ]
  };
}

const financialColumns: ColumnsType<FinancialSnapshot> = [
  { title: '报告日', dataIndex: 'report_date', width: 104, fixed: 'left' },
  { title: '市盈率', dataIndex: 'pe_ttm', width: 92, render: (value) => formatNumber(value as number | null) },
  { title: 'PB', dataIndex: 'pb', width: 76, render: (value) => formatNumber(value as number | null) },
  { title: 'ROE', dataIndex: 'roe', width: 86, render: (value) => pctText(value as number | null) },
  { title: '毛利率', dataIndex: 'gross_margin', width: 92, render: (value) => pctText(value as number | null) },
  { title: '净利率', dataIndex: 'netprofit_margin', width: 92, render: (value) => pctText(value as number | null) },
  { title: '营收同比', dataIndex: 'revenue_yoy', width: 98, render: (value) => pctText(value as number | null) },
  { title: '扣非净利同比', dataIndex: 'deduct_profit_yoy', width: 122, render: (value) => pctText(value as number | null) },
  { title: '资产负债率', dataIndex: 'debt_to_assets', width: 110, render: (value) => pctText(value as number | null) },
  { title: '股息率', dataIndex: 'dividend_yield', width: 92, render: (value) => pctText(value as number | null) }
];

const StockDetail = () => {
  const { tsCode } = useParams<{ tsCode: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<StockDetailType | null>(null);

  const load = () => {
    if (tsCode) runSafely(api.getStockDetail(tsCode).then(setDetail));
  };

  useEffect(load, [tsCode]);

  const metricCards = useMemo(() => {
    if (!detail) return [];
    return [
      { title: 'AI评分', value: detail.base.ai_score.toFixed(1), suffix: detail.base.rating },
      { title: '市盈率(TTM)', value: formatNumber(detail.base.pe_ttm) },
      { title: 'PB', value: detail.base.pb?.toFixed(2) ?? '-' },
      { title: 'ROE', value: pctText(detail.base.roe) },
      { title: '营收同比', value: pctText(detail.base.revenue_yoy) },
      { title: '舆情分', value: detail.base.sentiment_score.toFixed(0), suffix: detail.base.sentiment_label }
    ];
  }, [detail]);

  const financialRows = useMemo(
    () => [...(detail?.financial_history ?? [])].sort((a, b) => b.report_date.localeCompare(a.report_date)),
    [detail]
  );

  const needsHistorySync = useMemo(() => {
    if (!detail) return false;
    return detail.kline.length < 30 || detail.data_warnings.some((warning) => warning.includes('K线'));
  }, [detail]);

  async function addToWatchlist(): Promise<void> {
    if (!detail) return;
    await api.addWatchlistItem({
      ts_code: detail.base.ts_code,
      group_name: '观察池',
      reason: `来自个股详情：AI评分${detail.base.ai_score.toFixed(1)}，评级${detail.base.rating}`,
      tags: [detail.base.industry ?? '未分类'].filter(Boolean),
      priority: detail.base.rating === 'A' ? 5 : detail.base.rating === 'B' ? 4 : 3,
      risk_level: detail.base.sentiment_score < 45 ? 'high' : 'medium'
    });
    notifySuccess(`${detail.base.name} 已加入自选股`);
  }

  if (!tsCode) return <Empty description="请从工作台选择一只股票" />;

  return (
    <PageContainer
      title={detail ? `${detail.base.name}（${detail.base.ts_code}）` : tsCode}
      extra={[
        <Button key="back" icon={<ArrowLeftOutlined />} onClick={() => navigate('/')}>
          返回工作台
        </Button>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={load}>
          刷新
        </Button>,
        <Button key="watch" type="primary" icon={<StarOutlined />} onClick={() => runSafely(addToWatchlist())} disabled={!detail}>
          加入自选
        </Button>
      ]}
    >
      {detail ? (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            showIcon
            type={detail.data_warnings.length ? 'warning' : 'info'}
            message={`行情来源：${detail.data_source}`}
            description={detail.data_warnings.length ? detail.data_warnings.join('；') : '行情、财务和因子均来自本地SQLite缓存；可在数据中心查看同步状态和缓存覆盖。'}
            action={
              needsHistorySync ? (
                <Button size="small" icon={<DatabaseOutlined />} onClick={() => navigate('/data')}>
                  全市场补齐K线
                </Button>
              ) : undefined
            }
          />
          <StatisticCard.Group>
            {metricCards.map((item) => (
              <StatisticCard key={item.title} statistic={item} />
            ))}
          </StatisticCard.Group>
          <ProCard bordered title="基础信息">
            <Descriptions column={{ xs: 1, sm: 2, md: 4 }} size="small">
              <Descriptions.Item label="行业">{detail.base.industry}</Descriptions.Item>
              <Descriptions.Item label="所属指数">{detail.base.index_names.join(' / ')}</Descriptions.Item>
              <Descriptions.Item label="最新收盘">{formatNumber(detail.base.close)}</Descriptions.Item>
              <Descriptions.Item label="涨跌幅">{pctText(detail.base.pct_chg)}</Descriptions.Item>
              <Descriptions.Item label="市盈率(TTM)">{formatNumber(detail.base.pe_ttm)}</Descriptions.Item>
              <Descriptions.Item label="PB">{formatNumber(detail.base.pb)}</Descriptions.Item>
              <Descriptions.Item label="ROE">{pctText(detail.base.roe)}</Descriptions.Item>
              <Descriptions.Item label="营收同比">{pctText(detail.base.revenue_yoy)}</Descriptions.Item>
              <Descriptions.Item label="流通市值">{formatNumber(detail.base.circ_mv, 0)}亿</Descriptions.Item>
              <Descriptions.Item label="主力净流入">{formatNumber(detail.base.main_net_inflow)}</Descriptions.Item>
              <Descriptions.Item label="评级">
                <Tag color={detail.base.rating === 'A' ? 'green' : detail.base.rating === 'B' ? 'blue' : 'gold'}>{detail.base.rating}</Tag>
              </Descriptions.Item>
            </Descriptions>
          </ProCard>
          <ProCard split="vertical" bordered>
            <ProCard title="财务趋势" colSpan="55%">
              {financialRows.length ? (
                <ReactECharts option={financialOption(detail.financial_history)} style={{ height: 320 }} notMerge />
              ) : (
                <Empty description="暂无财务历史" />
              )}
            </ProCard>
            <ProCard title="财务明细">
              <Table<FinancialSnapshot>
                rowKey="report_date"
                size="small"
                columns={financialColumns}
                dataSource={financialRows}
                pagination={false}
                scroll={{ x: 960, y: 270 }}
              />
            </ProCard>
          </ProCard>
          <ProCard split="vertical" bordered>
            <ProCard title="120日K线" colSpan="70%">
              <ReactECharts option={klineOption(detail)} style={{ height: 430 }} notMerge />
            </ProCard>
            <ProCard title="四维度因子雷达">
              <ReactECharts option={radarOption(detail)} style={{ height: 430 }} notMerge />
            </ProCard>
          </ProCard>
          <ProCard bordered title="近15日新闻与公告舆情" className="news-list">
            <List
              dataSource={detail.news.slice(0, 15)}
              locale={{ emptyText: '暂无新闻' }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={
                      <Space wrap>
                        <Typography.Text strong>{item.title}</Typography.Text>
                        <Tag color={item.sentiment_score >= 60 ? 'green' : item.sentiment_score >= 40 ? 'gold' : 'red'}>
                          {item.sentiment_label} {item.sentiment_score.toFixed(0)}
                        </Tag>
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={4}>
                        <Typography.Text type="secondary">
                          {item.publish_time} · {item.source ?? 'unknown'} · {item.keywords.join(' / ')}
                        </Typography.Text>
                        <Typography.Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>{item.content}</Typography.Paragraph>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </ProCard>
        </Space>
      ) : (
        <Empty description="正在加载或未找到股票" />
      )}
    </PageContainer>
  );
};

export default StockDetail;
