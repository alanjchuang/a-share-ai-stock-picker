import { ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Space, Tag, Typography } from 'antd';
import { PageContainer, ProCard, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import type { DecisionDashboardResponse, IndustryHeatItem, Rating, StockScore } from '../types';
import { runSafely } from '../utils/async';

const ratingColor: Record<Rating, string> = {
  A: 'green',
  B: 'blue',
  C: 'gold',
  D: 'red'
};

function pct(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-';
}

function buildBreadthOption(data: DecisionDashboardResponse | null): EChartsOption {
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0 },
    series: [
      {
        name: '涨跌家数',
        type: 'pie',
        radius: ['45%', '70%'],
        center: ['50%', '44%'],
        data: [
          { name: '上涨', value: data?.up_count ?? 0, itemStyle: { color: '#cf1322' } },
          { name: '下跌', value: data?.down_count ?? 0, itemStyle: { color: '#389e0d' } },
          { name: '平盘', value: data?.flat_count ?? 0, itemStyle: { color: '#8c8c8c' } }
        ]
      }
    ]
  };
}

function buildIndustryOption(items: IndustryHeatItem[]): EChartsOption {
  const names = items.map((item) => item.industry);
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 20, top: 24, bottom: 58 },
    xAxis: { type: 'category', data: names, axisLabel: { rotate: 32 } },
    yAxis: { type: 'value' },
    series: [
      {
        name: '行业平均涨跌幅',
        type: 'bar',
        data: items.map((item) => item.avg_pct_chg),
        itemStyle: { color: '#1f7a8c' }
      }
    ]
  };
}

const DecisionDashboard = () => {
  const navigate = useNavigate();
  const [data, setData] = useState<DecisionDashboardResponse | null>(null);

  async function load(): Promise<void> {
    setData(await api.getDecisionDashboard(8));
  }

  useEffect(() => {
    runSafely(load());
  }, []);

  const stockColumns: ProColumns<StockScore>[] = [
    {
      title: '股票',
      dataIndex: 'ts_code',
      width: 160,
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          {record.name} · {record.ts_code}
        </Button>
      )
    },
    { title: '行业', dataIndex: 'industry', width: 110, ellipsis: true },
    { title: '涨跌幅', dataIndex: 'pct_chg', width: 86, render: (_, record) => <Typography.Text type={Number(record.pct_chg ?? 0) >= 0 ? 'danger' : 'success'}>{pct(record.pct_chg)}</Typography.Text> },
    { title: 'PE', dataIndex: 'pe_ttm', width: 72, render: (_, record) => record.pe_ttm?.toFixed(2) ?? '-' },
    {
      title: '舆情',
      dataIndex: 'sentiment_score',
      width: 108,
      render: (_, record) => <Tag color={record.sentiment_score >= 60 ? 'green' : record.sentiment_score >= 40 ? 'gold' : 'red'}>{record.sentiment_label} {record.sentiment_score.toFixed(0)}</Tag>
    },
    {
      title: 'AI评分',
      dataIndex: 'ai_score',
      width: 92,
      render: (_, record) => <Tag color={ratingColor[record.rating]} className="score-badge">{record.rating} {record.ai_score.toFixed(1)}</Tag>
    }
  ];

  const industryColumns: ProColumns<IndustryHeatItem>[] = [
    { title: '行业', dataIndex: 'industry', width: 130 },
    { title: '数量', dataIndex: 'count', width: 72 },
    { title: '平均涨跌幅', dataIndex: 'avg_pct_chg', width: 112, render: (_, record) => pct(record.avg_pct_chg) },
    { title: '上涨占比', dataIndex: 'up_ratio', width: 96, render: (_, record) => pct(record.up_ratio) },
    { title: '平均AI评分', dataIndex: 'avg_ai_score', width: 108, render: (_, record) => record.avg_ai_score.toFixed(1) }
  ];

  const strategyTags = useMemo(
    () =>
      (data?.strategy_hits ?? []).map((item) => (
        <Tag key={String(item.key)} color={Number(item.count ?? 0) > 0 ? 'blue' : 'default'}>
          {String(item.name)} {Number(item.count ?? 0)}
        </Tag>
      )),
    [data?.strategy_hits]
  );

  return (
    <PageContainer
      title="决策仪表盘"
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(load())}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert showIcon type="info" message={data?.market_view ?? '正在读取本地行情缓存'} />
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '股票池', value: data?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '上涨/下跌', value: `${data?.up_count ?? 0}/${data?.down_count ?? 0}` }} />
          <StatisticCard statistic={{ title: '平均涨跌幅', value: pct(data?.avg_pct_chg) }} />
          <StatisticCard statistic={{ title: '平均AI评分', value: data?.avg_ai_score?.toFixed(1) ?? '0.0' }} />
          <StatisticCard statistic={{ title: '涨停/跌停', value: `${data?.limit_up_count ?? 0}/${data?.limit_down_count ?? 0}` }} />
        </StatisticCard.Group>
        <div className="dashboard-grid">
          <ProCard title="涨跌分布" bordered>
            <ReactECharts className="chart-panel compact-chart" option={buildBreadthOption(data)} notMerge />
          </ProCard>
          <ProCard title="行业热度" bordered>
            <ReactECharts className="chart-panel compact-chart" option={buildIndustryOption(data?.industry_heat ?? [])} notMerge />
          </ProCard>
        </div>
        <ProCard title="风险警报" bordered>
          <Space direction="vertical" size={8}>
            {(data?.risk_alerts ?? []).map((item) => (
              <Typography.Text key={item} type={item.includes('未发现') ? 'secondary' : 'warning'}>
                {item}
              </Typography.Text>
            ))}
            <Space wrap>{strategyTags}</Space>
          </Space>
        </ProCard>
        <div className="dashboard-grid">
          <ProTable<StockScore> rowKey="ts_code" cardBordered search={false} options={false} size="small" columns={stockColumns} dataSource={data?.top_ai ?? []} pagination={false} headerTitle="AI评分靠前" />
          <ProTable<StockScore> rowKey="ts_code" cardBordered search={false} options={false} size="small" columns={stockColumns} dataSource={data?.top_gainers ?? []} pagination={false} headerTitle="涨幅靠前" />
          <ProTable<IndustryHeatItem> rowKey="industry" cardBordered search={false} options={false} size="small" columns={industryColumns} dataSource={data?.industry_heat ?? []} pagination={false} headerTitle="行业强弱" />
          <ProTable<StockScore> rowKey="ts_code" cardBordered search={false} options={false} size="small" columns={stockColumns} dataSource={data?.high_risk ?? []} pagination={false} headerTitle="风险复核" />
        </div>
      </Space>
    </PageContainer>
  );
};

export default DecisionDashboard;
