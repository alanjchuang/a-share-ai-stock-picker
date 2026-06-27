import { Spin } from 'antd';
import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import AppLayout from '../layout/AppLayout';

const DataCenter = lazy(() => import('../pages/DataCenter'));
const DecisionDashboard = lazy(() => import('../pages/DecisionDashboard'));
const EtfCenter = lazy(() => import('../pages/EtfCenter'));
const IntelligenceCenter = lazy(() => import('../pages/IntelligenceCenter'));
const PatternRadar = lazy(() => import('../pages/PatternRadar'));
const ReportCenter = lazy(() => import('../pages/ReportCenter'));
const StockDetail = lazy(() => import('../pages/StockDetail'));
const StockMarket = lazy(() => import('../pages/StockMarket'));
const StrategyLab = lazy(() => import('../pages/StrategyLab'));
const StrategyManager = lazy(() => import('../pages/StrategyManager'));
const SystemConfig = lazy(() => import('../pages/SystemConfig'));
const WatchlistCenter = lazy(() => import('../pages/WatchlistCenter'));
const Workbench = lazy(() => import('../pages/Workbench'));

const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
  const accessFlag = localStorage.getItem('a-share-local-access') ?? 'enabled';
  return accessFlag === 'enabled' ? children : <Navigate to="/" replace />;
};

const protectedPage = (children: JSX.Element) => (
  <ProtectedRoute>
    <Suspense
      fallback={
        <div className="route-loading">
          <Spin />
        </div>
      }
    >
      {children}
    </Suspense>
  </ProtectedRoute>
);

const AppRouter = () => (
  <Routes>
    <Route element={<AppLayout />}>
      <Route path="/" element={protectedPage(<DecisionDashboard />)} />
      <Route path="/workbench" element={protectedPage(<Workbench />)} />
      <Route path="/strategy-lab" element={protectedPage(<StrategyLab />)} />
      <Route path="/patterns" element={protectedPage(<PatternRadar />)} />
      <Route path="/markets" element={protectedPage(<StockMarket />)} />
      <Route path="/etfs" element={protectedPage(<EtfCenter />)} />
      <Route path="/reports" element={protectedPage(<ReportCenter />)} />
      <Route path="/data" element={protectedPage(<DataCenter />)} />
      <Route path="/intelligence" element={protectedPage(<IntelligenceCenter />)} />
      <Route path="/stock/:tsCode" element={protectedPage(<StockDetail />)} />
      <Route path="/stock" element={<Navigate to="/stock/000001.SZ" replace />} />
      <Route path="/strategies" element={protectedPage(<StrategyManager />)} />
      <Route path="/watchlist" element={protectedPage(<WatchlistCenter />)} />
      <Route path="/config" element={protectedPage(<SystemConfig />)} />
    </Route>
  </Routes>
);

export default AppRouter;
