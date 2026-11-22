# 트립핀 테스트 (실행: python tests/test_trippin.py)
#
# 버전 기록
# v0.1 보고서 예시 A·B 재현, 필터·보정 테스트
# v0.2 빠른 다양성 보정 = 느린 방식 확인
# v0.3 대형 프랜차이즈·현재 위치
# v0.4 카테고리 필터, 보정 한도, S6·S2
# v0.5 화면 흐름 테스트 합침
# v0.6 pytest 없이 실행

import copy
import math
import os
import random
import sys
import tempfile

# 임시 DB (app import 전에 설정)
os.environ["TRIPPIN_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as trippin
import database
import search as s
from texts import romanize, romanize_dong

PW = "trippin-demo"
JUNG_GU_OFFICE = (36.3256, 127.4213)


def make_place(name, cats, desc, rating, reviews, extra=None):
    p = {"id": name, "name": name, "categories": cats, "description": desc,
         "lat": 0, "lng": 0, "fee": 0, "hours": None, "is_conglomerate": False,
         "google_rating": rating, "google_reviews": reviews,
         "own_avg": None, "own_count": 0, "likes": 0}
    if extra:
        p.update(extra)
    return p


def name_list(items):
    out = []
    for x in items:
        out.append(x["name"])
    return out


def ids(items):
    out = []
    for x in items:
        out.append(x["id"])
    return out


def rounded_contrib(r):
    out = []
    for k in s.WEIGHTS:
        out.append(round(r["contrib"][k], 3))
    return out


def make_item(id_, category, total, distance=1, reviews=0, name=None):
    return {"id": id_, "name": name or id_, "main_category": category, "distance_km": distance,
            "google_reviews": reviews, "result": {"total": total}}


def test_report_example_a_and_b():
    """중간보고서 예시: 카테고리 [역사, 사진명소, 야경], 검색어 '역사', v_max = 50,000, D_max = 10km"""
    cond = s.Conditions(categories=["역사", "사진명소", "야경"], query="역사")
    a = make_place("근대 건축물", ["역사", "사진명소"], "", 4.6, 20000, {"distance_km": 3.0})
    b = make_place("작은 카페", ["카페", "야경"], "역사가 깊은 골목의 카페", 5.0, 3, {"distance_km": 1.0})
    ctx = s.build_context([a, b], cond, v_max=50000)
    ra = s.score_place(a, cond, ctx)
    rb = s.score_place(b, cond, ctx)

    assert math.isclose(ra["scores"]["s1"], 2 / 3)
    assert ra["scores"]["s2"] == 0.7 and rb["scores"]["s2"] == 0.4
    assert math.isclose(ra["scores"]["s3"], 0.7) and math.isclose(rb["scores"]["s3"], 0.9)
    assert rounded_contrib(ra) == [0.233, 0.14, 0.14, 0.09, 0.073, 0.0]
    assert rounded_contrib(rb) == [0.117, 0.08, 0.18, 0.076, 0.01, 0.0]
    # 보고서는 항목별 반올림이라 0.1점 차이
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
    assert s.bayesian_rating(5.0, 1, 5, 4.0) < 5.0
    # 보고서 그림 3
    assert round(s.summarize([4, 5], site_avg=4.402)["adjusted"], 2) == 4.43


def test_s6_matches_report_figure():
    assert round(s.s6_own(4.5, 2, 2, 2, 4.402), 3) == 0.900


def test_s6_without_reviews_uses_likes_only():
    assert s.s6_own(None, 0, 0, 10, 4.0) == 0.0
    assert abs(s.s6_own(None, 0, 1, 1, 4.0) - 0.3) < 1e-9


def test_s2_matches_english_name_and_description():
    p = make_place("뿌리공원", ["가족"], "성씨 조형물이 있는 공원", None, None, {"name_en": "Ppuri Park"})
    assert s.s2_query(p, "ppuri") == s.S2_NAME
    assert s.s2_query(p, "성씨") == s.S2_DESCRIPTION
    assert s.s2_query(p, "museum") == 0.0


def test_romanize_and_search_by_romanized_name():
    assert romanize("미소본가스마일칼국수") == "Misobongaseumail Kalguksu"
    assert romanize("성심당") == "Seongsimdang"
    assert romanize_dong("대흥동") == "Daeheung-dong"
    p = make_place("한밭칼국수", ["음식"], "", None, None)
    assert s.s2_query(p, "kalguksu") == s.S2_NAME
    assert s.s2_query(p, "hanbat kalguksu") == s.S2_NAME


def test_hard_filter_reasons():
    cond = s.Conditions(max_km=2, budget=10000, day=5, time="14:00", origin=JUNG_GU_OFFICE)
    far = make_place("먼 곳", ["자연"], "", None, None, {"lat": 36.29, "lng": 127.39})
    pricey = make_place("비싼 곳", ["가족"], "", None, None, {"lat": 36.3256, "lng": 127.4213, "fee": 20000})
    closed = make_place("닫힌 곳", ["음식"], "", None, None, {"lat": 36.3256, "lng": 127.4213, "hours": {"0": "10:00-18:00"}})
    big = make_place("대기업 카페", ["카페"], "", None, None, {"lat": 36.3256, "lng": 127.4213, "is_conglomerate": True})
    ok = make_place("괜찮은 곳", ["역사"], "", None, None, {"lat": 36.3256, "lng": 127.4213, "hours": {"5": "10:00-18:00"}})
    kept, excluded = s.hard_filter([far, pricey, closed, big, ok], cond)
    assert name_list(kept) == ["괜찮은 곳"]
    reasons = {}
    for p, r in excluded:
        reasons[p["name"]] = r
    assert reasons["먼 곳"] == ["distance"]
    assert reasons["비싼 곳"] == ["budget"]
    assert reasons["닫힌 곳"] == ["closed"]
    assert reasons["대기업 카페"] == ["conglomerate"]


def test_franchise_is_excluded():
    chain = make_place("체인 카페 대흥점", ["카페"], "", None, None, {"lat": 36.3256, "lng": 127.4213, "is_franchise": True})
    local = make_place("동네 카페", ["카페"], "", None, None, {"lat": 36.3256, "lng": 127.4213})
    kept, excluded = s.hard_filter([chain, local], s.Conditions(origin=JUNG_GU_OFFICE))
    assert name_list(kept) == ["동네 카페"]
    assert excluded[0][1] == ["franchise"]


def test_category_mismatch_is_filtered_out():
    cafe = make_place("동네 카페", ["카페"], "", None, None, {"lat": 36.3256, "lng": 127.4213})
    shop = make_place("화장품 가게", ["쇼핑"], "", None, None, {"lat": 36.3256, "lng": 127.4213})
    both = make_place("빵집", ["카페", "음식"], "", None, None, {"lat": 36.3256, "lng": 127.4213})
    kept, excluded = s.hard_filter([cafe, shop, both], s.Conditions(categories=["카페"]))
    assert name_list(kept) == ["동네 카페", "빵집"]
    assert excluded == []
    kept, _ = s.hard_filter([cafe, shop, both], s.Conditions(categories=[]))
    assert len(kept) == 3


def test_origin_inside_jung_gu_is_used():
    origin, state = s.resolve_origin("36.3290", "127.4270")  # 으능정이 거리 부근
    assert origin == (36.329, 127.427) and state == s.ORIGIN_CURRENT


def test_origin_outside_or_missing_falls_back_to_default():
    assert s.resolve_origin("37.5665", "126.9780") == (s.DEFAULT_ORIGIN, s.ORIGIN_OUTSIDE)  # 서울
    for lat, lng in [(None, None), ("", ""), ("36.33", None), ("abc", "127.4"),
                     ("nan", "127.4"), ("inf", "127.4"), ("100", "127.4")]:
        assert s.resolve_origin(lat, lng) == (s.DEFAULT_ORIGIN, s.ORIGIN_DEFAULT)


def test_default_origin_is_inside_service_area():
    assert s.in_service_area(*s.DEFAULT_ORIGIN)


def test_search_measures_distance_from_origin():
    place = make_place("은행동 가게", ["음식"], "", None, None, {"lat": 36.3290, "lng": 127.4270})
    kept, _ = s.hard_filter([place], s.Conditions(max_km=1, origin=(36.3290, 127.4270)))
    assert len(kept) == 1 and kept[0]["distance_km"] < 0.01
    kept, excluded = s.hard_filter([place], s.Conditions(max_km=1, origin=(36.2700, 127.4000)))
    assert not kept and excluded[0][1] == ["distance"]


def test_diversity_penalty():
    items = [make_item("A", "역사", 90), make_item("B", "역사", 85), make_item("C", "역사", 81), make_item("D", "카페", 70)]
    ranked = s.rank_with_diversity(items)
    assert name_list(ranked) == ["A", "B", "D", "C"]
    c = ranked[3]
    assert c["penalty_k"] == 2 and round(c["adjusted"], 1) == 65.6


def test_diversity_penalty_is_capped():
    items = []
    for i in range(11):
        items.append(make_item(i, "음식", 90 - i, name=f"칼국수{i}"))
    items.append(make_item(99, "쇼핑", 55, name="화장품"))
    ranked = s.rank_with_diversity(items)
    assert ranked[-1]["name"] == "화장품"
    assert ranked[-2]["penalty_k"] == 3 and ranked[-2]["same_above"] == 10


def slow_diversity(items):
    """보고서 방식: 매번 남은 후보 전체에 0.9^min(k, 3)을 곱해 재비교"""
    remaining = list(items)
    counts = {}
    out = []
    while remaining:
        best = None
        best_key = None
        for it in remaining:
            k = counts.get(it["main_category"], 0)
            key = s.order_key(it["result"]["total"] * 0.9 ** min(k, s.DIVERSITY_MAX_K), it)
            if best_key is None or key < best_key:
                best, best_key = it, key
        remaining.remove(best)
        counts[best["main_category"]] = counts.get(best["main_category"], 0) + 1
        out.append(best["id"])
    return out


def test_fast_diversity_matches_slow():
    rng = random.Random(7)
    for _ in range(300):
        items = []
        for i in range(rng.randint(1, 30)):
            items.append(make_item(i, rng.choice("abcd"), rng.choice([50, 60, 70, 72.9, 81, 90]),
                                   distance=rng.choice([0.5, 1, 2]), reviews=rng.choice([0, 10, None])))
        fast = ids(s.rank_with_diversity(copy.deepcopy(items)))
        assert fast == slow_diversity(copy.deepcopy(items))


def new_client():
    return trippin.app.test_client()


def login(client, name):
    return client.post("/login", data={"username": name, "password": PW})


def owner_place():
    return database.get_user_by_name("demo_owner")["owner_place_id"]


def test_owner_cannot_review_or_like_own_place():
    client = new_client()
    pid = owner_place()
    login(client, "demo_owner")
    likes = database.dashboard_stats(pid)["likes"]
    reviews = len(database.reviews_for_place(pid))
    client.post(f"/place/{pid}/review", data={"rating": 5, "body": "최고", "next": f"/place/{pid}"})
    client.post(f"/place/{pid}/like", data={"next": f"/place/{pid}"})
    assert database.dashboard_stats(pid)["likes"] == likes
    assert len(database.reviews_for_place(pid)) == reviews


def test_owner_views_and_repeat_views_are_not_counted():
    client = new_client()
    pid = owner_place()
    login(client, "demo_owner")
    before = database.dashboard_stats(pid)["total_views"]
    for _ in range(5):
        client.get(f"/place/{pid}")
    assert database.dashboard_stats(pid)["total_views"] == before

    other = new_client()
    for _ in range(5):
        other.get(f"/place/{pid}")
    assert database.dashboard_stats(pid)["total_views"] == before + 1


def test_like_before_login_is_kept_after_login():
    client = new_client()
    r = client.post("/place/7/like", data={"next": "/place/7?q=test"})
    assert r.status_code == 302 and r.headers["Location"].startswith("/login")
    r = client.post(r.headers["Location"], data={"username": "demo_kr2", "password": PW})
    assert r.headers["Location"] == "/place/7?q=test"
    assert database.has_liked(database.get_user_by_name("demo_kr2")["id"], 7)


def test_view_is_counted_once_across_login_and_logout():
    client = new_client()
    before = database.dashboard_stats(8)["total_views"]
    client.get("/place/8")
    r = client.post("/place/8/like", data={"next": "/place/8"})
    r = client.post(r.headers["Location"], data={"username": "demo_kr3", "password": PW})
    client.get(r.headers["Location"])
    client.get("/logout")
    client.get("/place/8")
    assert database.dashboard_stats(8)["total_views"] == before + 1


if __name__ == "__main__":
    names = []
    for name in list(globals()):
        if name.startswith("test_"):
            names.append(name)
    failed = 0
    for name in names:
        try:
            globals()[name]()
            print("통과", name)
        except AssertionError:
            failed += 1
            print("실패", name)
    print(f"\n{len(names) - failed}/{len(names)}개 통과")
    if failed:
        sys.exit(1)
    sys.exit(0)
