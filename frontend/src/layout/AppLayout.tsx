import {
  AreaChartOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  HddOutlined,
  LineChartOutlined,
  MoonOutlined,
  RadarChartOutlined,
  SettingOutlined,
  StarOutlined,
  StockOutlined,
  SunOutlined
} from '@ant-design/icons';
import { Alert, Button, Layout, Menu, Space, Tag, Tooltip, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api/modules';
import DisclaimerBar from '../components/DisclaimerBar';
import { useAppStore } from '../store/useAppStore';
import type { AppConfig } from '../types';
import { runSafely } from '../utils/async';

const { Header, Sider, Content } = Layout;
const stockDetailMenuKey = '/stock/000001.SZ';

function modeTag(config: AppConfig | null): { color: string; text: string; tooltip: string } {
  const provider = config?.market_data.provider ?? 'auto';
  if (provider === 'demo') {
    return {
      color: 'red',
      text: 'DEMO模式',
      tooltip: '当前使用演示数据，一键荐股会要求切换到真实数据源。点击进入系统配置。'
    };
  }
  if (provider === 'akshare') {
    return { color: 'green', text: 'AKShare数据', tooltip: '当前默认使用 AKShare 真实公开数据源。点击进入系统配置。' };
  }
  if (provider === 'tushare') {
    return { color: 'blue', text: 'Tushare数据', tooltip: '当前默认使用 Tushare 数据源。点击进入系统配置。' };
  }
  return {
    color: config?.market_data.fallback_to_demo ? 'gold' : 'cyan',
    text: config?.market_data.fallback_to_demo ? 'AUTO·DEMO兜底' : 'AUTO真实数据',
    tooltip: config?.market_data.fallback_to_demo
      ? '当前为自动数据源，并允许失败回退演示数据。线上使用建议关闭演示回退。点击进入系统配置。'
      : '当前为自动真实数据源。点击进入系统配置。'
  };
}

const AppLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const themeMode = useAppStore((state) => state.themeMode);
  const setThemeMode = useAppStore((state) => state.setThemeMode);
  const lastError = useAppStore((state) => state.lastError);
  const setLastError = useAppStore((state) => state.setLastError);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const tag = modeTag(config);

  useEffect(() => {
    const refreshConfig = () => runSafely(api.getConfig().then(setConfig));
    const handleConfigUpdated = (event: Event) => {
      const nextConfig = (event as CustomEvent<AppConfig>).detail;
      if (nextConfig) {
        setConfig(nextConfig);
      } else {
        refreshConfig();
      }
    };

    refreshConfig();
    window.addEventListener('app-config-updated', handleConfigUpdated);
    return () => window.removeEventListener('app-config-updated', handleConfigUpdated);
  }, []);

  return (
    <Layout className="layout-root">
      <DisclaimerBar />
      <Header className="app-header">
        <Space size={12}>
          <StockOutlined className="brand-icon" />
          <Typography.Title level={4} className="brand-title">
            A股多因子智能选股
          </Typography.Title>
        </Space>
        <Space size={8} className="header-actions">
          <Tooltip title={tag.tooltip}>
            <Button type="text" size="small" onClick={() => navigate('/config')}>
              <Tag color={tag.color} className="mode-tag">
                {tag.text}
              </Tag>
            </Button>
          </Tooltip>
          <Button
            aria-label="切换主题"
            icon={themeMode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
            onClick={() => setThemeMode(themeMode === 'dark' ? 'light' : 'dark')}
          />
        </Space>
      </Header>
      <Layout>
        <Sider width={214} breakpoint="lg" collapsedWidth={64} className="app-sider">
          <Menu
            mode="inline"
            selectedKeys={[location.pathname.startsWith('/stock') ? stockDetailMenuKey : location.pathname]}
            onClick={(item) => navigate(item.key)}
            items={[
              { key: '/', icon: <DashboardOutlined />, label: '决策仪表盘' },
              { key: '/workbench', icon: <AreaChartOutlined />, label: '选股工作台' },
              { key: '/markets', icon: <LineChartOutlined />, label: '行情选择' },
              { key: '/data', icon: <HddOutlined />, label: '数据中心' },
              { key: '/strategy-lab', icon: <ExperimentOutlined />, label: '策略实验室' },
              { key: '/patterns', icon: <RadarChartOutlined />, label: '形态雷达' },
              { key: '/reports', icon: <FileTextOutlined />, label: '报告中心' },
              { key: '/watchlist', icon: <StarOutlined />, label: '自选股复盘' },
              { key: '/strategies', icon: <BarChartOutlined />, label: '策略管理' },
              { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
              { key: stockDetailMenuKey, icon: <DatabaseOutlined />, label: '个股详情' }
            ]}
          />
        </Sider>
        <Content className="app-content">
          {lastError ? (
            <Alert
              showIcon
              closable
              type="error"
              message="请求失败"
              description={lastError}
              onClose={() => setLastError(null)}
              style={{ marginBottom: 12 }}
            />
          ) : null}
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
