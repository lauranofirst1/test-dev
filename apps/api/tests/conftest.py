"""DB 테스트 픽스처.

전용 테스트 DB(festaflow_test)에 마이그레이션을 한 번 적용하고,
테스트마다 트랜잭션을 롤백해 서로 간섭하지 않게 합니다.

Postgres 가 안 떠 있으면 DB 테스트는 skip 합니다 —
TourAPI 테스트는 DB 없이도 돌아야 하기 때문입니다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from festaflow.core.config import settings
from festaflow.models import Base

TEST_DB = "festaflow_test"


def _test_url() -> str:
    return make_url(settings.database_url).set(database=TEST_DB).render_as_string(
        hide_password=False
    )


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    admin_url = make_url(settings.database_url).set(database="postgres")
    try:
        admin = create_engine(
            admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT"
        )
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres 에 접속할 수 없어 DB 테스트를 건너뜁니다: {exc}")

    eng = create_engine(_test_url())
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    # 모델 metadata 로 직접 생성한다 — 마이그레이션과 모델이 어긋나면
    # 별도 테스트(test_migration_matches_models)에서 잡는다.
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    """테스트마다 롤백되는 세션."""
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        conn.close()


@pytest.fixture
def second_db(engine: Engine) -> Iterator[Session]:
    """동시성 테스트용 독립 커넥션. db 픽스처와 트랜잭션을 공유하지 않는다."""
    session = Session(bind=engine.connect(), expire_on_commit=False)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    """bcrypt 비용을 테스트에서만 낮춘다.

    운영 기본값 12 는 한 번에 약 180ms 다. 축제를 만드는 테스트마다 해시가
    한 번씩 돌아 스위트가 눈에 띄게 느려진다. 검증 로직은 라운드 수와 무관하다.
    """
    monkeypatch.setattr(settings, "bcrypt_rounds", 4, raising=False)


os.environ.setdefault("PYTHONUTF8", "1")
