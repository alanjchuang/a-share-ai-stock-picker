import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from '../layout/AppLayout';
import StockDetail from '../pages/StockDetail';
import StrategyManager from '../pages/StrategyManager';
import SystemConfig from '../pages/SystemConfig';
import WatchlistCenter from '../pages/WatchlistCenter';
import Workbench from '../pages/Workbench';

const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
  const accessFlag = localStorage.getItem('a-share-local-access') ?? 'enabled';
  return accessFlag === 'enabled' ? children : <Navigate to="/" replace />;
};

const AppRouter = () => (
  <Routes>
    <Route element={<AppLayout />}>
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Workbench />
          </ProtectedRoute>
        }
      />
      <Route
        path="/stock/:tsCode"
        element={
          <ProtectedRoute>
            <StockDetail />
          </ProtectedRoute>
        }
      />
      <Route path="/stock" element={<Navigate to="/" replace />} />
      <Route
        path="/strategies"
        element={
          <ProtectedRoute>
            <StrategyManager />
          </ProtectedRoute>
        }
      />
      <Route
        path="/watchlist"
        element={
          <ProtectedRoute>
            <WatchlistCenter />
          </ProtectedRoute>
        }
      />
      <Route
        path="/config"
        element={
          <ProtectedRoute>
            <SystemConfig />
          </ProtectedRoute>
        }
      />
    </Route>
  </Routes>
);

export default AppRouter;
