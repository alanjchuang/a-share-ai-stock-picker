import { ClearOutlined, SaveOutlined, SearchOutlined, SyncOutlined } from '@ant-design/icons';
import { Button, Form, Space, Switch } from 'antd';
import { PageContainer, ProCard, ProForm, ProFormDigit, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/modules';
import type { AppConfig, WorkflowInfo } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

const SystemConfig = () => {
  const [form] = Form.useForm<AppConfig>();
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);

  useEffect(() => {
    runSafely(api.getConfig().then((config) => form.setFieldsValue(config)));
    runSafely(api.listWorkflows().then(setWorkflows));
  }, []);

  const workflowOptions = useMemo(
    () =>
      workflows.map((item) => ({
        label: item.name || item.path,
        value: item.path
      })),
    [workflows]
  );

  async function save(): Promise<void> {
    const values = await form.validateFields();
    await api.updateConfig(values);
    notifySuccess('配置已保存');
  }

  async function refresh(): Promise<void> {
    const provider = form.getFieldValue(['market_data', 'provider']) as AppConfig['market_data']['provider'] | undefined;
    await api.syncData(provider);
    notifySuccess('数据同步完成');
  }

  async function recalc(): Promise<void> {
    const result = await api.calculateFactors();
    notifySuccess(`因子缓存已刷新：${result.count} 只股票`);
  }

  async function testSearch(): Promise<void> {
    const values = await form.validateFields();
    await api.updateConfig(values);
    const result = await api.searchWeb({
      query: 'A股 沪深300 最新政策 财报 舆情',
      count: Math.min(values.search.default_count || 3, 3),
      search_type: values.search.default_search_type
    });
    notifySuccess(`火山搜索连通：${result.items.length} 条结果`);
  }

  return (
    <PageContainer
      title="系统配置"
      extra={[
        <Button key="save" type="primary" icon={<SaveOutlined />} onClick={() => runSafely(save())}>
          保存配置
        </Button>,
        <Button key="sync" icon={<SyncOutlined />} onClick={() => runSafely(refresh())}>
          同步行情
        </Button>,
        <Button key="clear" icon={<ClearOutlined />} onClick={() => runSafely(recalc())}>
          清理并重算缓存
        </Button>
      ]}
    >
      <ProForm<AppConfig> form={form} submitter={false} layout="vertical">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <ProCard title="行情财务数据源" bordered>
            <Space wrap align="start">
              <ProFormSelect
                name={['market_data', 'provider']}
                label="默认数据源"
                width="sm"
                options={[
                  { label: '自动', value: 'auto' },
                  { label: 'AKShare', value: 'akshare' },
                  { label: 'Tushare', value: 'tushare' },
                  { label: '演示数据', value: 'demo' }
                ]}
              />
              <Form.Item name={['market_data', 'fallback_to_demo']} label="失败回退演示数据" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={['market_data', 'clear_factor_cache_on_sync']} label="同步前清理因子缓存" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Space>
          </ProCard>
          <ProCard title="AKShare配置" bordered>
            <Space wrap align="start">
              <Form.Item name={['akshare', 'enabled']} label="启用AKShare" valuePropName="checked">
                <Switch />
              </Form.Item>
              <ProFormSelect
                name={['akshare', 'adjust']}
                label="K线复权"
                width="xs"
                options={[
                  { label: '前复权', value: 'qfq' },
                  { label: '后复权', value: 'hfq' },
                  { label: '不复权', value: '' }
                ]}
              />
              <ProFormText name={['akshare', 'default_start_date']} label="默认开始日期" width="sm" />
              <ProFormText name={['akshare', 'default_end_date']} label="默认结束日期" width="sm" />
              <ProFormDigit name={['akshare', 'request_interval_seconds']} label="请求间隔秒" min={0} fieldProps={{ step: 0.05 }} />
              <ProFormDigit name={['akshare', 'max_history_symbols']} label="历史K线股票上限" min={0} />
              <ProFormDigit name={['akshare', 'max_financial_symbols']} label="财务指标股票上限" min={0} />
              <ProFormDigit name={['akshare', 'max_news_symbols']} label="新闻股票上限" min={0} />
              <ProFormDigit name={['akshare', 'max_metadata_symbols']} label="基础信息股票上限" min={0} />
            </Space>
          </ProCard>
          <ProCard title="Tushare配置" bordered>
            <Space wrap align="start">
              <Form.Item name={['tushare', 'enabled']} label="启用Tushare" valuePropName="checked">
                <Switch />
              </Form.Item>
              <ProFormText.Password name={['tushare', 'token']} label="Tushare Token" width="lg" />
              <ProFormText name={['tushare', 'default_start_date']} label="默认开始日期" width="sm" />
              <ProFormText name={['tushare', 'default_trade_date']} label="指定交易日" width="sm" />
              <ProFormDigit name={['tushare', 'request_interval_seconds']} label="请求间隔秒" min={0} fieldProps={{ step: 0.05 }} />
            </Space>
          </ProCard>
          <ProCard title="LLM大模型配置" bordered>
            <Space wrap align="start">
              <ProFormSelect
                name={['llm', 'provider']}
                label="Provider"
                width="sm"
                options={[
                  { label: '关键词规则', value: 'heuristic' },
                  { label: 'OpenAI兼容', value: 'openai' },
                  { label: '通义千问兼容', value: 'qwen' },
                  { label: '本地Transformers', value: 'local' }
                ]}
              />
              <ProFormText name={['llm', 'api_base']} label="API地址" width="lg" />
              <ProFormText.Password name={['llm', 'api_key']} label="API Key" width="md" />
              <ProFormText name={['llm', 'model']} label="模型" width="sm" />
              <ProFormDigit name={['llm', 'temperature']} label="温度" min={0} max={2} fieldProps={{ step: 0.1 }} />
              <ProFormDigit name={['llm', 'max_tokens']} label="Max Tokens" min={256} />
              <ProFormDigit name={['llm', 'timeout_seconds']} label="超时秒" min={5} />
              <ProFormDigit name={['llm', 'num_retries']} label="重试次数" min={1} max={10} />
              <ProFormText name={['llm', 'local_model_path']} label="本地模型路径" width="lg" />
            </Space>
          </ProCard>
          <ProCard
            title="火山搜索配置"
            bordered
            extra={
              <Button icon={<SearchOutlined />} onClick={() => runSafely(testSearch())}>
                测试搜索
              </Button>
            }
          >
            <Space wrap align="start">
              <Form.Item name={['search', 'enabled']} label="启用火山搜索" valuePropName="checked">
                <Switch />
              </Form.Item>
              <ProFormText name={['search', 'base_url']} label="搜索API地址" width="lg" />
              <ProFormText.Password name={['search', 'api_key']} label="搜索API Key" width="md" />
              <ProFormText name={['search', 'model']} label="模型标识" width="sm" />
              <ProFormDigit name={['search', 'timeout_seconds']} label="超时秒" min={1} />
              <ProFormDigit name={['search', 'default_count']} label="默认条数" min={1} max={20} />
              <ProFormDigit name={['search', 'max_count']} label="最大条数" min={1} max={20} />
              <ProFormSelect
                name={['search', 'default_search_type']}
                label="默认类型"
                width="xs"
                options={[
                  { label: '网页', value: 'web' },
                  { label: '图片', value: 'image' },
                  { label: '摘要网页', value: 'web_summary' }
                ]}
              />
              <Form.Item name={['search', 'need_summary']} label="返回摘要" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={['search', 'need_content']} label="返回正文" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Space>
          </ProCard>
          <ProCard title="选股Workflow" bordered>
            <Space wrap align="start">
              <Form.Item name={['workflow', 'enabled']} label="启用Workflow" valuePropName="checked">
                <Switch />
              </Form.Item>
              <ProFormSelect name={['workflow', 'default_path']} label="默认Workflow" width="lg" options={workflowOptions} allowClear />
              <Form.Item name={['workflow', 'trace_payload_preview']} label="记录步骤预览" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Space>
          </ProCard>
          <ProCard title="全局过滤规则" bordered>
            <Space wrap align="start">
              <Form.Item name={['filters', 'exclude_st']} label="剔除ST/*ST" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item name={['filters', 'exclude_paused']} label="剔除停牌" valuePropName="checked">
                <Switch />
              </Form.Item>
              <ProFormDigit name={['filters', 'new_stock_days']} label="次新股阈值天数" min={0} />
              <ProFormDigit name={['filters', 'min_market_cap']} label="最小总市值" min={0} />
            </Space>
          </ProCard>
          <ProCard title="综合评分权重" bordered>
            <Space wrap align="start">
              <ProFormDigit name={['weights', 'fundamental']} label="基本面" min={0} />
              <ProFormDigit name={['weights', 'technical']} label="技术" min={0} />
              <ProFormDigit name={['weights', 'capital']} label="资金" min={0} />
              <ProFormDigit name={['weights', 'sentiment']} label="舆情" min={0} />
            </Space>
          </ProCard>
          <ProCard title="调度与服务" bordered>
            <Space wrap align="start">
              <Form.Item name={['scheduler', 'enabled']} label="启用定时同步" valuePropName="checked">
                <Switch />
              </Form.Item>
              <ProFormText name={['scheduler', 'daily_sync_cron']} label="每日同步Cron" width="sm" />
              <ProFormText name={['server', 'host']} label="服务Host" width="sm" />
              <ProFormDigit name={['server', 'port']} label="服务端口" min={1} max={65535} />
              <ProFormSelect name={['server', 'cors_origins']} label="CORS Origins" mode="tags" width="lg" />
            </Space>
          </ProCard>
        </Space>
      </ProForm>
    </PageContainer>
  );
};

export default SystemConfig;
