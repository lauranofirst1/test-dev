import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import './styles/tokens.css';
import './styles/app.css';
import './styles/paper.css';
import './styles/consumer.css';
// 콘솔 전용. app.css 를 덮으므로 반드시 뒤에 온다.
import './styles/console.css';
import { AudienceLayout, PlannerLayout } from './layouts';
import { RequireAccount } from './components/RequireAccount';
import { BoothGrantPage } from './pages/BoothGrantPage';
import { BoothPosterPage } from './pages/BoothPosterPage';
import { BoothQrPage } from './pages/BoothQrPage';
import { BoothsPage } from './pages/BoothsPage';
import { CheckInPage } from './pages/CheckInPage';
import { CheckpointScreenPage } from './pages/CheckpointScreenPage';
import { DashboardPage } from './pages/DashboardPage';
import { DiagnosisPage } from './pages/DiagnosisPage';
import { ExhibitionPage } from './pages/ExhibitionPage';
import { ExperiencePage } from './pages/ExperiencePage';
import { ExplorePage } from './pages/ExplorePage';
import { ExhibitsAdminPage } from './pages/ExhibitsAdminPage';
import { JoinPage } from './pages/JoinPage';
import { FlowPage } from './pages/FlowPage';
import { LoginPage } from './pages/LoginPage';
import {
  PasswordResetConfirmPage,
  PasswordResetRequestPage,
} from './pages/PasswordResetPage';
import { StaffAdminPage } from './pages/StaffAdminPage';
import { StaffLoginPage } from './pages/StaffLoginPage';
import { JudgingPage } from './pages/JudgingPage';
import { LecturesPage } from './pages/LecturesPage';
import { MyLecturesPage } from './pages/MyLecturesPage';
import { NewFestivalPage } from './pages/NewFestivalPage';
import { OverviewPage } from './pages/OverviewPage';
import { PrizeClaimPage } from './pages/PrizeClaimPage';
import { ReportPage } from './pages/ReportPage';
import { ScanPage } from './pages/ScanPage';
import { VerifyCertificatePage } from './pages/VerifyCertificatePage';
import { WorkspacePage } from './pages/WorkspacePage';

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 30_000 } },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          {/* 로그인·회원가입은 세션이 없어도 열려야 한다. */}
          <Route path="/login" element={<LoginPage />} />
          {/* 스태프는 운영자가 준 초대 링크로 들어온다. */}
          <Route path="/staff/login" element={<StaffLoginPage />} />
          {/* 비밀번호 재설정 — 세션이 없어도 열려야 한다. */}
          <Route path="/reset-password-request" element={<PasswordResetRequestPage />} />
          <Route path="/reset-password" element={<PasswordResetConfirmPage />} />

          {/* 기획자·운영자 — 기관 세션이 있어야 열린다. */}
          <Route element={<PlannerLayout />}>
            <Route path="/" element={<RequireAccount><WorkspacePage /></RequireAccount>} />
            <Route path="/festivals/new" element={<RequireAccount><NewFestivalPage /></RequireAccount>} />
            {/* 축제에 들어가면 처음 열리는 화면. 예전에는 진단이 먼저 열렸는데,
                진단은 기획 단계에 몇 번 하고 마는 일이라 매일 여는 화면이
                아니었습니다. */}
            <Route path="/festivals/:id" element={<RequireAccount><OverviewPage /></RequireAccount>} />
            <Route path="/festivals/:id/diagnosis" element={<RequireAccount><DiagnosisPage /></RequireAccount>} />
            {/* 기획 수정은 이제 진단 화면의 탭이다. 진단 → 교정 → 재진단이
                한 루프인데 화면이 둘로 갈라져 있으면, 고치러 가는 순간 점수가
                사라져 무엇을 고쳐야 점수가 오르는지 보면서 고칠 수 없다.
                예전 주소는 살려 둔다 — 북마크와 이미 나간 링크가 있다. */}
            <Route
              path="/festivals/:id/edit"
              element={<Navigate to="../diagnosis?tab=plan" replace relative="path" />}
            />
            {/* 축제 당일 띄워 두는 화면. 참여 편중 지표와 확인 요청 카드. */}
            <Route path="/festivals/:id/dashboard" element={<RequireAccount><DashboardPage /></RequireAccount>} />
            {/* 축제가 끝난 뒤 여는 화면. 목표 대비 실제와 다음 축제 개선안. */}
            <Route path="/festivals/:id/report" element={<RequireAccount><ReportPage /></RequireAccount>} />
            <Route path="/festivals/:id/booths" element={<RequireAccount><BoothsPage /></RequireAccount>} />
          {/* 부스에 띄워 두는 회전 QR. 관객이 찍을 대상이 여기서 나온다. */}
          <Route path="/festivals/:id/booths/:boothId/qr" element={<BoothQrPage />} />
          {/* 인쇄용 안내문 — 종이에 뽑아 부스에 붙인다. `poster?all=1` 은 전 부스. */}
          <Route path="/festivals/:id/booths/poster" element={<BoothPosterPage />} />
          <Route path="/festivals/:id/booths/:boothId/poster" element={<BoothPosterPage />} />
          {/* 경품 수령대 — 당첨된 관객에게 실물을 건네는 곳. */}
          <Route path="/festivals/:id/claim" element={<RequireAccount><PrizeClaimPage /></RequireAccount>} />
          {/* 특강 출결 — 운영자가 체크인을 열고, 강의실 스크린에 QR 을 띄운다. */}
          <Route path="/festivals/:id/lectures" element={<RequireAccount><LecturesPage /></RequireAccount>} />
          {/* 전시 심사 — 작품·항목 관리와 시상 집계, 그리고 심사위원 심사표. */}
          <Route path="/festivals/:id/exhibits" element={<RequireAccount><ExhibitsAdminPage /></RequireAccount>} />
          <Route path="/festivals/:id/staff" element={<RequireAccount><StaffAdminPage /></RequireAccount>} />
          <Route path="/festivals/:id/judging" element={<JudgingPage />} />
          <Route
            path="/festivals/:id/lectures/:sessionId/checkin/:checkpointId"
            element={<CheckpointScreenPage />}
          />
          </Route>

          {/* 부스 스태프 — 축제 당일 8시간 내내 열려 있는 화면.
              기획자 껍데기를 쓰지 않는다. 부스 담당자는 이 도구의 사용자가 아니라
              오늘 하루 여기 서 있는 사람이고, 축제 목록으로 나가는 링크가 필요 없다. */}
          <Route path="/booth/festivals/:id" element={<BoothGrantPage />} />

          {/* 관객 — 로그인 없이 축제 링크로 들어온다. 헤더가 다르다. */}
          <Route element={<AudienceLayout />}>
            <Route path="/join/:id" element={<JoinPage />} />
            <Route path="/join/:id/explore" element={<ExplorePage />} />
            <Route path="/join/:id/flow" element={<FlowPage />} />
            <Route path="/join/:id/experience/:sourceType/:sourceId" element={<ExperiencePage />} />
            <Route path="/join/:id/scan" element={<ScanPage />} />
          {/* 특강 출결 — 학생이 보는 쪽. */}
          <Route path="/join/:id/lectures" element={<MyLecturesPage />} />
          <Route path="/join/:id/checkin" element={<CheckInPage />} />
          <Route path="/join/:id/exhibition" element={<ExhibitionPage />} />
          </Route>

          {/* 공결 확인 — 교수님이 계정 없이 여는 화면. 어떤 껍데기도 쓰지 않는다.
              이 화면의 사용자는 이 제품을 처음 보고, 다시 올 일도 없다. */}
          <Route path="/verify/:id/:code" element={<VerifyCertificatePage />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
