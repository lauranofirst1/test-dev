# 팀 GitHub · 로컬 실행 · PR 가이드

이 문서는 FestaFlow를 처음 받은 팀원이 **자기 브랜치에서 실행하고, 테스트하고,
안전하게 `test` 브랜치로 PR을 보내는 전체 절차**입니다. 원본 저장소는
<https://github.com/lauranofirst1/test-dev>, 통합 대상 브랜치는 `test`입니다.

## 1. 도구와 버전

- Git
- Python 3.12 이상
- PostgreSQL 15 이상(현재 17로 검증)
- Node.js 20 이상(22 LTS 권장)

프런트엔드는 lockfile과 정확히 같은 버전을 설치하도록 `npm install`이 아니라
`npm ci`를 사용합니다. 진단 화면의 TourAPI 실호출을 제외하면 로컬 테스트에
공공데이터 API 키는 필요하지 않습니다.

## 2. 포크와 작업 브랜치

원본 저장소를 Fork한 뒤 자기 포크를 clone합니다.

```bash
git clone https://github.com/{내-GitHub-ID}/test-dev.git
cd test-dev
git remote add upstream https://github.com/lauranofirst1/test-dev.git
git fetch upstream
git switch -c feat/짧은-작업명 upstream/test
```

`origin`은 내 포크, `upstream`은 팀 원본이어야 합니다.

```bash
git remote -v
```

브랜치는 작업마다 새로 만듭니다.

- 기능: `feat/consumer-search`
- 버그: `fix/share-fallback`
- 문서: `docs/windows-setup`
- 정리: `chore/dependency-audit`

공용 `test` 브랜치에서 직접 작업하거나 force-push하지 않습니다. 이미 원본 저장소에
직접 쓰기 권한이 있어도 같은 방식으로 기능 브랜치를 만들면 됩니다.

## 3. 최초 로컬 설정

### Windows PowerShell

먼저 PostgreSQL에서 로컬 개발 계정과 DB를 만듭니다. 아래 계정은 로컬 PC 전용입니다.

```powershell
psql -U postgres -c "CREATE ROLE festaflow LOGIN PASSWORD 'festaflow' CREATEDB;"
psql -U postgres -c "CREATE DATABASE festaflow OWNER festaflow;"
psql -U postgres -d festaflow -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

Copy-Item .env.example .env

Set-Location apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head

Set-Location ..\web
npm ci
```

역할이나 DB가 이미 있다는 메시지가 나오면 기존 로컬 설정을 확인한 뒤 중복 생성
명령만 건너뜁니다. 앱 계정에는 `SUPERUSER`를 주지 않습니다. 테스트 DB 생성에
필요한 `CREATEDB`만 사용합니다.

### macOS · Linux

```bash
createuser -d festaflow
createdb -O festaflow festaflow
psql -d festaflow -c "ALTER USER festaflow WITH PASSWORD 'festaflow';"
psql -d festaflow -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

cp .env.example .env

cd apps/api
python3.12 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python -m alembic upgrade head

cd ../web
npm ci
```

`.env`는 절대 커밋하지 않습니다. 실제 KTO 키, SMTP 비밀번호, JWT 비밀도
`.env.example`이나 문서에 넣지 않습니다.

## 4. 실행과 테스트 데이터

Windows에서는 터미널 두 개를 엽니다.

```powershell
# 터미널 1 — API
Set-Location apps\api
.\.venv\Scripts\python.exe -m uvicorn festaflow.main:app --reload --port 8000
```

```powershell
# 터미널 2 — Web
Set-Location apps\web
npm run dev
```

macOS/Linux는 저장소 루트에서 `./dev.sh`로 둘을 함께 실행할 수 있습니다.

- Web: <http://localhost:5173>
- API 문서: <http://localhost:8000/docs>

API 포트를 바꾸면 두 프로세스에 같은 `API_PORT`를 전달합니다. Vite 프록시가 이
값을 읽습니다.

```powershell
$env:API_PORT = "8001"
# API 터미널: ... uvicorn ... --port 8001
# Web 터미널: npm run dev
```

화면을 채울 테스트 계정은 API 디렉터리에서 만듭니다.

```powershell
.\.venv\Scripts\python.exe scripts\seed_test_account.py
```

macOS/Linux에서는 `./.venv/bin/python scripts/seed_test_account.py`입니다. 로그인은
`test@test.com / 123456test!`이며 **로컬 개발 DB 전용**입니다. 스크립트는
`APP_ENV=local`과 localhost DB가 아니면 실행을 거부합니다. 실제 운영·공유 DB에는
절대 실행하지 않습니다.

제품 화면별 QA 절차는 [10-team-testing.md](10-team-testing.md), Consumer 실기기
게이트는 [11-consumer-pilot-readiness.md](11-consumer-pilot-readiness.md)를 봅니다.

## 5. 휴대폰 테스트

신뢰할 수 있는 같은 Wi-Fi에서만 프런트를 LAN에 엽니다. Windows는 `ipconfig`에서
현재 Wi-Fi의 사설 IPv4 주소(보통 `192.168.*.*`)를 확인합니다.

```powershell
Set-Location apps\web
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

휴대폰에서 `http://{PC의-사설-IP}:5173`으로 접속합니다. API는 Vite가 프록시하므로
휴대폰에 8000 포트를 직접 입력하지 않습니다. Windows 방화벽 질문이 나오면 공용
네트워크가 아니라 **개인 네트워크만** 허용하고, 테스트가 끝나면 서버를 종료합니다.

LAN HTTP에서는 브라우저 보안 정책 때문에 카메라, Web Share, Clipboard 일부가
제한될 수 있습니다. 390px 레이아웃과 복사 fallback은 LAN에서 확인할 수 있지만,
iPhone/Android 네이티브 공유 시트와 카메라 최종 판정은 HTTPS 배포 주소에서 합니다.

## 6. PR 전 필수 검증

PostgreSQL이 실행 중이고 `.env`가 로컬 DB를 가리키는지 먼저 확인합니다. 백엔드
테스트는 `festaflow_test` DB의 테이블을 재생성하므로 공유·운영 DB 계정을 쓰면 안
됩니다.

```powershell
# Backend
Set-Location apps\api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip_audit --local
.\.venv\Scripts\python.exe -m bandit -r src\festaflow -q
.\.venv\Scripts\python.exe -m pytest -q -ra

# Frontend
Set-Location ..\web
npm ci
npm audit --omit=dev
npm run typecheck
npm run test:share
npm run test:navigation
npm run build

# Repository root
Set-Location ..\..
git diff --check
git status --short
```

macOS/Linux에서는 `.\.venv\Scripts\python.exe`를 `./.venv/bin/python`으로 바꿉니다.
pytest가 PostgreSQL 연결 실패로 DB 테스트를 `SKIPPED`해도 명령 자체는 성공할 수
있습니다. 결과 요약에 skip이 있으면 통과로 기록하지 말고 DB를 고친 뒤 다시 돌립니다.

Python 전체 lint에는 기존 기술 부채가 남아 있어 현재 CI 필수 게이트로 두지
않았습니다. Python 파일을 고쳤다면 최소한 그 파일은 직접 검사합니다.

```powershell
Set-Location apps\api
.\.venv\Scripts\python.exe -m ruff check src\festaflow\고친파일.py tests\고친테스트.py
```

## 7. 안전하게 커밋하고 PR 올리기

먼저 최신 `upstream/test`를 반영합니다. 작업 중인 변경은 먼저 커밋해야 합니다.

```bash
git fetch upstream
git rebase upstream/test
```

파일은 이름을 명시해 stage합니다. 이 저장소에서는 로컬 감사 산출물이나 사용자
데이터가 함께 생길 수 있으므로 `git add .`와 `git add -A`를 사용하지 않습니다.

```bash
git add apps/web/src/lib/navigation.ts apps/web/tests/navigation.test.mjs
git diff --cached --check
git diff --cached
git status --short
git commit -m "fix: validate participant return navigation"
git push -u origin feat/짧은-작업명
```

GitHub에서 PR을 만들 때 다음 조합을 확인합니다.

- base repository: `lauranofirst1/test-dev`
- base branch: `test`
- head repository: 내 포크
- compare branch: 내 기능 브랜치

자동으로 채워지는 PR 템플릿에 변경 이유, 테스트 결과, 휴대폰 QA, migration과 환경
변수 변경, 알려진 제한을 적습니다. CI의 `Frontend`와 `Backend`가 모두 통과하고
리뷰 대화가 해결된 뒤 merge합니다. `main` PR은 별도 출시 합의가 있을 때만 만듭니다.

## 8. GitHub에 올리면 안 되는 것

- `.env`, API 키, JWT/SMTP/DB 비밀번호, 세션·참여자 secret
- 실제 학번·이메일·참여 기록·설문 자유응답
- `media/`, 업로드 이미지, DB dump, 서버 로그
- 개인 PC 절대 경로와 사용자명이 든 로컬 감사 문서
- 운영 화면 캡처의 개인정보

현재 로컬의 `docs/current-prototype-audit/`는 개인 Windows 절대 경로가 포함된
미추적 산출물이므로 이번 PR에 넣지 않습니다. 공개가 필요하면 별도 브랜치에서
경로와 개인정보를 지우고 내용 정확성을 다시 검토합니다.

실수로 secret을 커밋했다면 파일만 지우고 끝내지 않습니다. 즉시 팀장에게 비공개로
알리고 해당 키를 폐기·재발급한 뒤 Git history 정리 여부를 결정합니다.

## 9. 저장소 관리자가 GitHub에서 켤 설정

`test`와 `main` branch protection에 다음을 권장합니다.

- PR 없이 직접 push 금지
- `Frontend`, `Backend` status check 필수
- 최소 1명 승인, 새 commit 시 기존 승인 해제
- 모든 review conversation 해결 필수
- force-push와 branch 삭제 금지
- Dependabot alerts, secret scanning, private vulnerability reporting 활성화

저장소를 public으로 바꾸기 전에는 코드·이미지 권리를 확인하고 LICENSE를 팀 소유자가
선택해야 합니다. 현재 LICENSE가 없으므로 “공개 저장소에서 보인다”와 “외부 사용을
허가한다”는 같은 뜻이 아닙니다.
