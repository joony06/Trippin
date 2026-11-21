# 시연용 계정·리뷰·찜·조회 기록 넣기 (사업자 대시보드가 빈 화면이 되지 않게)
#
# 버전 기록
# v0.1 (2026-11-21) 사업자 데모 계정 1개 + 관광객 계정 8개(내·외국인), 최근 7일 조회 기록·찜·리뷰를 넣는다.
#                   Vercel은 함수가 새로 뜰 때마다 DB가 초기화되므로 db.init_db()가 장소를 새로 적재할 때 자동으로 실행된다.
#
# 데모 계정 (시연용, 실제 개인정보 아님)
#   사업자: demo_owner / trippin-demo   → 대시보드에서 아래 DEMO_PLACE 가게 지표를 본다
#   관광객: demo_kr1, demo_us1 ... / trippin-demo
#
# 직접 실행 (로컬 DB에 넣기):  python data/seed_demo.py
# 끄려면 환경 변수 TRIPPIN_DEMO=0

import json
import os
import random
import sys
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

DEMO_PASSWORD = "trippin-demo"
DEMO_OWNER = "demo_owner"
DEMO_PLACE = "미소본가스마일칼국수"   # 없으면 지도에 나오는 첫 관광공사 음식점
TOURISTS = [("demo_kr1", "KR"), ("demo_kr2", "KR"), ("demo_kr3", "KR"), ("demo_us1", "US"),
            ("demo_jp1", "JP"), ("demo_cn1", "CN"), ("demo_tw1", "TW"), ("demo_vn1", "VN")]
QUERIES = ["칼국수", "점심", "kalguksu", "칼국수", None, None]
REVIEWS = [("demo_kr1", 5, "국물이 진하고 양이 많아요."), ("demo_us1", 4, "Great noodles, friendly staff."),
           ("demo_jp1", 5, "とても美味しかったです。"), ("demo_kr2", 4, "점심시간엔 조금 기다려요.")]


def _pick_place(conn):
    row = conn.execute("SELECT id FROM places WHERE name = ?", (DEMO_PLACE,)).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        """SELECT id FROM places WHERE source = 'tour' AND is_conglomerate = 0 AND is_franchise = 0
           AND categories LIKE '%음식%' ORDER BY id LIMIT 1""").fetchone()
    return row[0] if row else None


def seed(conn):
    """이미 데모 계정이 있으면 아무것도 하지 않는다. 넣었으면 True"""
    if os.environ.get("TRIPPIN_DEMO") == "0":
        return False
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (DEMO_OWNER,)).fetchone():
        return False
    place_id = _pick_place(conn)
    if place_id is None:
        return False

    rng = random.Random(42)  # 매번 같은 시연 화면이 나오게
    now = datetime.now()
    pw = generate_password_hash(DEMO_PASSWORD)
    stamp = now.isoformat(timespec="seconds")

    conn.execute("INSERT INTO users (username, pw_hash, nationality, role, owner_place_id, created_at) "
                 "VALUES (?, ?, 'KR', 'owner', ?, ?)", (DEMO_OWNER, pw, place_id, stamp))
    ids = {}
    for name, nat in TOURISTS:
        cur = conn.execute("INSERT INTO users (username, pw_hash, nationality, role, created_at) "
                           "VALUES (?, ?, ?, 'tourist', ?)", (name, pw, nat, stamp))
        ids[name] = cur.lastrowid

    # 최근 7일 조회 기록 (요일마다 다르게, 주말에 더 많게)
    for day in range(7):
        d = now - timedelta(days=6 - day)
        n = rng.randint(3, 7) + (3 if d.weekday() >= 5 else 0)
        for _ in range(n):
            user = rng.choice(list(ids.values()) + [None])  # None = 로그인 안 한 방문자
            source = rng.choices(["list", "map", "direct"], weights=[5, 3, 1])[0]
            t = d.replace(hour=rng.randint(10, 20), minute=rng.randint(0, 59), second=0)
            conn.execute("INSERT INTO views (place_id, user_id, source, query, created_at) VALUES (?, ?, ?, ?, ?)",
                         (place_id, user, source, rng.choice(QUERIES) if source == "list" else None,
                          t.isoformat(timespec="seconds")))

    # 같은 업종 다른 가게에도 조금씩 (업종 평균이 0이 되지 않게)
    others = [r[0] for r in conn.execute(
        "SELECT id FROM places WHERE id != ? AND categories LIKE '[\"음식\"%' AND is_franchise = 0 "
        "AND is_conglomerate = 0 ORDER BY id LIMIT 40", (place_id,))]
    for pid in others:
        for _ in range(rng.randint(1, 9)):
            t = now - timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 8))
            conn.execute("INSERT INTO views (place_id, user_id, source, query, created_at) VALUES (?, NULL, 'list', NULL, ?)",
                         (pid, t.isoformat(timespec="seconds")))

    for name in ["demo_kr1", "demo_us1", "demo_jp1", "demo_cn1"]:
        conn.execute("INSERT INTO likes (user_id, place_id, created_at) VALUES (?, ?, ?)", (ids[name], place_id, stamp))
    for name, rating, body in REVIEWS:
        conn.execute("INSERT INTO reviews (user_id, place_id, rating, body, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)", (ids[name], place_id, rating, body, stamp, stamp))
    return True


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import db
    db.init_db()
    with db.connect() as c:
        print("데모 데이터 넣음" if seed(c) else "이미 있거나 꺼져 있어서 건너뜀")
