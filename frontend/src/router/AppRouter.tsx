import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from '../layout/AppLayout';
import DecisionDashboard from '../pages/DecisionDashboard';
import PatternRadar from '../pages/PatternRadar';
import ReportCenter from '../pages/ReportCenter';
import StockDetail from '../pages/StockDetail';
import StockMarket from '../pages/StockMarket';
import StrategyLab from '../pages/StrategyLab';
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
            <DecisionDashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/workbench"
        element={
          <ProtectedRoute>
            <Workbench />
          </ProtectedRoute>
        }
      />
      <Route
        path="/strategy-lab"
        element={
          <ProtectedRoute>
            <StrategyLab />
          </ProtectedRoute>
        }
      />
      <Route
        path="/patterns"
        element={
          <ProtectedRoute>
            <PatternRadar />
          </ProtectedRoute>
        }
      />
      <Route
        path="/markets"
        element={
          <ProtectedRoute>
            <StockMarket />
          </ProtectedRoute>
        }
      />
      <Route
        path="/reports"
        element={
          <ProtectedRoute>
            <ReportCenter />
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
      <Route path="/stock" element={<Navigate to="/stock/000001.SZ" replace />} />
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
