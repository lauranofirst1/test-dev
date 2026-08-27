# 프론트엔드 + 웹 서버 한 장.
#
# vite 로 정적 파일을 만들고, 그것을 Caddy 가 서빙합니다. 개발 때는 vite 서버가
# `/api` 를 백엔드로 넘겨 주었는데(vite.config.ts), 배포에는 vite 서버가 없으므로
# 그 역할을 Caddy 가 이어받습니다.

# ── 1단계: 빌드 ──
FROM node:22-slim AS build
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# ── 2단계: 서빙 ──
#
# nginx 가 아니라 Caddy 를 씁니다. **인증서를 자동으로 받고 자동으로 갱신하기
# 때문입니다.** 부스 QR 스캔이 카메라(`getUserMedia`)를 쓰는데 브라우저는 HTTPS
# 가 아니면 카메라를 아예 열어 주지 않습니다. 즉 인증서는 이 서비스에서 선택이
# 아니라 기능의 전제이고, 그것을 손으로 관리하면 만료된 날 축제가 멈춥니다.
FROM caddy:2-alpine
COPY --from=build /web/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile
