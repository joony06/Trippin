# 화면 흐름 테스트 (사용자 테스트 5·6·7번 재현)
#
# 버전 기록
# v0.1 (2026-11-21) 사업자 자기 가게 리뷰·찜 차단, 같은 날 반복 조회 1회·사업자 본인 조회 제외, 로그인 전 찜 → 로그인 후 처리
#
# 실행: python -m pytest -q

import os
import tempfile

import pytest

os.environ["TRIPPIN_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

import app as trippin  # noqa: E402  (DB 경로를 정한 뒤 불러온다)
import db  # noqa: E402

PW = "trippin-demo"


def _owner_place():
    with db.connect() as conn:
        return conn.execute("SELECT owner_place_id FROM users WHERE username = 'demo_owner'").fetchone()[0]


def _uid(name):
    return db.get_user_by_name(name)["id"]


@pytest.fixture
def client():
    return trippin.app.test_client()


def _login(c, name):
    return c.post("/login", data={"username": name, "password": PW})


def test_owner_cannot_review_or_like_own_place(client):
    pid = _owner_place()
    _login(client, "demo_owner")
    likes = db.dashboard_stats(pid)["likes"]
    reviews = len(db.reviews_for_place(pid))
    client.post(f"/place/{pid}/review", data={"rating": 5, "body": "최고", "next": f"/place/{pid}"})
    client.post(f"/place/{pid}/like", data={"next": f"/place/{pid}"})
    assert db.dashboard_stats(pid)["likes"] == likes
    assert len(db.reviews_for_place(pid)) == reviews


def test_owner_views_and_repeat_views_are_not_counted(client):
    pid = _owner_place()
    _login(client, "demo_owner")
    before = db.dashboard_stats(pid)["total_views"]
    for _ in range(5):
        client.get(f"/place/{pid}")
    assert db.dashboard_stats(pid)["total_views"] == before

    other = trippin.app.test_client()
    for _ in range(5):
        other.get(f"/place/{pid}")
    assert db.dashboard_stats(pid)["total_views"] == before + 1


def test_like_before_login_is_kept_after_login(client):
    r = client.post("/place/7/like", data={"next": "/place/7?q=test"})
    assert r.status_code == 302 and r.headers["Location"].startswith("/login")
    r = client.post(r.headers["Location"], data={"username": "demo_kr2", "password": PW})
    assert r.headers["Location"] == "/place/7?q=test"
    assert db.has_liked(_uid("demo_kr2"), 7)
