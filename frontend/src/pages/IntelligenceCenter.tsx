import { GlobalOutlined, SaveOutlined, SearchOutlined, SettingOutlined } from '@ant-design/icons';
import { Alert, Button, Input, List, Select, Space, Tag, Typography } from 'antd';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import type { AppConfig, SearchType, WebSearchItem, WebSearchResponse } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

const quickQueries = [
  'A股 今日 政策 资金面 行业机会',
  '半导体 国产替代 A股 最新消息',
  '人工智能 算力 服务器 A股 订单',
  '新能源 储能 光伏 A股 产业链',
  '医药 创新药 A股 政策 集采'
];

function displayHost(item: WebSearchItem): string {
  if (item.site_name) return item.site_name;
  try {
    return new URL(item.url).hostname;
  } catch {
    return item.url;
  }
}

const IntelligenceCenter = () => {
  const navigate = useNavigate();
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [query, setQuery] = useState(quickQueries[0]);
  const [searchType, setSearchType] = useState<SearchType>('web_summary');
  const [count, setCount] = useState(8);
  const [result, setResult] = useState<WebSearchResponse | null>(null);
  const searchReady = Boolean(config?.search.enabled && config.search.api_key && config.search.base_url);

  const summaryText = useMemo(() => {
    if (!result) return '';
    return result.items
      .slice(0, 6)
      .map((item, index) => `${index + 1}. ${item.title}\n${item.summary || item.snippet}`)
      .join('\n\n');
  }, [result]);

  useEffect(() => {
    runSafely(
      api.getConfig().then((nextConfig) => {
        setConfig(nextConfig);
        setSearchType(nextConfig.search.default_search_type);
        setCount(Math.min(nextConfig.search.default_count || 8, nextConfig.search.max_count || 10));
      })
    );
  }, []);

  async function search(): Promise<void> {
    if (!searchReady) return;
    setResult(
      await api.searchWeb({
        query,
        count,
        search_type: searchType,
        need_summary: true,
        need_content: false
      })
    );
  }

  async function saveBriefing(): Promise<void> {
    if (!summaryText) return;
    await api.createWatchlistNote({
      note_type: 'market_intelligence',
      content: `# ${query}\n\n${summaryText}`
    });
    notifySuccess('情报摘要已保存到自选股复盘笔记');
  }

  return (
    <PageContainer
      title="市场情报"
      extra={[
        <Button key="save" icon={<SaveOutlined />} disabled={!summaryText} onClick={() => runSafely(saveBriefing())}>
          保存摘要
        </Button>,
        <Button key="config" icon={<SettingOutlined />} onClick={() => navigate('/config')}>
          搜索配置
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {!searchReady ? (
          <Alert
            showIcon
            type="warning"
            message="火山搜索尚未配置"
            description="请在系统配置页填写搜索 API 地址、API Key 并启用搜索。配置完成前，本页不会发起外部搜索。"
            action={
              <Button size="small" type="primary" onClick={() => navigate('/config')}>
                去配置
              </Button>
            }
          />
        ) : (
          <Alert showIcon type="info" message={`当前搜索源：${config?.search.model || 'volc-search'}，只在点击搜索时请求外部接口。`} />
        )}
        <ProCard bordered>
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Space.Compact style={{ width: '100%' }}>
              <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入政策、行业、个股或题材关键词" />
              <Button type="primary" icon={<SearchOutlined />} disabled={!searchReady || !query.trim()} onClick={() => runSafely(search())}>
                搜索
              </Button>
            </Space.Compact>
            <Space wrap>
              <Select<SearchType>
                value={searchType}
                onChange={setSearchType}
                options={[
                  { label: '网页摘要', value: 'web_summary' },
                  { label: '网页', value: 'web' },
                  { label: '图片', value: 'image' }
                ]}
                style={{ width: 120 }}
              />
              <Select
                value={count}
                onChange={setCount}
                options={[5, 8, 10, 12, 15].map((value) => ({ label: `${value} 条`, value }))}
                style={{ width: 96 }}
              />
              {quickQueries.map((item) => (
                <Tag.CheckableTag key={item} checked={item === query} onChange={() => setQuery(item)}>
                  {item}
                </Tag.CheckableTag>
              ))}
            </Space>
          </Space>
        </ProCard>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '结果数', value: result?.total ?? 0 }} />
          <StatisticCard statistic={{ title: '搜索类型', value: result?.search_type ?? searchType }} />
          <StatisticCard statistic={{ title: '请求耗时', value: result?.time_cost_ms ? `${result.time_cost_ms} ms` : '-' }} />
          <StatisticCard statistic={{ title: 'Request IDs', value: result?.request_ids.length ?? 0 }} />
        </StatisticCard.Group>
        <ProCard title="情报结果" bordered>
          {result?.items.length ? (
            <List<WebSearchItem>
              className="intelligence-list"
              dataSource={result.items}
              renderItem={(item) => (
                <List.Item
                  actions={[
                    <Button key="open" type="link" href={item.url} target="_blank" rel="noreferrer" icon={<GlobalOutlined />}>
                      打开
                    </Button>
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space wrap size={8}>
                        <Typography.Text strong>{item.title}</Typography.Text>
                        <Tag>{displayHost(item)}</Tag>
                        {item.publish_time ? <Tag color="blue">{item.publish_time}</Tag> : null}
                      </Space>
                    }
                    description={
                      <Space direction="vertical" size={6} style={{ width: '100%' }}>
                        <Typography.Paragraph ellipsis={{ rows: 2, expandable: true }}>{item.summary || item.snippet}</Typography.Paragraph>
                        {item.content ? <Typography.Paragraph type="secondary" ellipsis={{ rows: 3, expandable: true }}>{item.content}</Typography.Paragraph> : null}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          ) : (
            <Typography.Text type="secondary">配置搜索后输入关键词，适合复盘政策、题材和个股新闻。</Typography.Text>
          )}
        </ProCard>
      </Space>
    </PageContainer>
  );
};

export default IntelligenceCenter;
