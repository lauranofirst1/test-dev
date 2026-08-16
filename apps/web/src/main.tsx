import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom';

import './styles/tokens.css';
import './styles/app.css';
import { DiagnosisPage } from './pages/DiagnosisPage';
import { NewFestivalPage } from './pages/NewFestivalPage';
import { WorkspacePage } from './pages/WorkspacePage';

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <header className="topbar">
          <Link to="/" className="brand">
            FestaFlow <small>축제 기획 진단</small>
          </Link>
          <span className="muted">출처: ⓒ한국관광공사</span>
        </header>
        <Routes>
          <Route path="/" element={<WorkspacePage />} />
          <Route path="/festivals/new" element={<NewFestivalPage />} />
          <Route path="/festivals/:id/diagnosis" element={<DiagnosisPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
