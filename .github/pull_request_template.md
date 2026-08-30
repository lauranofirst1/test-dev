## 요약

<!-- 무엇을 왜 바꿨는지 2~4줄로 적어 주세요. -->

- 관련 이슈: <!-- 예: Closes #123 / 없음 -->
- PR 대상 브랜치: `test` <!-- 특별히 합의한 경우가 아니면 main으로 열지 않습니다. -->

## 변경 내용

-

## 검증

실행한 항목만 체크하고, 실행하지 못한 항목은 이유를 아래에 적어 주세요.

- [ ] Backend: `python -m pytest -q`
- [ ] Backend: `python -m alembic check`
- [ ] Backend security: `python -m pip_audit --local` / `python -m bandit -r src/festaflow -q`
- [ ] Frontend: `npm run typecheck`
- [ ] Frontend: `npm run test:share`
- [ ] Frontend: `npm run test:navigation`
- [ ] Frontend: `npm run build`
- [ ] UI 변경을 데스크톱에서 직접 확인함
- [ ] UI 변경을 390px 또는 실제 휴대폰에서 확인함

검증하지 못한 항목과 이유:

<!-- 없음 / 환경 제약과 대신 확인한 내용을 적어 주세요. -->

## DB · 환경 변수

- [ ] DB 스키마 변경 없음
- [ ] DB 스키마 변경이 있으며 Alembic migration을 포함함
- [ ] 새 환경 변수 없음
- [ ] 새 환경 변수가 있으며 `.env.example`과 문서를 갱신함

<!-- 해당하지 않는 선택지는 지우거나 체크하지 마세요. -->

## 보안 · 개인정보 확인

- [ ] `.env`, API 키, 토큰, 실제 비밀번호를 포함하지 않음
- [ ] 실제 학번·참여자 데이터, 업로드 파일, 운영 로그를 포함하지 않음
- [ ] `git diff --cached`로 커밋될 파일과 내용을 직접 확인함
- [ ] 인증·권한·쿠키·CORS 변경이 있다면 실패 경로까지 테스트함
- [ ] 새 의존성이 있다면 필요성과 lockfile 변경을 설명함

## 화면 자료

<!-- UI 변경이면 개인정보가 없는 전/후 화면을 첨부하세요. 아니면 "해당 없음". -->

## 알려진 제한 · 배포 시 주의

<!-- 없음 / 후속 작업, 호환성, migration 순서, 롤백 방법 등을 적어 주세요. -->
