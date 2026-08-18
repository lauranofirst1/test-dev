import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import './styles/tokens.css';
import './styles/app.css';
import { AudienceLayout, PlannerLayout } from './layouts';
import { BoothsPage } from './pages/BoothsPage';
import { DiagnosisPage } from './pages/DiagnosisPage';
import { JoinPage } from './pages/JoinPage';
import { NewFestivalPage } from './pages/NewFestivalPage';
import { ScanPage } from './pages/ScanPage';
import { WorkspacePage } from './pages/WorkspacePage';

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          {/* 기획자·운영자 */}
          <Route element={<PlannerLayout />}>
            <Route path="/" element={<WorkspacePage />} />
            <Route path="/festivals/new" element={<NewFestivalPage />} />
            <Route path="/festivals/:id/diagnosis" element={<DiagnosisPage />} />
            <Route path="/festivals/:id/booths" element={<BoothsPage />} />
          </Route>

          {/* 관객 — 로그인 없이 축제 링크로 들어온다. 헤더가 다르다. */}
          <Route element={<AudienceLayout />}>
            <Route path="/join/:id" element={<JoinPage />} />
            <Route path="/join/:id/scan" element={<ScanPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
