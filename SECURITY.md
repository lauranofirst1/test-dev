# FestaFlow 보안 정책

## 취약점 제보

취약점, 유출된 키, 실제 참여자 데이터 노출은 공개 Issue나 PR 댓글에 적지 마세요.
저장소의 **Security → Report a vulnerability**가 활성화되어 있으면 private report를
사용하고, 그렇지 않으면 저장소 소유자에게 비공개 채널로 알립니다.

제보에는 재현에 필요한 최소 정보만 포함합니다. 실제 API 키, 세션 토큰, 학번,
이메일, 운영 DB 사본은 첨부하지 말고 마스킹된 예시를 사용합니다.

## 지원 범위

- `test`: 다음 릴리스 후보와 보안 수정의 기본 PR 대상
- `main`: 팀 검증을 마친 안정 버전
- 개인 기능 브랜치와 오래된 commit: 별도 지원하지 않음

## 배포 보안 기준

로컬이 아닌 환경은 다음 값을 만족하지 않으면 API가 부팅을 거부합니다.

- 예측 불가능한 32자 이상 `JWT_SECRET`
- `SESSION_COOKIE_SECURE=true`
- 경로 없는 HTTPS `PUBLIC_WEB_ORIGIN`
- 실제 API 호스트만 넣은 `TRUSTED_HOSTS` (`*` 금지)
- HTTPS origin만 넣은 `CORS_ORIGINS`
- `DEMO_MODE=false`

로컬 `DEMO_MODE`, `X-Organization-Id` 폴백, 테스트 시드 계정은 운영 인증 수단이
아닙니다. 운영 배포에서는 HTTPS, SMTP, 백업·복구, 데이터 보존·삭제 정책을 별도로
검증해야 합니다. 비밀번호 재설정과 공개 참여 API에는 프록시 또는 애플리케이션
수준의 요청 속도 제한과 남용 모니터링도 적용합니다.

## 의존성과 수정 원칙

PR CI는 프런트 production dependency audit, 타입 검사, 보안 회귀 테스트, 빌드,
Python dependency audit·정적 보안 분석, 백엔드 테스트와 migration 일치를 검사합니다.
Dependabot은 npm, pip, GitHub Actions를 매주 확인합니다. 보안 수정은 먼저 `test`에
PR로 보내고 검증 후 `main`으로 승격합니다.
