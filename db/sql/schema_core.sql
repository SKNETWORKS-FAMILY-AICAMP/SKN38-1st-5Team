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
