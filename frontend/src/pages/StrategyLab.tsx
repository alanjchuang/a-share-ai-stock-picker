import { ExperimentOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Select, Space, Tag, Typography } from 'antd';
import { PageContainer, ProCard, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import StockLlmAnalysisButton from '../components/StockLlmAnalysisButton';
import type { Rating, StrategyDefinition, StrategyHit } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

const ratingColor: Record<Rating, string> = {
  A: 'green',
  B: 'blue',
  C: 'gold',
  D: 'red'
};

const riskColor: Record<string, string> = {
  low: 'green',
  medium: 'gold',
  high: 'red'
};

function pct(value?: number | null): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(2)}%` : '-';
}

const StrategyLab = () => {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>('volume_surge_up');
  const [holdingDays, setHoldingDays] = useState(10);
  const [scan, setScan] = useState<Awaited<ReturnType<typeof api.scanBuiltInStrategy>> | null>(null);

  const selectedStrategy = useMemo(() => strategies.find((item) => item.key === selectedKey), [selectedKey, strategies]);

  async function loadStrategies(forceRefresh = false): Promise<void> {
    const data = await api.listBuiltInStrategies({ forceRefresh });
    setStrategies(data);
    if (!data.some((item) => item.key === selectedKey) && data[0]) {
      setSelectedKey(data[0].key);
    }
  }

  async function runScan(key = selectedKey, forceRefresh = false): Promise<void> {
    setScan(await api.scanBuiltInStrategy(key, { limit: 80, holding_days: holdingDays }, { forceRefresh }));
  }

  useEffect(() => {
    runSafely(loadStrategies());
  }, []);

  useEffect(() => {
    if (selectedKey) runSafely(runScan(selectedKey));
  }, [selectedKey, holdingDays]);

  async function addToWatchlist(record: StrategyHit): Promise<void> {
    await api.addWatchlistItem({
      ts_code: record.ts_code,
      group_name: '策略池',
      reason: `${record.strategy_name}：${record.reason}`,
      tags: [record.strategy_name, record.industry ?? '未分类'],
      priority: record.stock.rating === 'A' ? 5 : record.stock.rating === 'B' ? 4 : 3,
      risk_level: selectedStrategy?.risk_level === 'high' ? 'high' : 'medium'
    });
    notifySuccess(`${record.name} 已加入策略池`);
  }

  const columns: ProColumns<StrategyHit>[] = [
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
    { title: '信号分', dataIndex: 'signal_score', width: 92, sorter: (a, b) => a.signal_score - b.signal_score, render: (_, record) => record.signal_score.toFixed(1) },
    { title: '涨跌幅', dataIndex: ['stock', 'pct_chg'], width: 92, render: (_, record) => <Typography.Text type={Number(record.stock.pct_chg ?? 0) >= 0 ? 'danger' : 'success'}>{pct(record.stock.pct_chg)}</Typography.Text> },
    { title: 'PE', dataIndex: ['stock', 'pe_ttm'], width: 78, render: (_, record) => record.stock.pe_ttm?.toFixed(2) ?? '-' },
    { title: 'ROE', dataIndex: ['stock', 'roe'], width: 82, render: (_, record) => pct(record.stock.roe) },
    {
      title: 'AI评分',
      dataIndex: ['stock', 'ai_score'],
      width: 96,
      render: (_, record) => <Tag color={ratingColor[record.stock.rating]} className="score-badge">{record.stock.rating} {record.stock.ai_score.toFixed(1)}</Tag>
    },
    { title: '命中理由', dataIndex: 'reason', ellipsis: true },
    {
      title: '操作',
      valueType: 'option',
      width: 190,
      fixed: 'right',
      render: (_, record) => [
        <Button key="detail" type="link" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          详情
        </Button>,
        <StockLlmAnalysisButton key="analysis" tsCode={record.ts_code} name={record.name} />,
        <Button key="add" type="link" icon={<PlusOutlined />} onClick={() => runSafely(addToWatchlist(record))}>
          自选
        </Button>
      ]
    }
  ];

  return (
    <PageContainer
      title="策略实验室"
      extra={[
        <Button key="run" type="primary" icon={<ExperimentOutlined />} onClick={() => runSafely(runScan())}>
          扫描
        </Button>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(loadStrategies(true).then(() => runScan(selectedKey, true)))}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <ProCard bordered>
          <div className="market-toolbar">
            <Select
              value={selectedKey}
              onChange={setSelectedKey}
              options={strategies.map((item) => ({ label: `${item.name} · ${item.category}`, value: item.key }))}
              style={{ width: 260 }}
            />
            <Select
              value={holdingDays}
              onChange={setHoldingDays}
              options={[
                { label: '持有5日回测', value: 5 },
                { label: '持有10日回测', value: 10 },
                { label: '持有20日回测', value: 20 }
              ]}
              style={{ width: 150 }}
            />
            {selectedStrategy ? <Tag color={riskColor[selectedStrategy.risk_level]}>{selectedStrategy.risk_level}</Tag> : null}
            <Typography.Text type="secondary">{selectedStrategy?.description}</Typography.Text>
          </div>
        </ProCard>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '命中数量', value: scan?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '回测样本', value: scan?.backtest.sample_count ?? 0 }} />
          <StatisticCard statistic={{ title: '胜率', value: pct(scan?.backtest.win_rate) }} />
          <StatisticCard statistic={{ title: '平均收益', value: pct(scan?.backtest.avg_return) }} />
          <StatisticCard statistic={{ title: '最大/最小', value: `${pct(scan?.backtest.max_return)} / ${pct(scan?.backtest.min_return)}` }} />
        </StatisticCard.Group>
        <ProTable<StrategyHit>
          rowKey="ts_code"
          cardBordered
          search={false}
          options={false}
          columns={columns}
          dataSource={scan?.rows ?? []}
          scroll={{ x: 1340 }}
          pagination={{ pageSize: 12, showSizeChanger: true }}
          onRow={(record) => ({
            onDoubleClick: () => navigate(`/stock/${record.ts_code}`)
          })}
        />
      </Space>
    </PageContainer>
  );
};

export default StrategyLab;
