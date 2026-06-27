import { Spin } from 'antd';
import { BrowserRouter } from 'react-router-dom';
import AppRouter from './router/AppRouter';
import { useAppStore } from './store/useAppStore';

const App = () => {
  const globalLoading = useAppStore((state) => state.globalLoading);
  const themeMode = useAppStore((state) => state.themeMode);
  return (
    <div className={`app-shell ${themeMode}`}>
      <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
        <AppRouter />
      </BrowserRouter>
      {globalLoading ? <Spin fullscreen tip="数据处理中" /> : null}
    </div>
  );
};

export default App;
