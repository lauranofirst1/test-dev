-- booths.qr_secret 의 기본값이 gen_random_bytes() 라 이 확장이 없으면
-- 부스를 만들 수 없습니다. 빈 데이터 디렉터리에 처음 뜰 때 한 번 실행됩니다.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
