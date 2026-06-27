import { ClearOutlined, DatabaseOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons';
import { Alert, Button, Progress, Space, Tag, Typography } from 'antd';
import { PageContainer, ProCard, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/modules';
import type { DataHealthResponse, DataTableStatus, SyncJobOut } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

const statusColor: Record<string, string> = {
  queued: 'blue',
  running: 'gold',
  success: 'green',
  failed: 'red'
};

function pct(numerator?: number | null, denominator?: number | null): number {
  if (!numerator || !denominator) return 0;
  return Math.min(100, Math.round((numerator / denominator) * 100));
}

const DataCenter = () => {
  const [health, setHealth] = useState<DataHealthResponse | null>(null);
  const [jobs, setJobs] = useState<SyncJobOut[]>([]);
  const stockCount = useMemo(() => health?.tables.find((item) => item.key === 'stocks')?.row_count ?? 0, [health?.tables]);

  async function load(): Promise<void> {
    const [nextHealth, nextJobs] = await Promise.all([api.getDataHealth(), api.listSyncJobs()]);
    setHealth(nextHealth);
    setJobs(nextJobs);
  }

  async function sync(): Promise<void> {
    const job = await api.syncData(health?.provider);
    notifySuccess(job.message);
    await load();
  }

  async function recalc(): Promise<void> {
    const job = await api.calculateFactors();
    notifySuccess(job.message);
    await load();
  }

  useEffect(() => {
    runSafely(load());
  }, []);

  const tableColumns: ProColumns<DataTableStatus>[] = [
    { title: '数据集', dataIndex: 'name', width: 140, fixed: 'left' },
    { title: '行数', dataIndex: 'row_count', width: 110, sorter: (a, b) => a.row_count - b.row_count },
    { title: '最新日期', dataIndex: 'latest_date', width: 150, render: (_, record) => record.latest_date ?? '-' },
    {
      title: '覆盖',
      dataIndex: 'coverage_count',
      width: 180,
      render: (_, record) =>
        typeof record.coverage_count === 'number' ? (
          <Space direction="vertical" size={2} style={{ width: '100%' }}>
            <Progress percent={pct(record.coverage_count, stockCount)} size="small" />
            <Typography.Text type="secondary">{record.coverage_count}/{stockCount}</Typography.Text>
          </Space>
        ) : (
          '-'
        )
    },
    { title: '用途', dataIndex: 'note', ellipsis: true }
  ];

  const jobColumns: ProColumns<SyncJobOut>[] = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '任务', dataIndex: 'job_type', width: 150 },
    { title: '状态', dataIndex: 'status', width: 92, render: (_, record) => <Tag color={statusColor[record.status] ?? 'default'}>{record.status}</Tag> },
    { title: '消息', dataIndex: 'message', ellipsis: true },
    { title: '开始', dataIndex: 'started_at', width: 170 },
    { title: '结束', dataIndex: 'finished_at', width: 170, render: (_, record) => record.finished_at ?? '-' }
  ];

  return (
    <PageContainer
      title="数据中心"
      extra={[
        <Button key="sync" type="primary" icon={<SyncOutlined />} onClick={() => runSafely(sync())}>
          后台同步
        </Button>,
        <Button key="factor" icon={<ClearOutlined />} onClick={() => runSafely(recalc())}>
          重算因子
        </Button>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(load())}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {health?.warnings.length ? (
          <Alert showIcon type="warning" message="数据健康提醒" description={health.warnings.join('；')} />
        ) : (
          <Alert showIcon type="success" message="数据缓存状态正常，页面会优先读取本地缓存。" />
        )}
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '数据源', value: health?.provider ?? '-' }} />
          <StatisticCard statistic={{ title: '最新交易日', value: health?.latest_trade_date ?? '-' }} />
          <StatisticCard statistic={{ title: 'SQLite大小', value: `${health?.db_size_mb ?? 0} MB` }} />
          <StatisticCard statistic={{ title: '后台调度', value: health?.scheduler_enabled ? '已启用' : '未启用' }} />
          <StatisticCard statistic={{ title: '因子预热', value: `${health?.factor_cache_refresh_minutes ?? 0} 分钟` }} />
        </StatisticCard.Group>
        <ProCard bordered>
          <div className="data-health-strip">
            <Space wrap>
              <Tag icon={<DatabaseOutlined />} color={health?.fallback_to_demo ? 'gold' : 'green'}>
                {health?.fallback_to_demo ? '允许DEMO兜底' : '真实数据优先'}
              </Tag>
              <Tag color="blue">每日同步 {health?.daily_sync_cron ?? '-'}</Tag>
              <Typography.Text type="secondary">{health?.db_path}</Typography.Text>
            </Space>
          </div>
        </ProCard>
        <ProTable<DataTableStatus>
          rowKey="key"
          cardBordered
          search={false}
          options={false}
          columns={tableColumns}
          dataSource={health?.tables ?? []}
          pagination={false}
          scroll={{ x: 860 }}
          headerTitle="本地缓存覆盖"
        />
        <ProTable<SyncJobOut>
          rowKey="id"
          cardBordered
          search={false}
          options={false}
          columns={jobColumns}
          dataSource={jobs}
          pagination={{ pageSize: 8 }}
          scroll={{ x: 900 }}
          headerTitle="后台任务记录"
        />
      </Space>
    </PageContainer>
  );
};

export default DataCenter;
