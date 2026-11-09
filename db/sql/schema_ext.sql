CREATE DATABASE IF NOT EXISTS chachacha CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE chachacha;

-- 핵심 스키마 적용 후 시간자료 5개 표와 충전 상세 12개 열을 추가한다.
-- 핵심 스키마와 합쳐 17개 표, CHECK 제약 43개로 구성한다.
-- CHECK 제약은 MySQL 8.0.16 이상에서 적용된다.
-- 신규 생성용이며 기존 표를 변경하는 마이그레이션은 포함하지 않는다.
-- 기본 문자셋 변경은 기존 컬럼의 문자셋을 변환하지 않는다.
ALTER DATABASE chachacha CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET default_storage_engine = 'InnoDB';

-- ERDCloud에는 BEGIN~END ERDCLOUD 구간만 가져온다.
-- BEGIN ERDCLOUD

CREATE TABLE traffic_coverage (
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    expected_point_direction_count BIGINT UNSIGNED NOT NULL COMMENT '서울 주소로 연결된 지점 방향 수',
    PRIMARY KEY (source_snapshot_id, region_id),
    CONSTRAINT fk_traffic_coverage_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id),
    CONSTRAINT fk_traffic_coverage_2 FOREIGN KEY (region_id) REFERENCES region (region_id)
) COMMENT='구별 교통 관측 범위';

CREATE TABLE traffic_snapshot (
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    observed_at DATETIME NOT NULL COMMENT '한국 시각 관측시간 시작',
    valid_point_direction_count BIGINT UNSIGNED NOT NULL COMMENT '값이 확인된 지점 방향 수',
    known_vehicle_sum BIGINT UNSIGNED NULL COMMENT '확인된 통행량 부분합',
    PRIMARY KEY (source_snapshot_id, region_id, observed_at),
    CONSTRAINT fk_traffic_snapshot_1 FOREIGN KEY (source_snapshot_id, region_id) REFERENCES traffic_coverage (source_snapshot_id, region_id)
) COMMENT='구별 시간 교통량 표본';

CREATE TABLE transit_coverage (
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    stat_date DATE NOT NULL COMMENT '승객자료 기준일',
    analysis_type VARCHAR(10) NOT NULL COMMENT '원본 분석유형 코드',
    expected_dong_count BIGINT UNSIGNED NOT NULL COMMENT '해당 구 날짜 유형의 원본 행정동 수',
    PRIMARY KEY (source_snapshot_id, region_id, stat_date, analysis_type),
    CONSTRAINT fk_transit_coverage_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id),
    CONSTRAINT fk_transit_coverage_2 FOREIGN KEY (region_id) REFERENCES region (region_id)
) COMMENT='구별 날짜별 승객자료 범위';

CREATE TABLE transit_ridership_snapshot (
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    stat_date DATE NOT NULL COMMENT '승객자료 기준일',
    analysis_type VARCHAR(10) NOT NULL COMMENT '원본 분석유형 코드',
    hour_of_day TINYINT UNSIGNED NOT NULL COMMENT '시간대 시작 시',
    mode_code VARCHAR(10) NOT NULL COMMENT '수단 범위 total bus subway',
    valid_dong_count BIGINT UNSIGNED NOT NULL COMMENT '값이 확인된 행정동 수',
    known_passenger_sum BIGINT UNSIGNED NULL COMMENT '확인된 제공 승객수 부분합',
    PRIMARY KEY (source_snapshot_id, region_id, stat_date, analysis_type, hour_of_day, mode_code),
    CONSTRAINT fk_transit_ridership_snapshot_1 FOREIGN KEY (source_snapshot_id, region_id, stat_date, analysis_type) REFERENCES transit_coverage (source_snapshot_id, region_id, stat_date, analysis_type)
) COMMENT='구별 시간 수단 승객수 표본';

CREATE TABLE weather_snapshot (
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    observed_at DATETIME NOT NULL COMMENT 'tm 한국 시각 관측시간 서울108',
    temperature_c DECIMAL(5,2) NULL COMMENT 'ta 기온 섭씨',
    rain_mm DECIMAL(8,2) NULL COMMENT 'rn 강수량 밀리미터',
    snow_cm DECIMAL(8,2) NULL COMMENT 'dsnw 적설 센티미터',
    wind_speed_ms DECIMAL(8,2) NULL COMMENT 'ws 풍속 초당 미터',
    temperature_qc_flag CHAR(1) NULL COMMENT 'taQcflag 원본 품질 플래그',
    rain_qc_flag CHAR(1) NULL COMMENT 'rnQcflag 원본 품질 플래그',
    wind_qc_flag CHAR(1) NULL COMMENT 'wsQcflag 원본 품질 플래그',
    PRIMARY KEY (source_snapshot_id, observed_at),
    CONSTRAINT fk_weather_snapshot_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='확장 서울 ASOS 시간 관측';

-- END ERDCLOUD

-- BEGIN MYSQL_RUNTIME
-- CHECK 제약은 MySQL에서 적용하며 ERDCloud 가져오기에서는 제외한다.
ALTER TABLE traffic_snapshot ADD CONSTRAINT ck_traffic_snapshot_1 CHECK (MINUTE(observed_at) = 0 AND SECOND(observed_at) = 0);
ALTER TABLE traffic_snapshot ADD CONSTRAINT ck_traffic_snapshot_2 CHECK ((valid_point_direction_count = 0 AND known_vehicle_sum IS NULL) OR (valid_point_direction_count > 0 AND known_vehicle_sum IS NOT NULL));
ALTER TABLE transit_coverage ADD CONSTRAINT ck_transit_coverage_1 CHECK (expected_dong_count > 0);
ALTER TABLE transit_ridership_snapshot ADD CONSTRAINT ck_transit_ridership_snapshot_1 CHECK (mode_code IN ('total','bus','subway'));
ALTER TABLE transit_ridership_snapshot ADD CONSTRAINT ck_transit_ridership_snapshot_2 CHECK (hour_of_day BETWEEN 0 AND 23);
ALTER TABLE transit_ridership_snapshot ADD CONSTRAINT ck_transit_ridership_snapshot_3 CHECK ((valid_dong_count = 0 AND known_passenger_sum IS NULL) OR (valid_dong_count > 0 AND known_passenger_sum IS NOT NULL));
ALTER TABLE weather_snapshot ADD CONSTRAINT ck_weather_snapshot_1 CHECK (MINUTE(observed_at) = 0 AND SECOND(observed_at) = 0);
ALTER TABLE weather_snapshot ADD CONSTRAINT ck_weather_snapshot_2 CHECK (rain_mm IS NULL OR rain_mm >= 0);
ALTER TABLE weather_snapshot ADD CONSTRAINT ck_weather_snapshot_3 CHECK (snow_cm IS NULL OR snow_cm >= 0);
ALTER TABLE weather_snapshot ADD CONSTRAINT ck_weather_snapshot_4 CHECK (wind_speed_ms IS NULL OR wind_speed_ms >= 0);
-- END MYSQL_RUNTIME

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

/*
주차 요금·운영·감면 3개 표는 데이터 범위 확정과 정제 전까지 적용하지 않는다.

CREATE TABLE parking_profile (
    profile_id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '요금 운영 조건 번호',
    profile_key CHAR(64) NOT NULL COMMENT '정규화한 조건 묶음 해시',
    parking_kind_name VARCHAR(40) NULL COMMENT '주차장 유형',
    operation_name VARCHAR(80) NULL COMMENT '운영 구분',
    charge_code CHAR(1) NULL COMMENT '평일 유료 여부 원본 코드',
    base_fee DECIMAL(12,2) NULL COMMENT '기본 요금 원값',
    base_minute DECIMAL(8,2) NULL COMMENT '기본 요금 적용 분',
    additional_fee DECIMAL(12,2) NULL COMMENT '추가 요금 원값',
    additional_minute DECIMAL(8,2) NULL COMMENT '추가 요금 적용 분',
    monthly_fee DECIMAL(12,2) NULL COMMENT '월 정기권 요금 원값',
    daily_max_fee DECIMAL(12,2) NULL COMMENT '일 최대 요금 원값',
    weekday_start CHAR(4) NULL COMMENT '평일 시작시각 HHMM',
    weekday_end CHAR(4) NULL COMMENT '평일 종료시각 HHMM',
    weekend_start CHAR(4) NULL COMMENT '주말 시작시각 HHMM',
    weekend_end CHAR(4) NULL COMMENT '주말 종료시각 HHMM',
    holiday_start CHAR(4) NULL COMMENT '공휴일 시작시각 HHMM',
    holiday_end CHAR(4) NULL COMMENT '공휴일 종료시각 HHMM',
    saturday_charge_code CHAR(1) NULL COMMENT '토요일 유료 여부 원본 코드',
    holiday_charge_code CHAR(1) NULL COMMENT '공휴일 유료 여부 원본 코드',
    PRIMARY KEY (profile_id),
    CONSTRAINT uq_parking_profile_1 UNIQUE (profile_key)
) COMMENT='주차 요금과 운영 조건';

CREATE TABLE public_parking_site (
    public_parking_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '서울 공영주차 관측행 번호',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    source_row_no INT UNSIGNED NOT NULL COMMENT '원본 응답 행 순서',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    profile_id INT UNSIGNED NOT NULL COMMENT '요금 운영 조건 번호',
    parking_code VARCHAR(40) NOT NULL COMMENT 'PKLT_CD 원본 코드 반복 허용',
    parking_name VARCHAR(200) NOT NULL COMMENT 'PKLT_NM 주차장명',
    address VARCHAR(500) NOT NULL COMMENT 'ADDR 주차 주소',
    reported_capacity DECIMAL(12,2) NULL COMMENT 'TPKCT 관측행 주차면 표기값',
    source_synced_at DATETIME NULL COMMENT 'LAST_DATA_SYNC_TM 원본 동기화 시각',
    latitude DECIMAL(10,7) NULL COMMENT 'LAT 검수한 위도',
    longitude DECIMAL(10,7) NULL COMMENT 'LOT 검수한 경도',
    coordinate_valid TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '좌표 검수 통과 여부',
    PRIMARY KEY (public_parking_row_id),
    CONSTRAINT uq_public_parking_site_1 UNIQUE (source_snapshot_id, source_row_no),
    CONSTRAINT fk_public_parking_site_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id),
    CONSTRAINT fk_public_parking_site_2 FOREIGN KEY (region_id) REFERENCES region (region_id),
    CONSTRAINT fk_public_parking_site_3 FOREIGN KEY (profile_id) REFERENCES parking_profile (profile_id)
) COMMENT='서울 공영주차 API 구획 상세';

CREATE TABLE parking_guidance (
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    source_row_no INT UNSIGNED NOT NULL COMMENT '안내표 본문 행 번호',
    target_text TEXT NOT NULL COMMENT '감면 대상 원문',
    benefit_text TEXT NOT NULL COMMENT '급지별 혜택과 조건 원문',
    PRIMARY KEY (source_snapshot_id, source_row_no),
    CONSTRAINT fk_parking_guidance_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='운영기관 주차 감면 안내';

ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_1 CHECK (charge_code IS NULL OR charge_code IN ('Y','N'));
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_2 CHECK (saturday_charge_code IS NULL OR saturday_charge_code IN ('Y','N'));
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_3 CHECK (holiday_charge_code IS NULL OR holiday_charge_code IN ('Y','N'));
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_4 CHECK (base_fee IS NULL OR base_fee >= 0);
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_5 CHECK (base_minute IS NULL OR base_minute >= 0);
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_6 CHECK (additional_fee IS NULL OR additional_fee >= 0);
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_7 CHECK (additional_minute IS NULL OR additional_minute >= 0);
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_8 CHECK (monthly_fee IS NULL OR monthly_fee >= 0);
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_9 CHECK (daily_max_fee IS NULL OR daily_max_fee >= 0);
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_10 CHECK (weekday_start IS NULL OR weekday_start REGEXP '^([01][0-9]|2[0-3])[0-5][0-9]$|^2400$');
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_11 CHECK (weekday_end IS NULL OR weekday_end REGEXP '^([01][0-9]|2[0-3])[0-5][0-9]$|^2400$');
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_12 CHECK (weekend_start IS NULL OR weekend_start REGEXP '^([01][0-9]|2[0-3])[0-5][0-9]$|^2400$');
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_13 CHECK (weekend_end IS NULL OR weekend_end REGEXP '^([01][0-9]|2[0-3])[0-5][0-9]$|^2400$');
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_14 CHECK (holiday_start IS NULL OR holiday_start REGEXP '^([01][0-9]|2[0-3])[0-5][0-9]$|^2400$');
ALTER TABLE parking_profile ADD CONSTRAINT ck_parking_profile_15 CHECK (holiday_end IS NULL OR holiday_end REGEXP '^([01][0-9]|2[0-3])[0-5][0-9]$|^2400$');
ALTER TABLE public_parking_site ADD CONSTRAINT ck_public_parking_site_1 CHECK (source_row_no > 0);
ALTER TABLE public_parking_site ADD CONSTRAINT ck_public_parking_site_2 CHECK (reported_capacity IS NULL OR reported_capacity >= 0);
ALTER TABLE public_parking_site ADD CONSTRAINT ck_public_parking_site_3 CHECK (coordinate_valid IN (0,1));
ALTER TABLE public_parking_site ADD CONSTRAINT ck_public_parking_site_4 CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90);
ALTER TABLE public_parking_site ADD CONSTRAINT ck_public_parking_site_5 CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180);
ALTER TABLE public_parking_site ADD CONSTRAINT ck_public_parking_site_6 CHECK (coordinate_valid = 0 OR (latitude IS NOT NULL AND longitude IS NOT NULL));
ALTER TABLE parking_guidance ADD CONSTRAINT ck_parking_guidance_1 CHECK (source_row_no > 0);
ALTER TABLE parking_guidance ADD CONSTRAINT ck_parking_guidance_2 CHECK (CHAR_LENGTH(TRIM(target_text)) > 0);
ALTER TABLE parking_guidance ADD CONSTRAINT ck_parking_guidance_3 CHECK (CHAR_LENGTH(TRIM(benefit_text)) > 0);
*/
