import { ReloadOutlined } from '@ant-design/icons';
import { Button, Select, Space, Tag, Typography } from 'antd';
import { PageContainer, ProCard, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import type { KlinePatternHit, PatternRadarResponse, Rating } from '../types';
import { runSafely } from '../utils/async';

const signalColor: Record<string, string> = {
  bullish: 'red',
  bearish: 'green',
  neutral: 'blue'
};

const ratingColor: Record<Rating, string> = {
  A: 'green',
  B: 'blue',
  C: 'gold',
  D: 'red'
};

function pct(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-';
}

function buildDistributionOption(data: PatternRadarResponse | null): EChartsOption {
  const entries = Object.entries(data?.distribution ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 12);
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 20, top: 24, bottom: 58 },
    xAxis: { type: 'category', data: entries.map(([name]) => name), axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' },
    series: [{ name: '形态数量', type: 'bar', data: entries.map(([, value]) => value), itemStyle: { color: '#5468ff' } }]
  };
}

const PatternRadar = () => {
  const navigate = useNavigate();
  const [signal, setSignal] = useState<'all' | 'bullish' | 'bearish' | 'neutral'>('all');
  const [data, setData] = useState<PatternRadarResponse | null>(null);

  async function load(): Promise<void> {
    setData(await api.getPatternRadar({ limit: 160, signal }));
  }

  useEffect(() => {
    runSafely(load());
  }, [signal]);

  const columns: ProColumns<KlinePatternHit>[] = [
    {
      title: '股票',
      dataIndex: 'ts_code',
      width: 160,
      fixed: 'left',
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          {record.name} · {record.ts_code}
        </Button>
      )
    },
    { title: '行业', dataIndex: 'industry', width: 110, ellipsis: true },
    { title: '形态', dataIndex: 'pattern', width: 110, render: (_, record) => <Tag color={signalColor[record.signal]}>{record.pattern}</Tag> },
    { title: '信号', dataIndex: 'signal', width: 86, render: (_, record) => <Tag color={signalColor[record.signal]}>{record.signal}</Tag> },
    { title: '强度', dataIndex: 'strength', width: 82, sorter: (a, b) => a.strength - b.strength, render: (_, record) => record.strength.toFixed(1) },
    { title: '交易日', dataIndex: 'trade_date', width: 100 },
    { title: '收盘', dataIndex: 'close', width: 82, render: (_, record) => record.close?.toFixed(2) ?? '-' },
    { title: '涨跌幅', dataIndex: 'pct_chg', width: 90, render: (_, record) => <Typography.Text type={Number(record.pct_chg ?? 0) >= 0 ? 'danger' : 'success'}>{pct(record.pct_chg)}</Typography.Text> },
    {
      title: 'AI评分',
      dataIndex: ['stock', 'ai_score'],
      width: 96,
      render: (_, record) => record.stock ? <Tag color={ratingColor[record.stock.rating]} className="score-badge">{record.stock.rating} {record.stock.ai_score.toFixed(1)}</Tag> : '-'
    },
    { title: '说明', dataIndex: 'reason', ellipsis: true },
    {
      title: '操作',
      valueType: 'option',
      width: 80,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          详情
        </Button>
      )
    }
  ];

  return (
    <PageContainer
      title="K线形态雷达"
      extra={[
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(load())}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <ProCard bordered>
          <div className="market-toolbar">
            <Select
              value={signal}
              onChange={setSignal}
              options={[
                { label: '全部信号', value: 'all' },
                { label: '看多形态', value: 'bullish' },
                { label: '看空形态', value: 'bearish' },
                { label: '中性形态', value: 'neutral' }
              ]}
              style={{ width: 140 }}
            />
            <Typography.Text type="secondary">最新交易日：{data?.latest_trade_date ?? '-'}</Typography.Text>
          </div>
        </ProCard>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '形态信号', value: data?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '看多', value: data?.rows.filter((item) => item.signal === 'bullish').length ?? 0 }} />
          <StatisticCard statistic={{ title: '看空', value: data?.rows.filter((item) => item.signal === 'bearish').length ?? 0 }} />
          <StatisticCard statistic={{ title: '中性', value: data?.rows.filter((item) => item.signal === 'neutral').length ?? 0 }} />
        </StatisticCard.Group>
        <ProCard title="形态分布" bordered>
          <ReactECharts className="chart-panel compact-chart" option={buildDistributionOption(data)} notMerge />
        </ProCard>
        <ProTable<KlinePatternHit>
          rowKey={(record) => `${record.ts_code}-${record.pattern}-${record.signal}`}
          cardBordered
          search={false}
          options={false}
          columns={columns}
          dataSource={data?.rows ?? []}
          scroll={{ x: 1180 }}
          pagination={{ pageSize: 12, showSizeChanger: true }}
          onRow={(record) => ({
            onDoubleClick: () => navigate(`/stock/${record.ts_code}`)
          })}
        />
      </Space>
    </PageContainer>
  );
};

export default PatternRadar;
