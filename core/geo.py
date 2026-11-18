# 거리 계산 (하버사인 공식)
#
# 버전 기록
# v0.1 (2026-11-18) 두 위도·경도 사이의 거리(km) 계산 함수 작성

import math

EARTH_RADIUS_KM = 6371.0

# 프로토타입 기준 현재 위치: 대전 중구청 앞 (근사 좌표)
DEFAULT_ORIGIN = (36.3256, 127.4213)


def haversine_km(lat1, lon1, lat2, lon2):
    """두 지점 사이의 대원 거리(km)를 구한다."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
