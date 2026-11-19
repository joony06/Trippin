# 거리 계산 (하버사인 공식)
#
# 버전 기록
# v0.1 (2026-11-18) 두 위도·경도 사이의 거리(km) 계산 함수 작성
# v0.2 (2026-11-19) 현재 위치 반영: 브라우저 위치가 대전 중구 안이면 사용, 없거나 밖이면 기본 위치

import math

EARTH_RADIUS_KM = 6371.0

# 기본 출발점: 대전 중구청 앞 (근사 좌표). 위치를 못 받았거나 중구 밖이면 이 값을 쓴다
DEFAULT_ORIGIN = (36.3256, 127.4213)

# 서비스 지역(대전 중구)을 감싸는 사각형 (남, 북, 서, 동).
# data/places.json 장소 좌표의 범위(위도 36.23~36.35, 경도 127.37~127.46)에 여유 0.01도를 더한 근사 범위.
# 이 범위 밖(예: 서울)에서 접속하면 거리 점수가 의미 없으므로 기본 위치로 계산한다.
SERVICE_BOUNDS = (36.22, 36.36, 127.36, 127.47)

# 출발점 상태: 화면 문구(i18n)를 고르는 데 쓴다
ORIGIN_CURRENT = "current"   # 브라우저 위치를 사용함
ORIGIN_OUTSIDE = "outside"   # 위치는 받았지만 대전 중구 밖이라 기본 위치 사용
ORIGIN_DEFAULT = "default"   # 위치를 못 받음(거부·미지원·시간 초과) → 기본 위치 사용


def haversine_km(lat1, lon1, lat2, lon2):
    """두 지점 사이의 대원 거리(km)를 구한다."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def in_service_area(lat, lng):
    """좌표가 서비스 지역(대전 중구 근사 범위) 안에 있는지"""
    south, north, west, east = SERVICE_BOUNDS
    return south <= lat <= north and west <= lng <= east


def _to_coord(value, limit):
    """문자열을 위도·경도 숫자로 바꾼다. 숫자가 아니거나 범위를 벗어나면 None"""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or abs(x) > limit:
        return None
    return x


def resolve_origin(lat, lng):
    """브라우저가 보낸 lat, lng로 출발점을 정한다. ((위도, 경도), 상태)

    - 둘 다 올바른 숫자이고 대전 중구 안이면 그 위치 (current)
    - 올바른 숫자지만 중구 밖이면 기본 위치 (outside)
    - 비었거나 잘못된 값이면 기본 위치 (default)
    """
    la, lo = _to_coord(lat, 90), _to_coord(lng, 180)
    if la is None or lo is None:
        return DEFAULT_ORIGIN, ORIGIN_DEFAULT
    if not in_service_area(la, lo):
        return DEFAULT_ORIGIN, ORIGIN_OUTSIDE
    return (la, lo), ORIGIN_CURRENT
