# FestaFlow에 기여하기

팀 개발의 정본은 [GitHub · 로컬 실행 · PR 가이드](docs/12-team-github-guide.md)입니다.

핵심 규칙만 먼저 확인하세요.

1. `upstream/test`에서 `feat/*`, `fix/*`, `docs/*`, `chore/*` 브랜치를 만듭니다.
2. `.env`, 실제 키·학번·참여 데이터·업로드·로그를 커밋하지 않습니다.
3. `git add .` 대신 변경 파일을 이름으로 명시하고 `git diff --cached`를 읽습니다.
4. backend와 frontend 필수 검증을 실행하고 결과를 PR 템플릿에 기록합니다.
5. PR base는 `lauranofirst1/test-dev:test`입니다. `main`에는 직접 PR하지 않습니다.

보안 문제는 공개 Issue로 쓰지 말고 [SECURITY.md](SECURITY.md)의 비공개 제보 절차를
따르세요.
