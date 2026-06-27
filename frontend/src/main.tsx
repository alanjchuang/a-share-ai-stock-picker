import React from 'react';
import ReactDOM from 'react-dom/client';
import { App as AntApp, ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import { useAppStore } from './store/useAppStore';
import './styles/global.less';

const Root = () => {
  const themeMode = useAppStore((state) => state.themeMode);
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: themeMode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: '#1f7a8c',
          borderRadius: 6,
          fontSize: 13,
          wireframe: false
        }
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  );
};

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
