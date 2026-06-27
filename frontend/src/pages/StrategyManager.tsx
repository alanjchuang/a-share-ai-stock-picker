import { DeleteOutlined, EditOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Modal, Popconfirm, Space, Switch, Typography } from 'antd';
import { PageContainer, ProCard, ProForm, ProFormTextArea, ProTable } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, defaultScreeningRequest } from '../api/modules';
import { useAppStore } from '../store/useAppStore';
import type { ScreeningRequest, StrategyOut } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

interface StrategyFormValue {
  name: string;
  remark: string;
  schedule_enabled: boolean;
  schedule_cron: string;
}

const StrategyManager = () => {
  const [strategies, setStrategies] = useState<StrategyOut[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<StrategyOut | null>(null);
  const [form] = Form.useForm<StrategyFormValue>();
  const navigate = useNavigate();
  const setCurrentRequest = useAppStore((state) => state.setCurrentRequest);
  const setLatestResult = useAppStore((state) => state.setLatestResult);

  const load = () => runSafely(api.listStrategies().then(setStrategies));

  useEffect(load, []);

  const chartOption = useMemo<EChartsOption>(
    () => ({
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 48, right: 24, top: 42, bottom: 32 },
      xAxis: { type: 'category', data: strategies.map((item) => item.name) },
      yAxis: [{ type: 'value' }, { type: 'value' }],
      series: [
        { name: '选股数量', type: 'bar', data: strategies.map((item) => item.result_count), itemStyle: { color: '#1f7a8c' } },
        { name: '平均综合得分', type: 'line', yAxisIndex: 1, data: strategies.map((item) => item.avg_score), itemStyle: { color: '#c2410c' } },
        { name: '平均涨幅', type: 'line', yAxisIndex: 1, data: strategies.map((item) => item.avg_pct_chg), itemStyle: { color: '#4f46e5' } }
      ]
    }),
    [strategies]
  );

  const columns: ProColumns<StrategyOut>[] = [
    { title: '名称', dataIndex: 'name', width: 160 },
    { title: '备注', dataIndex: 'remark', ellipsis: true },
    { title: '选股数量', dataIndex: 'result_count', width: 96, sorter: (a, b) => a.result_count - b.result_count },
    { title: '平均得分', dataIndex: 'avg_score', width: 96, sorter: (a, b) => a.avg_score - b.avg_score },
    { title: '平均涨幅', dataIndex: 'avg_pct_chg', width: 96 },
    {
      title: '定时',
      dataIndex: 'schedule_enabled',
      width: 96,
      render: (_, record) => (record.schedule_enabled ? <Typography.Text type="success">已启用</Typography.Text> : <Typography.Text type="secondary">未启用</Typography.Text>)
    },
    { title: '更新时间', dataIndex: 'updated_at', width: 170 },
    {
      title: '操作',
      valueType: 'option',
      width: 220,
      render: (_, record) => [
        <Button key="run" type="link" icon={<PlayCircleOutlined />} onClick={() => runSafely(runStrategy(record))}>
          执行
        </Button>,
        <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>
          编辑
        </Button>,
        <Popconfirm key="delete" title="删除策略？" onConfirm={() => runSafely(api.deleteStrategy(record.id).then(load))}>
          <Button type="link" danger icon={<DeleteOutlined />}>
            删除
          </Button>
        </Popconfirm>
      ]
    }
  ];

  async function runStrategy(strategy: StrategyOut): Promise<void> {
    const result = await api.runScreener(strategy.conditions);
    setCurrentRequest(strategy.conditions);
    setLatestResult(result);
    notifySuccess(`策略执行完成，命中 ${result.total} 只`);
    navigate('/');
  }

  function openEdit(strategy: StrategyOut | null): void {
    setEditing(strategy);
    form.setFieldsValue(
      strategy
        ? {
            name: strategy.name,
            remark: strategy.remark,
            schedule_enabled: strategy.schedule_enabled,
            schedule_cron: strategy.schedule_cron
          }
        : { name: '', remark: '', schedule_enabled: false, schedule_cron: '30 18 * * 1-5' }
    );
    setModalOpen(true);
  }

  async function submit(): Promise<void> {
    const values = await form.validateFields();
    const conditions: ScreeningRequest = editing?.conditions ?? defaultScreeningRequest;
    if (editing) {
      await api.updateStrategy(editing.id, { ...values, conditions });
    } else {
      await api.createStrategy({ ...values, conditions });
    }
    setModalOpen(false);
    load();
  }

  return (
    <PageContainer
      title="策略管理"
      extra={[
        <Button key="new" type="primary" icon={<PlusOutlined />} onClick={() => openEdit(null)}>
          新建策略
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <ProCard title="多策略对比" bordered>
          <ReactECharts option={chartOption} style={{ height: 320 }} notMerge />
        </ProCard>
        <ProTable<StrategyOut> rowKey="id" search={false} options={false} columns={columns} dataSource={strategies} pagination={{ pageSize: 10 }} cardBordered />
      </Space>
      <Modal title={editing ? '编辑策略' : '新建策略'} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => runSafely(submit())} destroyOnHidden>
        <ProForm form={form} submitter={false} layout="vertical">
          <ProFormTextArea name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]} fieldProps={{ autoSize: { minRows: 1, maxRows: 1 } }} />
          <ProFormTextArea name="remark" label="备注" fieldProps={{ autoSize: { minRows: 2, maxRows: 4 } }} />
          <Form.Item name="schedule_enabled" label="本地定时自动选股" valuePropName="checked">
            <Switch />
          </Form.Item>
          <ProFormTextArea name="schedule_cron" label="Cron表达式" fieldProps={{ autoSize: { minRows: 1, maxRows: 1 } }} />
        </ProForm>
      </Modal>
    </PageContainer>
  );
};

export default StrategyManager;
