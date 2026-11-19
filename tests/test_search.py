# 검색 점수·리뷰 보정 테스트 (중간보고서 계산 예시 재현)
#
# 버전 기록
# v0.1 (2026-11-18) 보고서 예시 A 67.6점·B 46.3점 재현, 하드 필터·다양성 보정·베이지안 보정 테스트 작성
# v0.2 (2026-11-18) 빨라진 다양성 보정이 '하나씩 다시 비교하는' 원래 방식과 같은 순서를 내는지 확인하는 테스트 추가
# v0.3 (2026-11-18) 대형 프랜차이즈 하드 필터 테스트 추가
# v0.4 (2026-11-19) 현재 위치(출발점) 테스트 추가: 중구 안이면 사용, 밖·거부·잘못된 값이면 기본 위치
#
# 실행: python -m pytest -q

import math

from core import geo
from core import search as s
from core.reviews import bayesian_rating, summarize


def _place(name, cats, desc, rating, reviews, **kw):
    p = {"id": name, "name": name, "categories": cats, "description": desc,
         "lat": 0, "lng": 0, "fee": 0, "hours": None, "is_conglomerate": False,
         "google_rating": rating, "google_reviews": reviews,
         "own_avg": None, "own_count": 0, "likes": 0}
    p.update(kw)
    return p


def test_report_example_a_and_b():
    """카테고리 [역사, 사진명소, 야경], 검색어 '역사', v_max = 50,000, D_max = 10km"""
    cond = s.Conditions(categories=["역사", "사진명소", "야경"], query="역사")
    a = _place("근대 건축물", ["역사", "사진명소"], "", 4.6, 20000, distance_km=3.0)
    b = _place("작은 카페", ["카페", "야경"], "역사가 깊은 골목의 카페", 5.0, 3, distance_km=1.0)
    ctx = s.build_context([a, b], cond, v_max=50000)

    ra = s.score_place(a, cond, ctx)
    rb = s.score_place(b, cond, ctx)

    assert math.isclose(ra["scores"]["s1"], 2 / 3)
    assert ra["scores"]["s2"] == 0.7 and rb["scores"]["s2"] == 0.4
    assert math.isclose(ra["scores"]["s3"], 0.7) and math.isclose(rb["scores"]["s3"], 0.9)
    # 항목별 반영 점수(소수 셋째 자리)는 보고서 표와 같다
    assert [round(ra["contrib"][k], 3) for k in s.WEIGHTS] == [0.233, 0.14, 0.14, 0.09, 0.073, 0.0]
    assert [round(rb["contrib"][k], 3) for k in s.WEIGHTS] == [0.117, 0.08, 0.18, 0.076, 0.01, 0.0]
    # 총점은 보고서가 항목별로 반올림해 더했기 때문에 0.1점 안쪽 차이가 난다
    assert abs(ra["total"] - 67.6) < 0.1
    assert abs(rb["total"] - 46.3) < 0.1


def test_no_query_drops_s2_and_renormalizes():
    w = s.active_weights(s.Conditions(categories=["역사"], query=""))
    assert "s2" not in w
    assert math.isclose(sum(w.values()), 1.0)
    assert math.isclose(w["s1"], 0.35 / 0.8)


def test_missing_google_data_is_neutral():
    assert s.s4_google_rating(None, None) == 0.5
    assert s.s5_popularity(None, 1000) == 0.5


def test_bayesian_pulls_few_reviews_toward_mean():
    # 리뷰 1개 5.0점은 보정 후 5.0보다 낮아진다
    assert bayesian_rating(5.0, 1, 5, 4.0) < 5.0
    # 보고서 그림 3: 리뷰 2개 평균 4.5 → R′ 4.43 (사이트 평균 약 4.4)
    assert round(summarize([4, 5], site_avg=4.402)["adjusted"], 2) == 4.43


def test_s6_matches_report_figure():
    # 리뷰 2개 평균 4.5, 찜 2개(후보 중 최대) → S6 0.900
    v = s.s6_own(4.5, 2, 2, 2, 4.402)
    assert round(v, 3) == 0.900


def test_hard_filter_reasons():
    cond = s.Conditions(max_km=2, budget=10000, day=5, time="14:00", origin=(36.3256, 127.4213))
    far = _place("먼 곳", ["자연"], "", None, None, lat=36.29, lng=127.39)
    pricey = _place("비싼 곳", ["가족"], "", None, None, lat=36.3256, lng=127.4213, fee=20000)
    closed = _place("닫힌 곳", ["음식"], "", None, None, lat=36.3256, lng=127.4213,
                    hours={"0": "10:00-18:00"})
    big = _place("대기업 카페", ["카페"], "", None, None, lat=36.3256, lng=127.4213,
                 is_conglomerate=True)
    ok = _place("괜찮은 곳", ["역사"], "", None, None, lat=36.3256, lng=127.4213,
                hours={"5": "10:00-18:00"})
    kept, excluded = s.hard_filter([far, pricey, closed, big, ok], cond)
    assert [p["name"] for p in kept] == ["괜찮은 곳"]
    reasons = {p["name"]: r for p, r in excluded}
    assert reasons["먼 곳"] == ["distance"]
    assert reasons["비싼 곳"] == ["budget"]
    assert reasons["닫힌 곳"] == ["closed"]
    assert reasons["대기업 카페"] == ["conglomerate"]


def test_diversity_penalty():
    # 같은 대표 카테고리 세 번째 후보는 0.9² 를 곱해 비교한다
    items = []
    for name, total, cat in [("A", 90, "역사"), ("B", 85, "역사"), ("C", 81, "역사"), ("D", 70, "카페")]:
        items.append({"name": name, "main_category": cat, "distance_km": 1,
                      "google_reviews": 0, "result": {"total": total}})
    ranked = s.rank_with_diversity(items)
    assert [r["name"] for r in ranked] == ["A", "B", "D", "C"]
    c = next(r for r in ranked if r["name"] == "C")
    assert c["penalty_k"] == 2 and round(c["adjusted"], 1) == 65.6


def _naive_diversity(items):
    """보고서 설명 그대로: 매번 남은 후보 전체에 0.9^k를 곱해 다시 비교"""
    remaining, counts, out = list(items), {}, []
    while remaining:
        for it in remaining:
            it["_adj"] = it["result"]["total"] * 0.9 ** counts.get(it["main_category"], 0)
        remaining.sort(key=lambda it: (-round(it["_adj"], 9), *s._tie_key(it)))
        best = remaining.pop(0)
        counts[best["main_category"]] = counts.get(best["main_category"], 0) + 1
        out.append(best["id"])
    return out


def test_fast_diversity_matches_naive():
    import copy
    import random
    rng = random.Random(7)
    for _ in range(300):
        items = [{"id": i, "main_category": rng.choice("abcd"), "distance_km": rng.choice([0.5, 1, 2]),
                  "google_reviews": rng.choice([0, 10, None]),
                  "result": {"total": rng.choice([50, 60, 70, 72.9, 81, 90])}}
                 for i in range(rng.randint(1, 30))]
        fast = [x["id"] for x in s.rank_with_diversity(copy.deepcopy(items))]
        assert fast == _naive_diversity(copy.deepcopy(items))


def test_franchise_is_excluded():
    cond = s.Conditions(origin=(36.3256, 127.4213))
    chain = _place("체인 카페 대흥점", ["카페"], "", None, None, lat=36.3256, lng=127.4213, is_franchise=True)
    local = _place("동네 카페", ["카페"], "", None, None, lat=36.3256, lng=127.4213)
    kept, excluded = s.hard_filter([chain, local], cond)
    assert [p["name"] for p in kept] == ["동네 카페"]
    assert excluded[0][1] == ["franchise"]


def test_origin_inside_jung_gu_is_used():
    # 대전 중구 안(으능정이 거리 부근)이면 브라우저 위치를 그대로 쓴다
    origin, state = geo.resolve_origin("36.3290", "127.4270")
    assert origin == (36.329, 127.427) and state == geo.ORIGIN_CURRENT


def test_origin_outside_or_missing_falls_back_to_default():
    # 서울(시연 장소)처럼 중구 밖이면 기본 위치
    assert geo.resolve_origin("37.5665", "126.9780") == (geo.DEFAULT_ORIGIN, geo.ORIGIN_OUTSIDE)
    # 위치를 거부해 값이 비었거나, 잘못된 값이면 기본 위치
    for lat, lng in [(None, None), ("", ""), ("36.33", None), ("abc", "127.4"),
                     ("nan", "127.4"), ("inf", "127.4"), ("100", "127.4")]:
        assert geo.resolve_origin(lat, lng) == (geo.DEFAULT_ORIGIN, geo.ORIGIN_DEFAULT)


def test_default_origin_is_inside_service_area():
    assert geo.in_service_area(*geo.DEFAULT_ORIGIN)


def test_search_measures_distance_from_origin():
    # 같은 장소라도 출발점이 바뀌면 거리(하드 필터·S3)가 바뀐다
    place = _place("은행동 가게", ["음식"], "", None, None, lat=36.3290, lng=127.4270)
    near = s.Conditions(max_km=1, origin=(36.3290, 127.4270))
    far = s.Conditions(max_km=1, origin=(36.2700, 127.4000))
    kept, _ = s.hard_filter([place], near)
    assert len(kept) == 1 and kept[0]["distance_km"] < 0.01
    kept, excluded = s.hard_filter([place], far)
    assert not kept and excluded[0][1] == ["distance"]
