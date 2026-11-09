
-- 환경공단 충전기 상세 자료는 핵심 스키마 적용 후 추가한다.
ALTER TABLE charging_station
    MODIFY station_key CHAR(64) NOT NULL COMMENT '출처별 운영묶음 해시 환경공단 출처코드 원본시설ID 운영기관',
    ADD source_station_id VARCHAR(40) NULL COMMENT '환경공단 statId 원본 충전소 번호';
ALTER TABLE charger
    ADD connector_code VARCHAR(8) NULL COMMENT '환경공단 커넥터 코드',
    ADD capacity_kw DECIMAL(8,2) NULL COMMENT '수록 출력 킬로와트 결측은 NULL',
    ADD charging_method VARCHAR(20) NULL COMMENT '동시 단독 충전 원문',
    ADD restriction_code CHAR(1) NULL COMMENT '이용제한 Y N 원문',
    ADD parking_free CHAR(1) NULL COMMENT '주차 무료 Y N 원문 요금 금액 아님',
    ADD floor_type VARCHAR(8) NULL COMMENT '환경공단 층 구분 원문',
    ADD floor_number VARCHAR(40) NULL COMMENT '층수 원문 숫자 외 표기 보존',
    ADD status_code VARCHAR(8) NULL COMMENT '수집 당시 상태 코드 빈자리 수 아님',
    ADD status_updated_at DATETIME NULL COMMENT '제공자 상태 갱신시각 한국 시각',
    ADD latitude DECIMAL(18,15) NULL COMMENT '환경공단 위도 원문 정밀도 보존',
    ADD longitude DECIMAL(18,15) NULL COMMENT '환경공단 경도 원문 정밀도 보존',
    ADD CONSTRAINT ck_charger_capacity CHECK (capacity_kw IS NULL OR capacity_kw >= 0),
    ADD CONSTRAINT ck_charger_latitude CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
    ADD CONSTRAINT ck_charger_longitude CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180);
