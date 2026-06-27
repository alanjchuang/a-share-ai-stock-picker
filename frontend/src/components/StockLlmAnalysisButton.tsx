import { FileSearchOutlined } from '@ant-design/icons';
import { Alert, Button, List, Modal, Space, Tag, Typography } from 'antd';
import type { ButtonProps } from 'antd';
import { useState, type MouseEvent } from 'react';
import { api } from '../api/modules';
import type { StockLlmAnalysisResponse } from '../types';

interface StockLlmAnalysisButtonProps {
  tsCode: string;
  name?: string | null;
  buttonType?: ButtonProps['type'];
  size?: ButtonProps['size'];
  label?: string;
}

function requestErrorMessage(error: unknown): string {
  const maybeError = error as { response?: { data?: { message?: string } }; message?: string };
  return maybeError.response?.data?.message || maybeError.message || 'LLM解析失败，请稍后重试。';
}

const sectionTitles: Array<{ key: keyof Pick<StockLlmAnalysisResponse, 'key_points' | 'risks' | 'watch_items' | 'questions'>; title: string }> = [
  { key: 'key_points', title: '关注依据' },
  { key: 'risks', title: '风险提示' },
  { key: 'watch_items', title: '观察项' },
  { key: 'questions', title: '复盘问题' }
];

const StockLlmAnalysisButton = ({ tsCode, name, buttonType = 'link', size = 'small', label = '解析' }: StockLlmAnalysisButtonProps) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState<StockLlmAnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function analyze(event?: MouseEvent<HTMLElement>): Promise<void> {
    event?.stopPropagation();
    setOpen(true);
    setLoading(true);
    setError(null);
    try {
      setAnalysis(await api.analyzeStock(tsCode));
    } catch (nextError) {
      setError(requestErrorMessage(nextError));
    } finally {
      setLoading(false);
    }
  }

  const displayName = analysis?.name || name || tsCode;

  return (
    <>
      <Button type={buttonType} size={size} icon={<FileSearchOutlined />} loading={loading} onClick={(event) => void analyze(event)}>
        {label}
      </Button>
      <Modal
        title={`${displayName} · LLM解析`}
        open={open}
        footer={null}
        width={760}
        destroyOnHidden
        onCancel={() => setOpen(false)}
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          {error ? <Alert showIcon type="warning" message="解析失败" description={error} /> : null}
          {analysis ? (
            <>
              <Space wrap>
                <Tag color={analysis.source === 'llm' ? 'blue' : 'default'}>{analysis.source === 'llm' ? 'LLM' : '规则兜底'}</Tag>
                <Typography.Text type="secondary">{analysis.ts_code}</Typography.Text>
              </Space>
              <Typography.Paragraph style={{ marginBottom: 0 }}>{analysis.summary}</Typography.Paragraph>
              {sectionTitles.map((section) => (
                <div key={section.key}>
                  <Typography.Text strong>{section.title}</Typography.Text>
                  <List
                    size="small"
                    dataSource={analysis[section.key]}
                    locale={{ emptyText: '暂无' }}
                    renderItem={(item) => <List.Item>{item}</List.Item>}
                  />
                </div>
              ))}
              <Typography.Text type="secondary">{analysis.disclaimer}</Typography.Text>
            </>
          ) : null}
          {loading && !analysis ? <Alert showIcon type="info" message="正在生成个股解析" description="页面不会被锁住，可以继续查看其它股票。" /> : null}
        </Space>
      </Modal>
    </>
  );
};

export default StockLlmAnalysisButton;
