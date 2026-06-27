import { DeleteOutlined, EditOutlined, MessageOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Modal, Popconfirm, Segmented, Space, Switch, Tag, Typography, message } from 'antd';
import { PageContainer, ProCard, ProForm, ProFormDigit, ProFormSelect, ProFormText, ProFormTextArea, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import type { WatchlistAskResponse, WatchlistGroup, WatchlistItem } from '../types';
import { runSafely } from '../utils/async';

interface WatchlistFormValue {
  ts_code: string;
  group_id: number;
  reason: string;
  tags: string[];
  priority: number;
  risk_level: 'low' | 'medium' | 'high';
  status: 'active' | 'paused' | 'closed';
  cost_price?: number | null;
  target_price?: number | null;
  stop_loss_price?: number | null;
  review_interval_days: number;
  next_review_date?: string | null;
}

const riskColor: Record<string, string> = {
  low: 'green',
  medium: 'gold',
  high: 'red'
};

const WatchlistCenter = () => {
  const [groups, setGroups] = useState<WatchlistGroup[]>([]);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | undefined>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<WatchlistItem | null>(null);
  const [question, setQuestion] = useState('帮我检查自选股里哪些需要降级观察，哪些可以继续重点跟踪');
  const [includeSearch, setIncludeSearch] = useState(true);
  const [answer, setAnswer] = useState<WatchlistAskResponse | null>(null);
  const [form] = Form.useForm<WatchlistFormValue>();
  const navigate = useNavigate();

  const groupOptions = useMemo(() => groups.map((item) => ({ label: item.name, value: item.id })), [groups]);
  const selectedGroup = groups.find((item) => item.id === selectedGroupId);

  const loadGroups = async (): Promise<WatchlistGroup[]> => {
    const data = await api.listWatchlistGroups();
    setGroups(data);
    if (!selectedGroupId && data[0]) setSelectedGroupId(data[0].id);
    return data;
  };

  const loadItems = async (groupId = selectedGroupId): Promise<void> => {
    const data = await api.listWatchlistItems({ group_id: groupId, status: 'active' });
    setItems(data);
  };

  useEffect(() => {
    runSafely(loadGroups().then((data) => loadItems(data[0]?.id)));
  }, []);

  useEffect(() => {
    if (selectedGroupId) runSafely(loadItems(selectedGroupId));
  }, [selectedGroupId]);

  const columns: ProColumns<WatchlistItem>[] = [
    {
      title: '股票',
      dataIndex: 'ts_code',
      width: 160,
      fixed: 'left',
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          {record.stock?.name ?? record.ts_code} · {record.ts_code}
        </Button>
      )
    },
    { title: '行业', dataIndex: ['stock', 'industry'], width: 100 },
    {
      title: '评分',
      dataIndex: ['stock', 'ai_score'],
      width: 92,
      sorter: (a, b) => Number(a.stock?.ai_score ?? 0) - Number(b.stock?.ai_score ?? 0),
      render: (_, record) => <Tag color={record.stock?.rating === 'A' ? 'green' : record.stock?.rating === 'B' ? 'blue' : 'gold'}>{record.stock?.rating ?? '-'} {record.stock?.ai_score?.toFixed(1) ?? '-'}</Tag>
    },
    {
      title: '舆情',
      dataIndex: ['stock', 'sentiment_score'],
      width: 108,
      render: (_, record) => <Tag color={Number(record.stock?.sentiment_score ?? 50) >= 60 ? 'green' : Number(record.stock?.sentiment_score ?? 50) >= 40 ? 'gold' : 'red'}>{record.stock?.sentiment_label ?? '中性'} {record.stock?.sentiment_score?.toFixed(0) ?? '-'}</Tag>
    },
    { title: '涨跌幅', dataIndex: ['stock', 'pct_chg'], width: 92, render: (_, record) => `${record.stock?.pct_chg?.toFixed(2) ?? '-'}%` },
    { title: 'PE', dataIndex: ['stock', 'pe_ttm'], width: 76, render: (_, record) => record.stock?.pe_ttm?.toFixed(2) ?? '-' },
    {
      title: '风险',
      dataIndex: 'risk_level',
      width: 92,
      render: (_, record) => <Tag color={riskColor[record.risk_level] ?? 'default'}>{record.risk_level}</Tag>
    },
    { title: '优先级', dataIndex: 'priority', width: 82, sorter: (a, b) => a.priority - b.priority },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 180,
      render: (_, record) => record.tags.map((tag) => <Tag key={tag}>{tag}</Tag>)
    },
    { title: '关注理由', dataIndex: 'reason', ellipsis: true },
    { title: '下次复盘', dataIndex: 'next_review_date', width: 110 },
    {
      title: '操作',
      valueType: 'option',
      width: 156,
      render: (_, record) => [
        <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => openEdit(record)}>
          编辑
        </Button>,
        <Popconfirm key="delete" title="移除自选股？" onConfirm={() => runSafely(remove(record.id))}>
          <Button type="link" danger icon={<DeleteOutlined />}>
            移除
          </Button>
        </Popconfirm>
      ]
    }
  ];

  function openCreate(): void {
    setEditing(null);
    form.setFieldsValue({
      ts_code: '',
      group_id: selectedGroupId,
      reason: '',
      tags: [],
      priority: 3,
      risk_level: 'medium',
      status: 'active',
      review_interval_days: 7
    });
    setModalOpen(true);
  }

  function openEdit(item: WatchlistItem): void {
    setEditing(item);
    form.setFieldsValue({
      ts_code: item.ts_code,
      group_id: item.group_id,
      reason: item.reason,
      tags: item.tags,
      priority: item.priority,
      risk_level: item.risk_level as WatchlistFormValue['risk_level'],
      status: item.status as WatchlistFormValue['status'],
      cost_price: item.cost_price,
      target_price: item.target_price,
      stop_loss_price: item.stop_loss_price,
      review_interval_days: item.review_interval_days,
      next_review_date: item.next_review_date
    });
    setModalOpen(true);
  }

  async function submit(): Promise<void> {
    const values = await form.validateFields();
    if (editing) {
      await api.updateWatchlistItem(editing.id, values);
      message.success('自选股已更新');
    } else {
      await api.addWatchlistItem(values);
      message.success('已加入自选股');
    }
    setModalOpen(false);
    await loadGroups();
    await loadItems(values.group_id);
    setSelectedGroupId(values.group_id);
  }

  async function remove(id: number): Promise<void> {
    await api.deleteWatchlistItem(id);
    message.success('已移除自选股');
    await loadGroups();
    await loadItems();
  }

  async function ask(): Promise<void> {
    const result = await api.askWatchlist({ question, group_id: selectedGroupId, include_search: includeSearch });
    setAnswer(result);
    message.success(result.source === 'llm' ? 'AI复盘完成' : '规则复盘完成');
  }

  const avgScore = items.reduce((sum, item) => sum + Number(item.stock?.ai_score ?? 0), 0) / Math.max(1, items.length);
  const highRiskCount = items.filter((item) => item.risk_level === 'high' || Number(item.stock?.sentiment_score ?? 50) < 45).length;

  return (
    <PageContainer
      title="自选股研究与复盘"
      extra={[
        <Button key="new" type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          加入自选
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Segmented
          value={selectedGroupId}
          onChange={(value) => setSelectedGroupId(Number(value))}
          options={groups.map((item) => ({ label: `${item.name} ${item.item_count}`, value: item.id }))}
        />
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '当前分组', value: selectedGroup?.name ?? '-' }} />
          <StatisticCard statistic={{ title: '自选数量', value: items.length }} />
          <StatisticCard statistic={{ title: '平均AI评分', value: avgScore.toFixed(1) }} />
          <StatisticCard statistic={{ title: '风险复核', value: highRiskCount }} />
        </StatisticCard.Group>
        <ProCard bordered title="快速询问自选股">
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Input.TextArea value={question} onChange={(event) => setQuestion(event.target.value)} autoSize={{ minRows: 2, maxRows: 4 }} />
            <div className="toolbar-row">
              <Space wrap>
                {['哪些需要风险复核？', '哪些还符合加入自选的理由？', '帮我生成本周复盘问题'].map((text) => (
                  <Button key={text} onClick={() => setQuestion(text)}>
                    {text}
                  </Button>
                ))}
              </Space>
              <Space>
                <Typography.Text type="secondary">联网资料</Typography.Text>
                <Switch checked={includeSearch} onChange={setIncludeSearch} />
                <Button type="primary" icon={<MessageOutlined />} onClick={() => runSafely(ask())}>
                  询问
                </Button>
              </Space>
            </div>
          </Space>
        </ProCard>
        {answer ? (
          <ProCard bordered title={`复盘结果 · ${answer.source === 'llm' ? 'LLM' : '规则兜底'}`}>
            <Space direction="vertical" size={10} style={{ width: '100%' }}>
              <Typography.Paragraph>{answer.answer}</Typography.Paragraph>
              <Typography.Text strong>动作建议</Typography.Text>
              {answer.action_items.map((item) => <Typography.Text key={item}>· {item}</Typography.Text>)}
              <Typography.Text strong>风险提醒</Typography.Text>
              {answer.risk_notes.map((item) => <Typography.Text key={item} type="warning">· {item}</Typography.Text>)}
              <Typography.Text strong>复盘问题</Typography.Text>
              {answer.review_questions.map((item) => <Typography.Text key={item}>· {item}</Typography.Text>)}
            </Space>
          </ProCard>
        ) : null}
        <ProTable<WatchlistItem>
          rowKey="id"
          cardBordered
          search={false}
          options={false}
          columns={columns}
          dataSource={items}
          scroll={{ x: 1320 }}
          pagination={{ pageSize: 10, showSizeChanger: true }}
        />
      </Space>
      <Modal title={editing ? '编辑自选股' : '加入自选股'} open={modalOpen} onCancel={() => setModalOpen(false)} onOk={() => runSafely(submit())} destroyOnClose>
        <ProForm<WatchlistFormValue> form={form} submitter={false} layout="vertical">
          <ProFormText name="ts_code" label="股票代码" disabled={Boolean(editing)} rules={[{ required: true, message: '请输入股票代码，如 600519.SH' }]} />
          <ProFormSelect name="group_id" label="分组" options={groupOptions} rules={[{ required: true, message: '请选择分组' }]} />
          <ProFormTextArea name="reason" label="关注理由" fieldProps={{ autoSize: { minRows: 2, maxRows: 4 } }} />
          <ProFormSelect name="tags" label="标签" mode="tags" />
          <Space.Compact block>
            <ProFormDigit name="priority" label="优先级" min={1} max={5} />
            <ProFormSelect
              name="risk_level"
              label="风险级别"
              options={[
                { label: '低', value: 'low' },
                { label: '中', value: 'medium' },
                { label: '高', value: 'high' }
              ]}
            />
          </Space.Compact>
          <Space.Compact block>
            <ProFormDigit name="cost_price" label="观察/成本价" min={0} />
            <ProFormDigit name="target_price" label="目标观察价" min={0} />
            <ProFormDigit name="stop_loss_price" label="风险观察价" min={0} />
          </Space.Compact>
          <Space.Compact block>
            <ProFormDigit name="review_interval_days" label="复盘间隔天数" min={1} max={365} />
            <ProFormText name="next_review_date" label="下次复盘日期" />
          </Space.Compact>
          <ProFormSelect
            name="status"
            label="状态"
            options={[
              { label: '跟踪中', value: 'active' },
              { label: '暂停', value: 'paused' },
              { label: '已关闭', value: 'closed' }
            ]}
          />
        </ProForm>
      </Modal>
    </PageContainer>
  );
};

export default WatchlistCenter;
