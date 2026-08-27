# 백엔드 이미지 — FastAPI + Alembic.
#
# 슬림 이미지를 쓰고 빌드 도구를 넣지 않습니다. 의존성이 전부 휠로 배포되기
# 때문이고(psycopg[binary] · cryptography · bcrypt), 컴파일러를 넣는 순간
# 이미지가 몇 배로 불고 ARM 서버에서 빌드가 몇 분씩 걸립니다.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성을 먼저 넣습니다 — 소스만 바뀌었을 때 이 층을 다시 만들지 않습니다.
# 서버가 ARM 이라 이 층을 다시 만들면 몇 분씩 걸립니다.
#
# festaflow 는 `__init__.py` 가 없는 네임스페이스 패키지입니다. 의존성만 먼저
# 받으려면 setuptools 가 패키지를 하나는 찾아야 하므로, 빈 파일을 잠깐 놓았다가
# 지웁니다. 소스는 아래 `COPY . .` 가 실제 파일로 채웁니다.
COPY pyproject.toml ./
RUN mkdir -p src/festaflow \
    && : > src/festaflow/__init__.py \
    && pip install --upgrade pip \
    && pip install -e . \
    && rm src/festaflow/__init__.py

COPY . .

# 업로드 파일 자리. compose 가 여기에 볼륨을 붙입니다 —
# 붙이지 않으면 컨테이너를 다시 만들 때마다 조각 보드 그림이 사라집니다.
RUN mkdir -p /app/media
ENV MEDIA_DIR=/app/media

COPY docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
