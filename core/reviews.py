# 평점 보정 (베이지안 평균)
#
# 버전 기록
# v0.1 (2026-11-18) 베이지안 보정 평점 R′ 계산과 1~5점 → 0~1 변환 함수 작성

# 구글 평점 보정값 (S4): 믿을 만한 최소 리뷰 수 m, 전체 평균 C
GOOGLE_M = 50
GOOGLE_C = 4.0

# 자체 평점 보정값 (S6): 사이트 사용자가 적으므로 m을 작게 둔다
OWN_M = 5
DEFAULT_SITE_AVG = 4.0  # 사이트에 리뷰가 하나도 없을 때 쓰는 C


def bayesian_rating(avg, count, m, c):
    """R′ = (v·R + m·C) / (v + m). 리뷰가 적을수록 C 쪽으로 당겨진다."""
    if count <= 0 or avg is None:
        return c
    return (count * avg + m * c) / (count + m)


def rating_to_unit(r):
    """1~5점을 0~1로 바꾼다: (R′ − 1) ÷ 4"""
    return max(0.0, min(1.0, (r - 1) / 4))


def summarize(ratings, site_avg=None):
    """리뷰 별점 목록으로 평균·개수·보정 평점을 한 번에 구한다."""
    c = site_avg if site_avg is not None else DEFAULT_SITE_AVG
    count = len(ratings)
    avg = sum(ratings) / count if count else None
    return {
        "count": count,
        "avg": avg,
        "adjusted": bayesian_rating(avg, count, OWN_M, c),
        "site_avg": c,
    }
