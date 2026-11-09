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
