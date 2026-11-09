CREATE DATABASE IF NOT EXISTS chachacha CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE chachacha;

-- 핵심 스키마는 12개 표로 구성한다.
-- CHECK 제약은 MySQL 8.0.16 이상에서 적용된다.
-- 신규 생성용이며 기존 표를 변경하는 마이그레이션은 포함하지 않는다.
-- 기본 문자셋 변경은 기존 컬럼의 문자셋을 변환하지 않는다.
ALTER DATABASE chachacha CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
SET default_storage_engine = 'InnoDB';

-- ERDCloud에는 BEGIN~END ERDCLOUD 구간만 가져온다.
-- BEGIN ERDCLOUD

CREATE TABLE source_snapshot (
    snapshot_id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '수집본 번호',
    source_code VARCHAR(40) NOT NULL COMMENT '출처 구분 코드',
    source_url VARCHAR(2048) NOT NULL COMMENT '공개 원문 주소',
    artifact_path VARCHAR(512) NOT NULL COMMENT '원본 상대 경로',
    content_sha256 CHAR(64) NOT NULL COMMENT '원본 묶음 해시',
    reference_start DATE NULL COMMENT '자료 시작일',
    reference_end DATE NULL COMMENT '자료 종료일',
    page_updated_on DATE NULL COMMENT '제공 페이지 갱신일',
    collected_on DATE NOT NULL COMMENT '한국 시각 기준 수집일',
    collected_at DATETIME NULL COMMENT '한국 시각 기준 정확한 수집시각',
    collection_method VARCHAR(8) NOT NULL COMMENT '수집 방식 file api crawl',
    is_complete TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '검수 완료 여부',
    coverage_note VARCHAR(1000) NOT NULL COMMENT '수록 범위와 결측 주의',
    PRIMARY KEY (snapshot_id),
    CONSTRAINT uq_source_snapshot_1 UNIQUE (source_code, content_sha256)
) COMMENT='출처 수집본';

CREATE TABLE region (
    region_id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '서울 자치구 내부 번호',
    province_name VARCHAR(20) NOT NULL COMMENT '시도명',
    district_name VARCHAR(20) NOT NULL COMMENT '자치구명',
    resident_code CHAR(10) NOT NULL COMMENT '주민등록 지역 코드',
    PRIMARY KEY (region_id),
    CONSTRAINT uq_region_1 UNIQUE (province_name, district_name),
    CONSTRAINT uq_region_2 UNIQUE (resident_code)
) COMMENT='서울 자치구';

CREATE TABLE vehicle_type (
    vehicle_type_code VARCHAR(12) NOT NULL COMMENT '차종 코드',
    vehicle_type_name VARCHAR(10) NOT NULL COMMENT '차종명',
    PRIMARY KEY (vehicle_type_code),
    CONSTRAINT uq_vehicle_type_1 UNIQUE (vehicle_type_name)
) COMMENT='차종';

CREATE TABLE fuel_scope (
    fuel_scope_code VARCHAR(12) NOT NULL COMMENT '연료 범위 코드',
    fuel_scope_name VARCHAR(10) NOT NULL COMMENT '연료 범위명',
    PRIMARY KEY (fuel_scope_code),
    CONSTRAINT uq_fuel_scope_1 UNIQUE (fuel_scope_name)
) COMMENT='등록 연료 범위';

CREATE TABLE company (
    company_id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '기업 내부 번호',
    company_name VARCHAR(80) NOT NULL COMMENT '기업명',
    website_url VARCHAR(2048) NOT NULL COMMENT '공식 홈페이지',
    PRIMARY KEY (company_id),
    CONSTRAINT uq_company_1 UNIQUE (company_name)
) COMMENT='기업 FAQ 제공 브랜드';

CREATE TABLE registration (
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    stat_month DATE NOT NULL COMMENT '등록 기준월 첫날',
    vehicle_type_code VARCHAR(12) NOT NULL COMMENT '차종 코드',
    fuel_scope_code VARCHAR(12) NOT NULL COMMENT '연료 범위 코드',
    vehicle_count BIGINT UNSIGNED NOT NULL COMMENT '등록 대수',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    PRIMARY KEY (region_id, stat_month, vehicle_type_code, fuel_scope_code),
    CONSTRAINT fk_registration_1 FOREIGN KEY (region_id) REFERENCES region (region_id),
    CONSTRAINT fk_registration_2 FOREIGN KEY (vehicle_type_code) REFERENCES vehicle_type (vehicle_type_code),
    CONSTRAINT fk_registration_3 FOREIGN KEY (fuel_scope_code) REFERENCES fuel_scope (fuel_scope_code),
    CONSTRAINT fk_registration_4 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='구별 월별 자동차 등록';

CREATE TABLE province_registration (
    province_name VARCHAR(40) NOT NULL COMMENT '원본 시도 표기',
    stat_month DATE NOT NULL COMMENT '등록 기준월 첫날',
    vehicle_type_code VARCHAR(12) NOT NULL COMMENT '차종 코드',
    usage_code VARCHAR(12) NOT NULL COMMENT '용도 코드 official private commercial',
    vehicle_count BIGINT UNSIGNED NOT NULL COMMENT '등록 대수',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    PRIMARY KEY (province_name, stat_month, vehicle_type_code, usage_code),
    CONSTRAINT fk_province_registration_1 FOREIGN KEY (vehicle_type_code) REFERENCES vehicle_type (vehicle_type_code),
    CONSTRAINT fk_province_registration_2 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='전국 시도별 월별 자동차 등록';

CREATE TABLE region_context (
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    stat_month DATE NOT NULL COMMENT '비교 기준월 첫날',
    population BIGINT UNSIGNED NOT NULL COMMENT '주민등록 인구',
    household_count BIGINT UNSIGNED NOT NULL COMMENT '주민등록 세대',
    resident_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    stop_snapshot_id INT UNSIGNED NULL COMMENT '채택 정류장 수집본 번호',
    listed_bus_id_count BIGINT UNSIGNED NULL COMMENT '수록 업체별 버스 정류장 ID 수',
    listed_rail_id_count BIGINT UNSIGNED NULL COMMENT '수록 업체별 철도 정류장 ID 수',
    PRIMARY KEY (region_id, stat_month),
    CONSTRAINT fk_region_context_1 FOREIGN KEY (region_id) REFERENCES region (region_id),
    CONSTRAINT fk_region_context_2 FOREIGN KEY (resident_snapshot_id) REFERENCES source_snapshot (snapshot_id),
    CONSTRAINT fk_region_context_3 FOREIGN KEY (stop_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='구별 인구 세대와 정류장 참고값';

CREATE TABLE parking_site (
    parking_row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '주차 관측행 내부 번호',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    source_row_no INT UNSIGNED NOT NULL COMMENT '두 원본 파일의 전역 연속 행 번호',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    institution_code VARCHAR(32) NOT NULL COMMENT '제공기관 코드',
    source_parking_no VARCHAR(80) NOT NULL COMMENT '원본 주차장관리번호',
    parking_operation VARCHAR(20) NULL COMMENT 'PRKPLCE_SE 공영 민영 구분',
    parking_type VARCHAR(20) NULL COMMENT 'PRKPLCE_TYPE 노상 노외 부설 구분',
    address VARCHAR(500) NOT NULL COMMENT '도로명 우선 주차장 주소',
    space_count INT UNSIGNED NULL COMMENT '원본 주차면 수',
    latitude DECIMAL(10,7) NULL COMMENT '검수한 위도',
    longitude DECIMAL(10,7) NULL COMMENT '검수한 경도',
    reference_date DATE NULL COMMENT '행별 자료 기준일',
    identifier_status VARCHAR(12) NOT NULL COMMENT '식별번호 unique conflict 검수 상태',
    coordinate_valid TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '좌표 범위 검사 통과 여부',
    PRIMARY KEY (parking_row_id),
    CONSTRAINT uq_parking_site_1 UNIQUE (source_snapshot_id, source_row_no),
    CONSTRAINT fk_parking_site_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id),
    CONSTRAINT fk_parking_site_2 FOREIGN KEY (region_id) REFERENCES region (region_id)
) COMMENT='표준 주차장 관측 상세';

CREATE TABLE charging_station (
    station_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '충전소 내부 번호',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    station_key CHAR(64) NOT NULL COMMENT '운영기관 충전소명 주소 조합 해시',
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    operator_name VARCHAR(100) NOT NULL COMMENT 'OPER_INST 운영기관명',
    station_name VARCHAR(200) NOT NULL COMMENT 'CHARG_STTN 충전소명',
    address VARCHAR(500) NOT NULL COMMENT 'ADDR 충전소 주소',
    PRIMARY KEY (station_id),
    CONSTRAINT uq_charging_station_1 UNIQUE (source_snapshot_id, station_key),
    CONSTRAINT fk_charging_station_1 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id),
    CONSTRAINT fk_charging_station_2 FOREIGN KEY (region_id) REFERENCES region (region_id)
) COMMENT='수집본 안의 충전소 운영묶음';

CREATE TABLE charger (
    station_id BIGINT UNSIGNED NOT NULL COMMENT '충전소 내부 번호',
    source_charger_id VARCHAR(40) NOT NULL COMMENT 'CHARG_ID 원본 기기 번호',
    source_row_no INT UNSIGNED NOT NULL COMMENT '원본 충전목록 행 순서',
    speed_code VARCHAR(8) NOT NULL COMMENT '급속 완속 미상 코드',
    connector_text VARCHAR(120) NULL COMMENT 'CHARG_TYPE 커넥터 원문',
    capacity_text VARCHAR(120) NULL COMMENT 'CHARG_CPCT 용량 원문',
    operating_time_text VARCHAR(200) NULL COMMENT 'USE_PSBLTY_TM 이용 가능 시간 원문',
    restriction_note VARCHAR(500) NULL COMMENT 'USER_LMT 제한 안내 개인정보 제거',
    source_x DECIMAL(15,4) NULL COMMENT '좌표계 미확인 원좌표 X',
    source_y DECIMAL(15,4) NULL COMMENT '좌표계 미확인 원좌표 Y',
    PRIMARY KEY (station_id, source_charger_id),
    CONSTRAINT fk_charger_1 FOREIGN KEY (station_id) REFERENCES charging_station (station_id)
) COMMENT='수록 충전기 항목';

CREATE TABLE faq (
    company_id SMALLINT UNSIGNED NOT NULL COMMENT '기업 내부 번호',
    faq_key CHAR(64) NOT NULL COMMENT '페이지 범주 질문 해시',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '출처 수집본 번호',
    category VARCHAR(100) NOT NULL COMMENT '질문 범주',
    question TEXT NOT NULL COMMENT '질문',
    answer_text MEDIUMTEXT NOT NULL COMMENT '정제 답변',
    source_url VARCHAR(2048) NOT NULL COMMENT '질문 원문 페이지',
    PRIMARY KEY (company_id, faq_key),
    CONSTRAINT fk_faq_1 FOREIGN KEY (company_id) REFERENCES company (company_id),
    CONSTRAINT fk_faq_2 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='기업 질문과 답변';

-- END ERDCLOUD

-- BEGIN MYSQL_RUNTIME
-- CHECK 제약은 MySQL에서 적용하며 ERDCloud 가져오기에서는 제외한다.
ALTER TABLE source_snapshot ADD CONSTRAINT ck_source_snapshot_1 CHECK (is_complete IN (0,1));
ALTER TABLE source_snapshot ADD CONSTRAINT ck_source_snapshot_2 CHECK (collection_method IN ('file','api','crawl'));
ALTER TABLE source_snapshot ADD CONSTRAINT ck_source_snapshot_3 CHECK ((reference_start IS NULL AND reference_end IS NULL) OR (reference_start IS NOT NULL AND reference_end IS NOT NULL AND reference_start <= reference_end));
ALTER TABLE source_snapshot ADD CONSTRAINT ck_source_snapshot_4 CHECK (collected_at IS NULL OR DATE(collected_at) = collected_on);
ALTER TABLE region ADD CONSTRAINT ck_region_1 CHECK (province_name = '서울특별시');
ALTER TABLE region ADD CONSTRAINT ck_region_2 CHECK (resident_code REGEXP '^11[0-9]{3}00000$');
ALTER TABLE region ADD CONSTRAINT ck_region_3 CHECK (district_name IN ('종로구','중구','용산구','성동구','광진구','동대문구','중랑구','성북구','강북구','도봉구','노원구','은평구','서대문구','마포구','양천구','강서구','구로구','금천구','영등포구','동작구','관악구','서초구','강남구','송파구','강동구'));
ALTER TABLE vehicle_type ADD CONSTRAINT ck_vehicle_type_1 CHECK (vehicle_type_code IN ('passenger','bus','truck','special'));
ALTER TABLE fuel_scope ADD CONSTRAINT ck_fuel_scope_1 CHECK (fuel_scope_code IN ('all','electric'));
ALTER TABLE registration ADD CONSTRAINT ck_registration_1 CHECK (DAYOFMONTH(stat_month) = 1);
ALTER TABLE province_registration ADD CONSTRAINT ck_province_registration_1 CHECK (DAYOFMONTH(stat_month) = 1);
ALTER TABLE province_registration ADD CONSTRAINT ck_province_registration_2 CHECK (usage_code IN ('official','private','commercial'));
ALTER TABLE province_registration ADD CONSTRAINT ck_province_registration_3 CHECK (CHAR_LENGTH(TRIM(province_name)) > 0);
ALTER TABLE region_context ADD CONSTRAINT ck_region_context_1 CHECK (DAYOFMONTH(stat_month) = 1);
ALTER TABLE region_context ADD CONSTRAINT ck_region_context_2 CHECK ((stop_snapshot_id IS NULL AND listed_bus_id_count IS NULL AND listed_rail_id_count IS NULL) OR (stop_snapshot_id IS NOT NULL AND listed_bus_id_count IS NOT NULL AND listed_rail_id_count IS NOT NULL));
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_1 CHECK (source_row_no > 0);
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_2 CHECK (identifier_status IN ('unique','conflict'));
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_3 CHECK (coordinate_valid IN (0,1));
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_4 CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90);
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_5 CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180);
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_6 CHECK (coordinate_valid = 0 OR (latitude IS NOT NULL AND longitude IS NOT NULL));
ALTER TABLE parking_site ADD CONSTRAINT ck_parking_site_7 CHECK (CHAR_LENGTH(TRIM(address)) > 0);
ALTER TABLE charging_station ADD CONSTRAINT ck_charging_station_1 CHECK (CHAR_LENGTH(TRIM(station_name)) > 0);
ALTER TABLE charging_station ADD CONSTRAINT ck_charging_station_2 CHECK (CHAR_LENGTH(TRIM(address)) > 0);
ALTER TABLE charger ADD CONSTRAINT ck_charger_1 CHECK (source_row_no > 0);
ALTER TABLE charger ADD CONSTRAINT ck_charger_2 CHECK (speed_code IN ('fast','slow','unknown'));
ALTER TABLE charger ADD CONSTRAINT ck_charger_3 CHECK (CHAR_LENGTH(TRIM(source_charger_id)) > 0);
ALTER TABLE charger ADD CONSTRAINT ck_charger_4 CHECK (restriction_note IS NULL OR CHAR_LENGTH(TRIM(restriction_note)) > 0);
ALTER TABLE faq ADD CONSTRAINT ck_faq_1 CHECK (CHAR_LENGTH(TRIM(question)) > 0);
ALTER TABLE faq ADD CONSTRAINT ck_faq_2 CHECK (CHAR_LENGTH(TRIM(answer_text)) > 0);
-- END MYSQL_RUNTIME

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

-- 지도 표시 전용 경계 표.
-- BEGIN ERDCLOUD
CREATE TABLE region_boundary (
    region_id SMALLINT UNSIGNED NOT NULL COMMENT '서울 자치구 내부 번호',
    source_snapshot_id INT UNSIGNED NOT NULL COMMENT '경계 출처 수집본 번호',
    boundary_year SMALLINT UNSIGNED NOT NULL COMMENT '경계 기준 연도',
    geometry_json JSON NOT NULL COMMENT 'GeoJSON 도형 경도 위도 좌표',
    centroid_latitude DECIMAL(10,7) NOT NULL COMMENT '면적 중심 위도 지도 표시용',
    centroid_longitude DECIMAL(10,7) NOT NULL COMMENT '면적 중심 경도 지도 표시용',
    min_latitude DECIMAL(10,7) NOT NULL COMMENT '경계 최소 위도',
    max_latitude DECIMAL(10,7) NOT NULL COMMENT '경계 최대 위도',
    min_longitude DECIMAL(10,7) NOT NULL COMMENT '경계 최소 경도',
    max_longitude DECIMAL(10,7) NOT NULL COMMENT '경계 최대 경도',
    ring_count INT UNSIGNED NOT NULL COMMENT '외곽선과 내부 구멍의 총 고리 수',
    PRIMARY KEY (region_id),
    CONSTRAINT fk_region_boundary_1 FOREIGN KEY (region_id) REFERENCES region (region_id),
    CONSTRAINT fk_region_boundary_2 FOREIGN KEY (source_snapshot_id) REFERENCES source_snapshot (snapshot_id)
) COMMENT='서울 자치구 지도 경계';
-- END ERDCLOUD

ALTER TABLE region_boundary ADD CONSTRAINT ck_region_boundary_1 CHECK (boundary_year=2013 AND ring_count>0);
ALTER TABLE region_boundary ADD CONSTRAINT ck_region_boundary_2 CHECK (min_latitude>=37.4 AND min_latitude<=max_latitude AND max_latitude<=37.75 AND min_longitude>=126.75 AND min_longitude<=max_longitude AND max_longitude<=127.2);
ALTER TABLE region_boundary ADD CONSTRAINT ck_region_boundary_3 CHECK (centroid_latitude BETWEEN min_latitude AND max_latitude AND centroid_longitude BETWEEN min_longitude AND max_longitude);
ALTER TABLE region_boundary ADD CONSTRAINT ck_region_boundary_4 CHECK (JSON_TYPE(geometry_json)='OBJECT' AND JSON_CONTAINS_PATH(geometry_json, 'all', '$.type', '$.coordinates')=1 AND JSON_UNQUOTE(JSON_EXTRACT(geometry_json, '$.type')) IN ('Polygon','MultiPolygon') AND JSON_TYPE(JSON_EXTRACT(geometry_json, '$.coordinates'))='ARRAY');
