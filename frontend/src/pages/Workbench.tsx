import {
  DownloadOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SaveOutlined,
  StarOutlined,
  SyncOutlined,
  ThunderboltOutlined
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Divider,
  Form,
  Input,
  Modal,
  Select,
  Segmented,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography
} from 'antd';
import { ProCard, ProForm, ProFormDigit, ProFormSelect, ProFormTextArea, ProTable, StatisticCard } from '@ant-design/pro-components';
import type { ProColumns } from '@ant-design/pro-components';
import { useEffect, useMemo, useState, type MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import * as XLSX from '@e965/xlsx';
import FactorCharts from '../components/FactorCharts';
import { api, defaultScreeningRequest } from '../api/modules';
import { useAppStore } from '../store/useAppStore';
import type { IndexMeta, OneClickRecommendResponse, ScreeningRequest, ScreeningResult, StockDetail, StockScore, WorkflowInfo, WorkbenchMode } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

const ratingColor: Record<string, string> = {
  A: 'green',
  B: 'blue',
  C: 'gold',
  D: 'red'
};

type BeginnerPreset = 'balanced' | 'value' | 'growth' | 'sentiment';
type RecommendRisk = 'conservative' | 'balanced' | 'aggressive';

function diagnosticsDescription(result: ScreeningResult): string {
  const diagnostics = result.diagnostics;
  if (!diagnostics) return '后端未返回筛选诊断信息。';
  const excluded = Object.entries(diagnostics.excluded_counts)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => `${name}${count}只`)
    .join('，');
  const warnings = diagnostics.warnings.join(' ');
  return [
    `股票池${diagnostics.stock_universe_count}只，因子池${diagnostics.factor_universe_count}只，基础过滤后${diagnostics.base_universe_count}只。`,
    diagnostics.condition_count > 0 ? `本次应用${diagnostics.condition_count}个筛选条件，命中${diagnostics.matched_count}只。` : `本次没有启用具体因子条件，命中${diagnostics.matched_count}只。`,
    excluded ? `基础过滤剔除：${excluded}。` : '',
    warnings
  ]
    .filter(Boolean)
    .join(' ');
}

function normalizeRequest(values: Partial<ScreeningRequest>): ScreeningRequest {
  return {
    ...defaultScreeningRequest,
    ...values,
    index: { ...defaultScreeningRequest.index, ...values.index, index_codes: values.index?.index_codes ?? [] },
    fundamental: { ...defaultScreeningRequest.fundamental, ...values.fundamental },
    technical: {
      ...defaultScreeningRequest.technical,
      ...values.technical,
      above_ma: values.technical?.above_ma ?? []
    },
    capital: { ...defaultScreeningRequest.capital, ...values.capital },
    sentiment: {
      ...defaultScreeningRequest.sentiment,
      ...values.sentiment,
      include_labels: values.sentiment?.include_labels ?? [],
      whitelist_keywords: values.sentiment?.whitelist_keywords ?? [],
      blacklist_keywords: values.sentiment?.blacklist_keywords ?? []
    },
    filters: { ...defaultScreeningRequest.filters, ...values.filters },
    weights: { ...defaultScreeningRequest.weights, ...values.weights },
    limit: values.limit ?? defaultScreeningRequest.limit
  };
}

const Workbench = () => {
  const [form] = Form.useForm<ScreeningRequest>();
  const [saveForm] = Form.useForm<{ name: string; remark: string; schedule_enabled: boolean; schedule_cron: string }>();
  const navigate = useNavigate();
  const setCurrentRequest = useAppStore((state) => state.setCurrentRequest);
  const setLatestResult = useAppStore((state) => state.setLatestResult);
  const workbenchMode = useAppStore((state) => state.workbenchMode);
  const setWorkbenchMode = useAppStore((state) => state.setWorkbenchMode);
  const latestResult = useAppStore((state) => state.latestResult);
  const [indices, setIndices] = useState<IndexMeta[]>([]);
  const [result, setResult] = useState<ScreeningResult | null>(latestResult);
  const [selected, setSelected] = useState<StockScore | null>(null);
  const [stockDetail, setStockDetail] = useState<StockDetail | null>(null);
  const [aiText, setAiText] = useState('');
  const [beginnerPreset, setBeginnerPreset] = useState<BeginnerPreset>('balanced');
  const [recommendRisk, setRecommendRisk] = useState<RecommendRisk>('balanced');
  const [recommendation, setRecommendation] = useState<OneClickRecommendResponse | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  const [selectedWorkflowPath, setSelectedWorkflowPath] = useState<string | undefined>();
  const [saveOpen, setSaveOpen] = useState(false);

  useEffect(() => {
    form.setFieldsValue(defaultScreeningRequest);
    runSafely(api.listIndices().then(setIndices));
    runSafely(api.listWorkflows().then((items) => {
      setWorkflows(items);
      const defaultWorkflow = items.find((item) => item.is_default) ?? items[0];
      setSelectedWorkflowPath(defaultWorkflow?.path);
    }));
  }, []);

  useEffect(() => {
    if (!selected) return;
    runSafely(api.getStockDetail(selected.ts_code).then(setStockDetail));
  }, [selected]);

  const indexOptions = useMemo(
    () =>
      indices.map((item) => ({
        label: `${item.name} · ${item.category}`,
        value: item.index_code
      })),
    [indices]
  );

  function beginnerRequest(preset: BeginnerPreset): ScreeningRequest {
    const base = normalizeRequest(defaultScreeningRequest);
    const presets: Record<BeginnerPreset, Partial<ScreeningRequest>> = {
      balanced: {
        fundamental: { roe: { min: 8, max: null }, pe_ttm: { min: null, max: 45 } },
        sentiment: { ...base.sentiment, days: 7, min_avg_score: 50 },
        weights: { fundamental: 35, technical: 25, capital: 20, sentiment: 20 },
        limit: 80
      },
      value: {
        fundamental: { pe_ttm: { min: null, max: 25 }, pb: { min: null, max: 3 }, roe: { min: 10, max: null } },
        weights: { fundamental: 50, technical: 15, capital: 20, sentiment: 15 },
        limit: 80
      },
      growth: {
        fundamental: { revenue_yoy: { min: 12, max: null }, roe: { min: 8, max: null } },
        technical: { ...base.technical, above_ma: [20], pct_chg_n: { min: 0, max: null }, pct_chg_days: 20 },
        weights: { fundamental: 30, technical: 35, capital: 20, sentiment: 15 },
        limit: 80
      },
      sentiment: {
        sentiment: { ...base.sentiment, days: 7, min_avg_score: 65, blacklist_keywords: ['退市', '立案', '减持', '问询函'] },
        capital: { main_net_inflow_min: 0 },
        weights: { fundamental: 20, technical: 20, capital: 20, sentiment: 40 },
        limit: 80
      }
    };
    return normalizeRequest({
      ...base,
      ...presets[preset],
      filters: { ...base.filters, exclude_st: true, exclude_paused: true, new_stock_days: 180 },
      logic: 'and'
    });
  }

  const columns: ProColumns<StockScore>[] = [
    {
      title: '代码',
      dataIndex: 'ts_code',
      width: 110,
      fixed: 'left',
      render: (_, record) => (
        <Button type="link" size="small" onClick={() => navigate(`/stock/${record.ts_code}`)}>
          {record.ts_code}
        </Button>
      )
    },
    { title: '名称', dataIndex: 'name', width: 96, fixed: 'left' },
    { title: '行业', dataIndex: 'industry', width: 96 },
    {
      title: '指数',
      dataIndex: 'index_names',
      width: 180,
      render: (_, record) => record.index_names.slice(0, 2).map((name) => <Tag key={name}>{name}</Tag>)
    },
    { title: '收盘', dataIndex: 'close', valueType: 'digit', sorter: (a, b) => Number(a.close ?? 0) - Number(b.close ?? 0), width: 82 },
    {
      title: '涨跌幅',
      dataIndex: 'pct_chg',
      valueType: 'digit',
      sorter: (a, b) => Number(a.pct_chg ?? 0) - Number(b.pct_chg ?? 0),
      width: 92,
      render: (_, record) => <Typography.Text type={Number(record.pct_chg ?? 0) >= 0 ? 'danger' : 'success'}>{record.pct_chg?.toFixed(2)}%</Typography.Text>
    },
    { title: 'PE', dataIndex: 'pe_ttm', valueType: 'digit', sorter: (a, b) => Number(a.pe_ttm ?? 0) - Number(b.pe_ttm ?? 0), width: 78 },
    { title: 'PB', dataIndex: 'pb', valueType: 'digit', sorter: (a, b) => Number(a.pb ?? 0) - Number(b.pb ?? 0), width: 78 },
    { title: 'ROE', dataIndex: 'roe', valueType: 'digit', sorter: (a, b) => Number(a.roe ?? 0) - Number(b.roe ?? 0), width: 82 },
    {
      title: '舆情',
      dataIndex: 'sentiment_score',
      width: 110,
      sorter: (a, b) => a.sentiment_score - b.sentiment_score,
      render: (_, record) => <Tag color={record.sentiment_score >= 60 ? 'green' : record.sentiment_score >= 40 ? 'gold' : 'red'}>{record.sentiment_label} {record.sentiment_score.toFixed(0)}</Tag>
    },
    {
      title: 'AI评分',
      dataIndex: 'ai_score',
      width: 96,
      sorter: (a, b) => a.ai_score - b.ai_score,
      defaultSortOrder: 'descend',
      render: (_, record) => <Tag className="score-badge" color={ratingColor[record.rating]}>{record.rating} {record.ai_score.toFixed(1)}</Tag>
    },
    {
      title: '操作',
      valueType: 'option',
      width: 96,
      fixed: 'right',
      render: (_, record) => (
        <Button type="link" size="small" icon={<StarOutlined />} onClick={(event) => runSafely(addToWatchlist(record, event))}>
          自选
        </Button>
      )
    }
  ];

  async function run(values?: Partial<ScreeningRequest>): Promise<void> {
    const request = normalizeRequest(values ?? form.getFieldsValue(true));
    form.setFieldsValue(request);
    setCurrentRequest(request);
    const data = await api.runScreener(request);
    setResult(data);
    setLatestResult(data);
    setSelected(data.rows[0] ?? null);
    notifySuccess(`选股完成：命中 ${data.total} 只`);
  }

  async function parseAiText(): Promise<void> {
    const workflow = await api.runSelectionWorkflow(aiText, selectedWorkflowPath);
    form.setFieldsValue(workflow.parsed_request);
    setCurrentRequest(workflow.parsed_request);
    if (workflow.screening_result) {
      setResult(workflow.screening_result);
      setLatestResult(workflow.screening_result);
      setSelected(workflow.screening_result.rows[0] ?? null);
    } else {
      await run(workflow.parsed_request);
    }
    const view = workflow.llm_analysis.market_view;
    notifySuccess(typeof view === 'string' ? view : `Workflow执行完成：${workflow.workflow_name}`);
  }

  function reset(): void {
    form.setFieldsValue(defaultScreeningRequest);
    runSafely(run(defaultScreeningRequest));
  }

  function exportExcel(): void {
    const rows = result?.rows ?? [];
    const sheet = XLSX.utils.json_to_sheet(
      rows.map((row) => ({
        股票代码: row.ts_code,
        名称: row.name,
        行业: row.industry,
        所属指数: row.index_names.join('/'),
        收盘价: row.close,
        涨跌幅: row.pct_chg,
        PE: row.pe_ttm,
        PB: row.pb,
        ROE: row.roe,
        舆情分: row.sentiment_score,
        综合AI评分: row.ai_score,
        评级: row.rating
      }))
    );
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, sheet, '选股结果');
    XLSX.writeFile(workbook, `A股智能选股_${Date.now()}.xlsx`);
  }

  async function saveStrategy(): Promise<void> {
    const values = await saveForm.validateFields();
    const request = normalizeRequest(form.getFieldsValue(true));
    await api.createStrategy({
      name: values.name,
      remark: values.remark,
      conditions: request,
      schedule_enabled: values.schedule_enabled,
      schedule_cron: values.schedule_cron
    });
    setSaveOpen(false);
    notifySuccess('策略已保存');
  }

  async function addToWatchlist(record: StockScore, event?: MouseEvent<HTMLElement>): Promise<void> {
    event?.stopPropagation();
    await api.addWatchlistItem({
      ts_code: record.ts_code,
      group_name: '观察池',
      reason: `来自选股工作台：AI评分${record.ai_score.toFixed(1)}，评级${record.rating}`,
      tags: [record.industry ?? '未分类'].filter(Boolean),
      priority: record.rating === 'A' ? 5 : record.rating === 'B' ? 4 : 3,
      risk_level: record.sentiment_score < 45 ? 'high' : 'medium'
    });
    notifySuccess(`${record.name} 已加入自选股`);
  }

  async function oneClickRecommend(): Promise<void> {
    const data = await api.oneClickRecommend({
      risk_preference: recommendRisk,
      limit: 8,
      include_search: true
    });
    setRecommendation(data);
    notifySuccess('一键研究推荐完成');
  }

  async function refreshDataInBackground(): Promise<void> {
    const job = await api.syncData();
    notifySuccess(job.message);
  }

  return (
    <div className={workbenchMode === 'professional' ? 'workbench-grid' : 'workbench-grid beginner'}>
      {workbenchMode === 'professional' ? (
      <ProCard className="filter-panel" title="筛选条件" bordered>
        <ProForm<ScreeningRequest> form={form} submitter={false} layout="vertical">
          <ProFormSelect name={['index', 'index_codes']} label="指数池" mode="multiple" options={indexOptions} fieldProps={{ showSearch: true }} />
          <Space.Compact block>
            <Form.Item name={['index', 'max_pe_percentile']} label="指数PE分位上限" className="compact-item">
              <Input type="number" placeholder="35" />
            </Form.Item>
            <Form.Item name={['index', 'min_excess_return']} label="超额收益下限" className="compact-item">
              <Input type="number" placeholder="2" />
            </Form.Item>
          </Space.Compact>
          <ProFormDigit name={['index', 'track_momentum_top_n']} label="赛道动量Top N" min={1} max={20} />
          <Divider orientation="left">基本面</Divider>
          <Space.Compact block>
            <ProFormDigit name={['fundamental', 'pe_ttm', 'max']} label="PE低于" min={0} />
            <ProFormDigit name={['fundamental', 'pb', 'max']} label="PB低于" min={0} />
          </Space.Compact>
          <Space.Compact block>
            <ProFormDigit name={['fundamental', 'roe', 'min']} label="ROE高于" />
            <ProFormDigit name={['fundamental', 'revenue_yoy', 'min']} label="营收同比高于" />
          </Space.Compact>
          <Space.Compact block>
            <ProFormDigit name={['fundamental', 'circ_mv', 'min']} label="流通市值下限" />
            <ProFormDigit name={['fundamental', 'circ_mv', 'max']} label="流通市值上限" />
          </Space.Compact>
          <Divider orientation="left">技术</Divider>
          <ProFormSelect
            name={['technical', 'above_ma']}
            label="站上均线"
            mode="multiple"
            options={[5, 10, 20, 60, 120].map((value) => ({ label: `MA${value}`, value }))}
          />
          <Space.Compact block>
            <ProFormSelect
              name={['technical', 'macd_cross']}
              label="MACD"
              options={[
                { label: '金叉', value: 'golden' },
                { label: '死叉', value: 'dead' }
              ]}
              allowClear
            />
            <ProFormDigit name={['technical', 'pct_chg_n', 'min']} label="N日涨幅下限" />
          </Space.Compact>
          <Divider orientation="left">资金</Divider>
          <Space.Compact block>
            <ProFormDigit name={['capital', 'main_net_inflow_min']} label="主力净流入下限" />
            <ProFormDigit name={['capital', 'north_inflow_min']} label="北向净流入下限" />
          </Space.Compact>
          <Divider orientation="left">舆情</Divider>
          <Space.Compact block>
            <ProFormDigit name={['sentiment', 'days']} label="近N日" min={3} max={30} />
            <ProFormDigit name={['sentiment', 'min_avg_score']} label="均分高于" min={0} max={100} />
          </Space.Compact>
          <ProFormSelect name={['sentiment', 'whitelist_keywords']} label="关键词白名单" mode="tags" />
          <ProFormSelect name={['sentiment', 'blacklist_keywords']} label="关键词黑名单" mode="tags" />
          <Divider orientation="left">过滤与权重</Divider>
          <Space wrap>
            <Form.Item name={['filters', 'exclude_st']} label="剔除ST" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name={['filters', 'exclude_paused']} label="剔除停牌" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
          <Space.Compact block>
            <ProFormDigit name={['weights', 'fundamental']} label="基本面权重" min={0} />
            <ProFormDigit name={['weights', 'technical']} label="技术权重" min={0} />
          </Space.Compact>
          <Space.Compact block>
            <ProFormDigit name={['weights', 'capital']} label="资金权重" min={0} />
            <ProFormDigit name={['weights', 'sentiment']} label="舆情权重" min={0} />
          </Space.Compact>
        </ProForm>
      </ProCard>
      ) : (
        <ProCard className="filter-panel" title="新手模式" bordered>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Segmented
              block
              value={beginnerPreset}
              onChange={(value) => setBeginnerPreset(value as BeginnerPreset)}
              options={[
                { label: '均衡', value: 'balanced' },
                { label: '价值', value: 'value' },
                { label: '成长', value: 'growth' },
                { label: '舆情', value: 'sentiment' }
              ]}
            />
            <Button type="primary" block icon={<PlayCircleOutlined />} onClick={() => runSafely(run(beginnerRequest(beginnerPreset)))}>
              执行新手筛选
            </Button>
            <Button block onClick={() => setWorkbenchMode('professional')}>
              切到专业模式
            </Button>
            <Typography.Text type="secondary">当前预设会自动剔除ST、停牌和次新股。</Typography.Text>
          </Space>
        </ProCard>
      )}
      <Space direction="vertical" size={16} style={{ width: '100%', minWidth: 0 }}>
        <ProCard bordered>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div className="toolbar-row">
              <Space wrap>
                <Segmented<WorkbenchMode>
                  value={workbenchMode}
                  onChange={setWorkbenchMode}
                  options={[
                    { label: '新手模式', value: 'beginner' },
                    { label: '专业模式', value: 'professional' }
                  ]}
                />
                <Segmented<RecommendRisk>
                  value={recommendRisk}
                  onChange={setRecommendRisk}
                  options={[
                    { label: '稳健', value: 'conservative' },
                    { label: '均衡', value: 'balanced' },
                    { label: '进攻', value: 'aggressive' }
                  ]}
                />
                <Select
                  value={selectedWorkflowPath}
                  onChange={setSelectedWorkflowPath}
                  options={workflows.map((item) => ({
                    label: item.name || item.path,
                    value: item.path
                  }))}
                  placeholder="选择AI选股Workflow"
                  style={{ width: 320, maxWidth: '100%' }}
                  allowClear
                />
              </Space>
              <Typography.Text type="secondary">最新交易日：{result?.latest_trade_date ?? '-'}</Typography.Text>
            </div>
            <Input.TextArea
              value={aiText}
              onChange={(event) => setAiText(event.target.value)}
              autoSize={{ minRows: 2, maxRows: 4 }}
              placeholder="输入自然语言选股需求"
            />
            <div className="toolbar-row">
              <Space wrap>
                <Tooltip title="解析自然语言并执行选股">
                  <Button type="primary" icon={<RobotOutlined />} onClick={() => runSafely(parseAiText())}>
                    AI解析选股
                  </Button>
                </Tooltip>
                <Tooltip title="根据近期行情、新闻舆情和多因子评分生成研究候选">
                  <Button icon={<ThunderboltOutlined />} onClick={() => runSafely(oneClickRecommend())}>
                    一键荐股
                  </Button>
                </Tooltip>
                <Button icon={<PlayCircleOutlined />} onClick={() => runSafely(run())}>
                  执行选股
                </Button>
                <Button icon={<ReloadOutlined />} onClick={reset}>
                  重置条件
                </Button>
                <Button icon={<SaveOutlined />} onClick={() => setSaveOpen(true)}>
                  保存策略
                </Button>
                <Button icon={<DownloadOutlined />} onClick={exportExcel}>
                  导出Excel
                </Button>
                <Button icon={<SyncOutlined />} onClick={() => runSafely(refreshDataInBackground())}>
                  后台刷新
                </Button>
              </Space>
            </div>
          </Space>
        </ProCard>
        {result?.diagnostics ? (
          <Alert
            showIcon
            type={result.diagnostics.warnings.length ? 'warning' : 'info'}
            message={`筛选诊断：返回 ${result.diagnostics.returned_count} / 命中 ${result.diagnostics.matched_count}`}
            description={diagnosticsDescription(result)}
          />
        ) : null}
        {recommendation ? (
          <ProCard bordered title={`一键荐股 · ${recommendation.risk_preference}`}>
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Typography.Paragraph>{recommendation.market_view}</Typography.Paragraph>
              <Typography.Text type="secondary">{recommendation.strategy}</Typography.Text>
              <div className="recommendation-list">
                {recommendation.recommendations.map((item) => (
                  <div className="recommendation-item" key={item.ts_code}>
                    <Space wrap align="center">
                      <Button type="link" onClick={() => navigate(`/stock/${item.ts_code}`)}>
                        {item.name} · {item.ts_code}
                      </Button>
                      <Tag color={ratingColor[item.rating] ?? 'default'}>{item.rating} {item.ai_score.toFixed(1)}</Tag>
                      <Tag color={item.source === 'llm' ? 'blue' : 'default'}>{item.source === 'llm' ? 'LLM' : '规则'}</Tag>
                      <Typography.Text strong>{item.action}</Typography.Text>
                    </Space>
                    <Typography.Paragraph ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>{item.reason}</Typography.Paragraph>
                    <Typography.Text type="warning">{item.risk}</Typography.Text>
                  </div>
                ))}
              </div>
              <Space direction="vertical" size={4}>
                {recommendation.risk_notes.map((note) => (
                  <Typography.Text key={note} type="secondary">· {note}</Typography.Text>
                ))}
                <Typography.Text type="secondary">{recommendation.disclaimer}</Typography.Text>
              </Space>
            </Space>
          </ProCard>
        ) : null}
        <StatisticCard.Group direction="row">
          <StatisticCard statistic={{ title: '命中股票', value: result?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '平均AI评分', value: ((result?.factor_distribution.ai ?? []).reduce((sum, item) => sum + item, 0) / Math.max(1, result?.factor_distribution.ai?.length ?? 0)).toFixed(1) }} />
          <StatisticCard statistic={{ title: '行业数量', value: Object.keys(result?.industry_distribution ?? {}).length }} />
        </StatisticCard.Group>
        <ProTable<StockScore>
          rowKey="ts_code"
          cardBordered
          search={false}
          options={false}
          columns={columns}
          dataSource={result?.rows ?? []}
          scroll={{ x: 1250 }}
          pagination={{ pageSize: 10, showSizeChanger: true }}
          rowSelection={{}}
          onRow={(record) => ({
            onClick: () => setSelected(record),
            onDoubleClick: () => navigate(`/stock/${record.ts_code}`)
          })}
        />
        <ProCard title={selected ? `${selected.name} 图表分析` : '图表分析'} bordered>
          <FactorCharts result={result} stockDetail={stockDetail} />
        </ProCard>
      </Space>
      <Modal title="保存当前策略" open={saveOpen} onCancel={() => setSaveOpen(false)} onOk={() => runSafely(saveStrategy())} destroyOnHidden>
        <ProForm form={saveForm} submitter={false} layout="vertical" initialValues={{ schedule_enabled: false, schedule_cron: '30 18 * * 1-5' }}>
          <ProFormTextArea name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]} fieldProps={{ autoSize: { minRows: 1, maxRows: 1 } }} />
          <ProFormTextArea name="remark" label="备注" fieldProps={{ autoSize: { minRows: 2, maxRows: 3 } }} />
          <Form.Item name="schedule_enabled" label="本地定时自动选股" valuePropName="checked">
            <Switch />
          </Form.Item>
          <ProFormTextArea name="schedule_cron" label="Cron表达式" fieldProps={{ autoSize: { minRows: 1, maxRows: 1 } }} />
        </ProForm>
      </Modal>
    </div>
  );
};

export default Workbench;
