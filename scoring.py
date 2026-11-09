# 가중치와 판정 기준은 팀의 추정 규칙이다.

import numpy as np
import pandas as pd

SCORE_WEIGHT = {"parking": 1 / 3, "charging": 1 / 3, "registration": 1 / 3}
SCORE_METRIC = {"parking": "parking_per_vehicle", "charging": "charger_per_electric_vehicle", "registration": "vehicle_per_household"}
SCORE_THRESHOLD = {"recommend": 70, "check": 40}
MODEL_VERSION = "listed_equal_v3"


def compute_score(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) != 25 or df["region_id"].nunique() != 25:
        raise ValueError("점수는 중복 없는 서울 25구 전체로 계산해야 합니다.")
    if set(SCORE_WEIGHT) != set(SCORE_METRIC) or any(weight < 0 for weight in SCORE_WEIGHT.values()) or not np.isclose(sum(SCORE_WEIGHT.values()), 1):
        raise ValueError("축별 가중치는 0 이상이며 합이 1이어야 합니다.")
    result = df.copy()
    value = result[list(SCORE_METRIC.values())].apply(pd.to_numeric, errors="coerce")
    result["model_version"] = MODEL_VERSION
    if not np.isfinite(value.to_numpy(dtype=float)).all() or (value < 0).any().any():
        for axis in SCORE_METRIC:
            result[axis + "_percentile"] = np.nan
        result["score"] = np.nan
        result["score_raw"] = np.nan
        result["judgment"] = "자료 부족"
        result["score_reason"] = "25구 공통 지표에 결측·잘못된 분모가 있어 백분위를 계산하지 않음"
        return result
    result["score"] = 0.0
    for axis, column in SCORE_METRIC.items():
        percentile = 100 * (value[column].rank(method="average") - 1) / 24
        if axis == "registration":
            percentile = 100 - percentile
        result[axis + "_percentile"] = percentile
        result["score"] += percentile * SCORE_WEIGHT[axis]
    result["score_raw"] = result.score
    result["judgment"] = np.select([result.score_raw >= SCORE_THRESHOLD["recommend"], result.score_raw >= SCORE_THRESHOLD["check"]], ["권장", "조건 확인"], default="보류")
    result["score"] = result.score_raw.round(1)
    result["score_reason"] = "수록자료에 따른 추정 참고판정. 실제 주차·충전 난도 또는 구매 필요를 확정하지 않음"
    return result


def condition_judgment(base: str, parking: str, charging: str | None = None) -> str:
    if base == "자료 부족":
        return base
    if base not in ("권장", "조건 확인", "보류"):
        raise ValueError("기본 판정이 올바르지 않습니다.")
    condition = [parking] if charging is None else [parking, charging]
    if any(value not in ("가능", "어려움", "미확인") for value in condition):
        raise ValueError("개인 조건이 올바르지 않습니다.")
    if base == "보류" or "어려움" in condition:
        return "보류"
    return "조건 확인" if "미확인" in condition else base
