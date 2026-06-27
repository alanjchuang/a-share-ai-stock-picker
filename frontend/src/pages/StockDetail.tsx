import { ArrowLeftOutlined, ReloadOutlined, StarOutlined } from '@ant-design/icons';
import { Button, Descriptions, Empty, List, Space, Tag, Typography, message } from 'antd';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/modules';
import type { StockDetail as StockDetailType } from '../types';
import { runSafely } from '../utils/async';

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
      { title: 'PE(TTM)', value: detail.base.pe_ttm?.toFixed(2) ?? '-' },
      { title: 'PB', value: detail.base.pb?.toFixed(2) ?? '-' },
      { title: 'ROE', value: `${detail.base.roe?.toFixed(2) ?? '-'}%` },
      { title: '舆情分', value: detail.base.sentiment_score.toFixed(0), suffix: detail.base.sentiment_label }
    ];
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
    message.success(`${detail.base.name} 已加入自选股`);
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
          <StatisticCard.Group>
            {metricCards.map((item) => (
              <StatisticCard key={item.title} statistic={item} />
            ))}
          </StatisticCard.Group>
          <ProCard bordered title="基础信息">
            <Descriptions column={{ xs: 1, sm: 2, md: 4 }} size="small">
              <Descriptions.Item label="行业">{detail.base.industry}</Descriptions.Item>
              <Descriptions.Item label="所属指数">{detail.base.index_names.join(' / ')}</Descriptions.Item>
              <Descriptions.Item label="最新收盘">{detail.base.close}</Descriptions.Item>
              <Descriptions.Item label="涨跌幅">{detail.base.pct_chg}%</Descriptions.Item>
              <Descriptions.Item label="营收同比">{detail.base.revenue_yoy}%</Descriptions.Item>
              <Descriptions.Item label="流通市值">{detail.base.circ_mv}亿</Descriptions.Item>
              <Descriptions.Item label="主力净流入">{detail.base.main_net_inflow}</Descriptions.Item>
              <Descriptions.Item label="评级">
                <Tag color={detail.base.rating === 'A' ? 'green' : detail.base.rating === 'B' ? 'blue' : 'gold'}>{detail.base.rating}</Tag>
              </Descriptions.Item>
            </Descriptions>
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
