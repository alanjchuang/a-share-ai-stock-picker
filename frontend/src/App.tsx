import { Spin } from 'antd';
import { BrowserRouter } from 'react-router-dom';
import AppRouter from './router/AppRouter';
import { useAppStore } from './store/useAppStore';

const App = () => {
  const globalLoading = useAppStore((state) => state.globalLoading);
  const themeMode = useAppStore((state) => state.themeMode);
  return (
    <div className={`app-shell ${themeMode}`}>
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
      {globalLoading ? (
        <div className="global-loading">
          <Spin tip="数据处理中" />
        </div>
      ) : null}
    </div>
  );
};

export default App;
