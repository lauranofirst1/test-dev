# 배포 — 서버 한 대에 통째로 올리기

**목표는 두 가지입니다.** 심사위원이 10월 말까지 아무 때나 눌러도 열리는 주소를
갖는 것, 그리고 11월 축제에서 1000명이 붙어도 버티는 것.

`./dev.sh` 는 개발용입니다. 여기서 쓰는 것은 `docker compose` 입니다.

---

## 0. 무엇이 어떻게 놓이나

```
        인터넷
          │  443 (HTTPS)
     ┌────▼─────────────────────────────┐
     │  web   —  Caddy                  │
     │   · 화면(정적 파일) 서빙          │
     │   · 인증서 자동 발급·갱신          │
     │   · /api · /media → api 로 넘김   │
     └────┬─────────────────────────────┘
          │ (컨테이너끼리만)
     ┌────▼──────┐      ┌──────────────┐
     │  api      │─────▶│  db          │
     │  FastAPI  │      │  PostgreSQL 17│
     └───────────┘      └──────────────┘
          │                    │
      media 볼륨            pgdata 볼륨
   (올린 보드 그림)        (모든 데이터)
```

**포트는 80·443 두 개만 밖으로 열립니다.** DB 는 바깥에서 접속할 수 없습니다.

개발 때는 vite 개발 서버가 `/api` 를 백엔드로 넘겨 주었습니다. 배포에는 vite 서버가
없으므로 그 역할을 Caddy 가 이어받습니다.

---

## 1. 🚨 HTTPS 는 선택이 아닙니다

**부스 QR 스캔이 카메라를 씁니다**(`navigator.mediaDevices.getUserMedia`).
브라우저는 HTTPS 가 아닌 페이지에는 **카메라를 아예 열어 주지 않습니다.**

Caddy는 HSTS, clickjacking 차단, MIME sniffing 차단과 같은 출처 카메라만 허용하는
기본 보안 헤더도 응답에 붙입니다.

즉 `http://140.x.x.x` 같은 IP 주소로 띄우면 화면은 다 보이는데 스캔만 안 됩니다.
그리고 스캔은 이 서비스의 핵심 기능입니다.

인증서를 받으려면 **도메인**이 필요합니다. 그래서 nginx 대신 **Caddy** 를 씁니다 —
도메인만 알려주면 인증서를 알아서 받아 오고 알아서 갱신합니다. nginx 로도 되지만
발급과 갱신을 따로 붙여야 하고, 갱신을 놓친 날 축제가 멈춥니다.

---

## 2. 서버 — Oracle Cloud Always Free

무료 중 유일하게 **만료도 없고 초과 과금도 없습니다.** 유료로 올리지 않는 한
한도를 넘겨도 청구가 아니라 정지입니다.

| 항목 | Always Free 한도 |
|---|---|
| VM | Ampere A1 (ARM) 4 코어 · 24GB RAM |
| 디스크 | 200GB |
| 전송량 | 월 10TB |

축제 규모에는 과할 정도입니다.

1. <https://cloud.oracle.com> 가입 (카드 등록은 본인확인용, 청구되지 않습니다)
2. **Compute → Instances → Create Instance**
3. 이미지 **Ubuntu 24.04**, Shape **VM.Standard.A1.Flex** (4 OCPU / 24GB)
4. SSH 공개키를 넣고 생성. 공인 IP 를 적어 둡니다

> ⚠ ARM 서버는 인기가 많아 `Out of capacity` 가 자주 납니다. 다른 가용 도메인
> (AD-1/2/3)으로 바꿔 보고, 안 되면 몇 시간 뒤 다시 시도하세요. 며칠 걸릴 수도
> 있으니 **이 단계를 제일 먼저 시작하세요.**

### 학교 서버가 먼저입니다

한림대 SW중심대학사업단(`033-248-3341` · `hlsw@hallym.ac.kr`)에 **교내 서버를
빌려줄 수 있는지 먼저 물어보세요.** 11월 SW Week 주최 측이고 교내 행사용
시스템이라 명분이 확실합니다. 받으면 이 장의 2·3번을 건너뜁니다.

---

## 3. 도메인 — 무료로 하나

Let's Encrypt 는 IP 에는 인증서를 주지 않습니다. 도메인이 있어야 합니다.

<https://www.duckdns.org> 에서 깃허브 계정으로 로그인하고 이름 하나를 만듭니다.
`festaflow.duckdns.org` 처럼 됩니다. IP 칸에 서버 공인 IP 를 넣고 update 를 누릅니다.

```bash
# 내 PC 에서 — 도메인이 서버를 가리키는지 확인
dig +short festaflow.duckdns.org
```

서버 IP 가 나와야 다음으로 갑니다. 안 나오면 몇 분 기다리세요.

---

## 4. 방화벽 — 오라클은 **두 겹**입니다

여기서 제일 많이 막힙니다. 콘솔에서 열어도 서버 안에서 또 막혀 있습니다.

**① 콘솔 쪽** — Networking → Virtual Cloud Networks → 서브넷 → Security List →
**Add Ingress Rules**

| Source CIDR | 포트 |
|---|---|
| `0.0.0.0/0` | 80 |
| `0.0.0.0/0` | 443 |

**② 서버 안쪽** — 우분투 이미지에 iptables 규칙이 이미 들어 있습니다.

```bash
ssh ubuntu@festaflow.duckdns.org

sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

둘 다 해야 열립니다. 하나만 하면 "분명히 열었는데 접속이 안 된다" 가 됩니다.

---

## 5. 도커 설치

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER
exit          # 그룹 반영을 위해 한 번 나갔다 들어옵니다
```

---

## 6. 저장소와 환경변수

```bash
ssh ubuntu@festaflow.duckdns.org
git clone https://github.com/lauranofirst1/test-dev.git festaflow
cd festaflow
git checkout test

cp .env.example .env
nano .env
```

**반드시 채우는 네 개입니다.**

| 값 | 무엇을 넣나 |
|---|---|
| `SITE_ADDRESS` | `festaflow.duckdns.org` — **`http://` 를 붙이지 마세요.** 도메인만 |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` 결과. DATABASE_URL에 그대로 들어가므로 URL 예약문자가 없는 hex 사용 |
| `JWT_SECRET` | `openssl rand -hex 32` 결과. **개발 기본값이면 서버가 뜨지 않습니다** |
| `KTO_API_KEY` | 공공데이터포털 **Decoding 키** |

`PUBLIC_WEB_ORIGIN`, `CORS_ORIGINS`, `TRUSTED_HOSTS`,
`SESSION_COOKIE_SECURE=true`, `DEMO_MODE=false`는 compose가 `SITE_ADDRESS`에서
안전한 production 값으로 넣습니다. 화면과 API는 같은 공개 주소를 쓰며, 필수값이
빠지거나 HTTP 주소가 들어가면 API가 부팅을 거부합니다.

> `.env` 는 `.gitignore` 와 `.dockerignore` 양쪽에 있습니다. 커밋되지도,
> 이미지에 들어가지도 않습니다.

---

## 7. 띄우기

```bash
docker compose up -d --build
```

ARM 에서 첫 빌드는 5~10분쯤 걸립니다. 그 다음부터는 1분 안쪽입니다.

```bash
docker compose ps        # 셋 다 Up 이어야 합니다
docker compose logs -f   # Ctrl-C 로 빠져나옵니다
```

확인:

```bash
curl -s https://festaflow.duckdns.org/api/health
# {"status":"ok","env":"production", ...}
```

브라우저에서 <https://festaflow.duckdns.org> 를 열어 자물쇠가 보이면 끝입니다.

마이그레이션은 `api` 컨테이너가 뜰 때 **스스로 올립니다.** 실패하면 서버를
띄우지 않습니다 — 스키마가 낡은 채로 뜨면 화면은 멀쩡해 보이는데 특정 조회만
500 이 나고, 그게 축제 당일에 터지기 때문입니다.

---

## 8. 데모 데이터

빈 화면으로는 심사도 테스트도 안 됩니다.

```bash
docker compose exec api python scripts/seed_test_account.py
# → test@test.com / 123456test!
```

> ⚠ **심사 제출용 계정은 형식이 따로 정해져 있습니다** — `openapi / 2026openapi!`
> ([docs/08-contest-submission.md](08-contest-submission.md) §2.2). 지금 시드
> 스크립트는 `test@test.com` 을 고정으로 만듭니다. 제출 전에 심사용 계정을
> 만드는 방법이 필요합니다.

---

## 9. 코드를 고친 뒤 다시 올리기

```bash
cd ~/festaflow
git pull origin test
docker compose up -d --build
```

데이터는 볼륨에 있으므로 지워지지 않습니다. 받은 인증서도 그대로입니다.

## 10. 백업 — 축제 전날 반드시

```bash
docker compose exec -T db pg_dump -U festaflow festaflow | gzip > ~/festaflow-$(date +%F).sql.gz
```

되돌리기:

```bash
gunzip -c ~/festaflow-2026-11-02.sql.gz | docker compose exec -T db psql -U festaflow -d festaflow
```

올린 보드 그림까지 챙기려면:

```bash
docker run --rm -v festaflow_media:/m -v ~:/out alpine tar czf /out/media-$(date +%F).tar.gz -C /m .
```

---

## 11. 자주 막히는 곳

| 증상 | 원인과 해결 |
|---|---|
| 접속이 아예 안 된다 | 방화벽 **두 겹** 중 하나를 안 열었습니다 (4장) |
| 자물쇠가 안 뜨고 경고가 난다 | 도메인이 서버를 안 가리킵니다. `dig +short` 로 확인 |
| QR 스캔에서 카메라가 안 열린다 | HTTPS 가 아닙니다. `SITE_ADDRESS` 에 도메인이 들어갔는지 확인 |
| `api` 가 계속 재시작한다 | `docker compose logs api` — 대개 `JWT_SECRET`이 개발 기본값이거나 `SITE_ADDRESS`가 도메인 형식이 아닙니다 |
| 부스를 만들면 500 | `pgcrypto` 가 없습니다. `pgdata` 볼륨을 지우고 다시 올리면 초기화 스크립트가 돕니다 |
| 재배포했더니 보드 그림이 사라졌다 | `media` 볼륨이 안 붙었습니다. `docker compose ps` 와 compose 파일 확인 |
| 인증서를 자주 새로 받는다 | `caddy_data` 볼륨이 없으면 매번 재발급하다 Let's Encrypt 한도에 걸립니다 |
| 디스크가 찼다 | `docker system prune -a` — 안 쓰는 이미지가 쌓입니다 |

---

## 12. 축제 당일 전에 볼 것

- [ ] `pg_dump` 백업을 받아 두었나 (10장)
- [ ] `API_WORKERS` 가 서버 코어 수와 맞나
- [ ] 인증서 만료일이 축제 이후인가 — `curl -sI https://... | head -1` 로 접속만 확인해도 됩니다
- [ ] 관객 화면을 **휴대폰으로** 열어 QR 을 실제로 찍어 봤나
- [ ] 부스 담당 단말로 참여 코드를 **스캔**해 봤나 (아이폰이면 첫 스캔이 한 박자 늦습니다)
- [ ] 부스 담당자 접근 코드를 인쇄해 두었나
