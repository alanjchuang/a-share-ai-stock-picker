import ReactECharts from 'echarts-for-react';
import type { EChartsOption } from 'echarts';
import type { KLinePoint, ScreeningResult, StockDetail } from '../types';

interface FactorChartsProps {
  result: ScreeningResult | null;
  stockDetail: StockDetail | null;
}

function buildKlineOption(kline: KLinePoint[]): EChartsOption {
  const dates = kline.map((item) => item.trade_date);
  const candle = kline.map((item) => [item.open, item.close, item.low, item.high]);
  return {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['K线', 'MA5', 'MA20', 'MA60', '成交量'] },
    grid: [
      { left: 48, right: 24, top: 36, height: 170 },
      { left: 48, right: 24, top: 230, height: 52 }
    ],
    xAxis: [
      { type: 'category', data: dates, boundaryGap: false },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } }
    ],
    yAxis: [{ scale: true }, { gridIndex: 1, splitNumber: 2 }],
    dataZoom: [{ type: 'inside' }, { show: true, bottom: 0, height: 18 }],
    series: [
      { name: 'K线', type: 'candlestick', data: candle },
      { name: 'MA5', type: 'line', data: kline.map((item) => item.ma5), showSymbol: false, smooth: true },
      { name: 'MA20', type: 'line', data: kline.map((item) => item.ma20), showSymbol: false, smooth: true },
      { name: 'MA60', type: 'line', data: kline.map((item) => item.ma60), showSymbol: false, smooth: true },
      { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: kline.map((item) => item.volume) }
    ]
  };
}

function buildIndustryOption(result: ScreeningResult | null): EChartsOption {
  const data = Object.entries(result?.industry_distribution ?? {}).map(([name, value]) => ({ name, value }));
  return {
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    series: [
      {
        name: '行业分布',
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '45%'],
        data
      }
    ]
  };
}

function buildSentimentOption(result: ScreeningResult | null): EChartsOption {
  const values = result?.factor_distribution.sentiment ?? [];
  const bins = [
    { name: '0-39', min: 0, max: 39 },
    { name: '40-59', min: 40, max: 59 },
    { name: '60-79', min: 60, max: 79 },
    { name: '80-100', min: 80, max: 100 }
  ];
  return {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: bins.map((item) => item.name) },
    yAxis: { type: 'value' },
    series: [
      {
        name: '舆情分数',
        type: 'bar',
        data: bins.map((bin) => values.filter((value) => value >= bin.min && value <= bin.max).length),
        itemStyle: { color: '#d9822b' }
      }
    ]
  };
}

function buildFactorOption(result: ScreeningResult | null): EChartsOption {
  const dist = result?.factor_distribution;
  const avg = (values: number[] | undefined) => (values && values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0);
  return {
    tooltip: { trigger: 'axis' },
    radar: {
      indicator: [
        { name: '基本面', max: 100 },
        { name: '技术', max: 100 },
        { name: '资金', max: 100 },
        { name: '舆情', max: 100 },
        { name: 'AI综合', max: 100 }
      ],
      radius: 88
    },
    series: [
      {
        name: '结果均值',
        type: 'radar',
        data: [
          {
            value: [avg(dist?.fundamental), avg(dist?.technical), avg(dist?.capital), avg(dist?.sentiment), avg(dist?.ai)],
            name: '平均分'
          }
        ],
        areaStyle: { opacity: 0.18 }
      }
    ]
  };
}

const emptyKlineOption: EChartsOption = {
  title: { text: '选择一只股票查看K线', left: 'center', top: 'middle', textStyle: { fontSize: 14, fontWeight: 400 } },
  xAxis: { show: false },
  yAxis: { show: false },
  series: []
};

const FactorCharts = ({ result, stockDetail }: FactorChartsProps) => (
  <div className="chart-grid">
    <ReactECharts className="chart-panel" option={stockDetail ? buildKlineOption(stockDetail.kline) : emptyKlineOption} notMerge />
    <ReactECharts className="chart-panel" option={buildFactorOption(result)} notMerge />
    <ReactECharts className="chart-panel" option={buildIndustryOption(result)} notMerge />
    <ReactECharts className="chart-panel" option={buildSentimentOption(result)} notMerge />
  </div>
);

export default FactorCharts;
