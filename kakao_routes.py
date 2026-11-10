"""카카오맵 도보 경로의 거리와 예상 소요 시간 조회."""
import math

import requests

from kakao_map import rest_key


def get_walking_route(start_latitude: float, start_longitude: float,
                      end_latitude: float, end_longitude: float) -> dict[str, int] | None:
    """WGS84 위도·경도를 받아 거리(m)와 소요 시간(s)을 반환한다. 응답은 저장하지 않는다."""
    try:
        values = (start_latitude, start_longitude, end_latitude, end_longitude)
        if any(isinstance(value, bool) for value in values):
            return None
        coordinates = tuple(float(value) for value in values)
        if any(not math.isfinite(value) or not -limit <= value <= limit
               for value, limit in zip(coordinates, (90, 180, 90, 180))):
            return None
        key = rest_key()
        if not key:
            return None
        start_lat, start_lon, end_lat, end_lon = coordinates
        with requests.get(
            "https://dapi.kakao.com/v2/routing/walk",
            headers={"Authorization": f"KakaoAK {key}"},
            params={"start_x": str(start_lon), "start_y": str(start_lat),
                    "end_x": str(end_lon), "end_y": str(end_lat), "input_coord": "WGS84"},
            timeout=(3, 5), allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                return None
            payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            return None
        properties = payload["route"]["properties"]
        distance, duration = properties["totalDistance"], properties["totalTime"]
        if any(type(value) is not int or value < 0 for value in (distance, duration)):
            return None
        return {"distance_m": distance, "duration_s": duration}
    except (requests.RequestException, KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return None
