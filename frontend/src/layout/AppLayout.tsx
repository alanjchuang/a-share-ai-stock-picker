import {
  AreaChartOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  MoonOutlined,
  SettingOutlined,
  StarOutlined,
  StockOutlined,
  SunOutlined
} from '@ant-design/icons';
import { Button, Layout, Menu, Space, Typography } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import DisclaimerBar from '../components/DisclaimerBar';
import { useAppStore } from '../store/useAppStore';

const { Header, Sider, Content } = Layout;
const stockDetailMenuKey = '/stock/000001.SZ';

const AppLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const themeMode = useAppStore((state) => state.themeMode);
  const setThemeMode = useAppStore((state) => state.setThemeMode);

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
        <Button
          aria-label="切换主题"
          icon={themeMode === 'dark' ? <SunOutlined /> : <MoonOutlined />}
          onClick={() => setThemeMode(themeMode === 'dark' ? 'light' : 'dark')}
        />
      </Header>
      <Layout>
        <Sider width={214} breakpoint="lg" collapsedWidth={64} className="app-sider">
          <Menu
            mode="inline"
            selectedKeys={[location.pathname.startsWith('/stock') ? stockDetailMenuKey : location.pathname]}
            onClick={(item) => navigate(item.key)}
            items={[
              { key: '/', icon: <AreaChartOutlined />, label: '选股工作台' },
              { key: '/watchlist', icon: <StarOutlined />, label: '自选股复盘' },
              { key: '/strategies', icon: <BarChartOutlined />, label: '策略管理' },
              { key: '/config', icon: <SettingOutlined />, label: '系统配置' },
              { key: stockDetailMenuKey, icon: <DatabaseOutlined />, label: '个股详情' }
            ]}
          />
        </Sider>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
};

export default AppLayout;
