import { CopyOutlined, FileMarkdownOutlined, ReloadOutlined } from '@ant-design/icons';
import { Button, Empty, List, Space, Tag, Typography } from 'antd';
import { PageContainer, ProCard, StatisticCard } from '@ant-design/pro-components';
import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/modules';
import type { AnalysisReportOut } from '../types';
import { runSafely } from '../utils/async';
import { notifySuccess } from '../utils/feedback';

const ReportCenter = () => {
  const [reports, setReports] = useState<AnalysisReportOut[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);

  const activeReport = useMemo(
    () => reports.find((item) => item.id === activeId) ?? reports[0] ?? null,
    [activeId, reports]
  );

  async function loadReports(forceRefresh = false): Promise<void> {
    const data = await api.listReports(50, { forceRefresh });
    setReports(data);
    if (!activeId && data[0]) {
      setActiveId(data[0].id);
    }
  }

  async function generateDailyReport(): Promise<void> {
    setGenerating(true);
    try {
      const report = await api.generateDailyReport();
      const nextReports = await api.listReports(50, { forceRefresh: true });
      setReports(nextReports);
      setActiveId(report.id);
      notifySuccess('复盘报告已生成');
    } finally {
      setGenerating(false);
    }
  }

  async function copyReport(): Promise<void> {
    if (!activeReport) return;
    await navigator.clipboard.writeText(activeReport.content);
    notifySuccess('报告 Markdown 已复制');
  }

  useEffect(() => {
    runSafely(loadReports());
  }, []);

  return (
    <PageContainer
      title="报告中心"
      extra={[
        <Button key="generate" type="primary" icon={<FileMarkdownOutlined />} loading={generating} onClick={() => runSafely(generateDailyReport())}>
          生成今日复盘
        </Button>,
        <Button key="refresh" icon={<ReloadOutlined />} onClick={() => runSafely(loadReports(true))}>
          刷新
        </Button>
      ]}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: '历史报告', value: reports.length }} />
          <StatisticCard statistic={{ title: '当前报告', value: activeReport?.title ?? '-' }} />
          <StatisticCard statistic={{ title: '生成方式', value: activeReport?.source ?? 'deterministic' }} />
        </StatisticCard.Group>
        <div className="report-layout">
          <ProCard title="报告历史" bordered>
            {reports.length ? (
              <List
                className="report-list"
                dataSource={reports}
                renderItem={(item) => (
                  <List.Item
                    className={item.id === activeReport?.id ? 'report-list-item active' : 'report-list-item'}
                    onClick={() => setActiveId(item.id)}
                  >
                    <List.Item.Meta
                      title={
                        <Space size={6} wrap>
                          <Typography.Text strong>{item.title}</Typography.Text>
                          <Tag color={item.report_type === 'daily' ? 'blue' : 'default'}>{item.report_type}</Tag>
                        </Space>
                      }
                      description={item.created_at}
                    />
                  </List.Item>
                )}
              />
            ) : (
              <Empty description="暂无复盘报告" />
            )}
          </ProCard>
          <ProCard
            title={activeReport?.title ?? '复盘报告'}
            bordered
            extra={
              activeReport ? (
                <Button icon={<CopyOutlined />} onClick={() => runSafely(copyReport())}>
                  复制
                </Button>
              ) : null
            }
          >
            {activeReport ? (
              <pre className="report-markdown">{activeReport.content}</pre>
            ) : (
              <Empty description="生成一份报告后可查看市场复盘、风险警报和策略信号" />
            )}
          </ProCard>
        </div>
      </Space>
    </PageContainer>
  );
};

export default ReportCenter;
