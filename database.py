# 트립핀 데이터 저장: SQLite(파이썬 기본 sqlite3 모듈)로 장소·회원·리뷰·찜·조회 기록을 저장하고 꺼낸다
#
# 버전 기록
# v0.1 (2026-11-18) 테이블 생성(장소·회원·리뷰·찜·조회 기록), 샘플 데이터 적재, 조회·저장 함수 작성 (db.py)
# v0.2 (2026-11-18) 실제 데이터(data/places.json) 적재, 장소에 영문 이름·동·주소·사진·출처 열 추가
# v0.3 (2026-11-18) 대형 프랜차이즈 여부(is_franchise) 열 추가
# v0.4 (2026-11-19) 영문 설명문(description_en) 열 추가
# v0.5 (2026-11-21) 업종 평균 조회수: 최근 7일, 조회가 있는 같은 업종 가게끼리 평균. 장소를 새로 넣을 때 시연용 데이터도 함께 넣음
# v0.6 (2026-11-21) 시연용 계정·리뷰·찜·조회 기록 넣기 (data/seed_demo.py)
# v0.7 (2026-11-22) 수업 수준으로 다시 정리: db.py + data/seed_demo.py를 이 파일 하나로 합침
#                   - 쓰지 않던 샘플 데이터(data/sample_places.json) 대신 항상 data/places.json을 넣음
#                   - 같은 날짜 계산·딕셔너리 만들기를 for 반복문으로 풀어 씀. 저장되는 값과 화면 결과는 v0.6과 같다
#
# 저장 위치
# - 로컬: 프로젝트 폴더의 trippin.db (처음 실행할 때 자동으로 만들어진다. 환경 변수 TRIPPIN_DB로 바꿀 수 있음)
# - Vercel: /tmp/trippin.db. 서버가 새로 뜨면 처음 상태로 돌아간다 (시연용)
#
# 시연용 계정 (실제 개인정보 아님, 비밀번호는 모두 trippin-demo)
#   사업자: demo_owner → 대시보드에서 DEMO_PLACE 가게의 지표를 본다
#   관광객: demo_kr1, demo_us1, demo_jp1 …
#   넣지 않으려면 환경 변수 TRIPPIN_DEMO=0

import json
import os
import random
import sqlite3
from datetime import datetime, timedelta

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLACES_PATH = os.path.join(BASE_DIR, "data", "places.json")  # data/tools/build_places.py 결과

if os.environ.get("TRIPPIN_DB"):
    DB_PATH = os.environ["TRIPPIN_DB"]
elif os.environ.get("VERCEL") == "1":
    DB_PATH = "/tmp/trippin.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "trippin.db")

# 시연용 데이터
DEMO_PASSWORD = "trippin-demo"
DEMO_OWNER = "demo_owner"
DEMO_PLACE = "미소본가스마일칼국수"   # 없으면 관광공사 음식점 중 첫 번째
DEMO_TOURISTS = [("demo_kr1", "KR"), ("demo_kr2", "KR"), ("demo_kr3", "KR"), ("demo_us1", "US"),
                 ("demo_jp1", "JP"), ("demo_cn1", "CN"), ("demo_tw1", "TW"), ("demo_vn1", "VN")]
DEMO_QUERIES = ["칼국수", "점심", "kalguksu", "칼국수", None, None]
DEMO_REVIEWS = [("demo_kr1", 5, "국물이 진하고 양이 많아요."), ("demo_us1", 4, "Great noodles, friendly staff."),
                ("demo_jp1", 5, "とても美味しかったです。"), ("demo_kr2", 4, "점심시간엔 조금 기다려요.")]
DEMO_LIKERS = ["demo_kr1", "demo_us1", "demo_jp1", "demo_cn1"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    categories TEXT NOT NULL,          -- JSON 목록, 첫 번째가 대표 카테고리
    description TEXT,
    description_en TEXT,               -- Gemini 영문 설명 (관광공사 장소)
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    fee INTEGER DEFAULT 0,
    hours TEXT,                        -- JSON {"0": "10:00-18:00", ...}
    is_conglomerate INTEGER DEFAULT 0,
    is_franchise INTEGER DEFAULT 0,    -- 대형 프랜차이즈 (하드 필터)
    google_rating REAL,
    google_reviews INTEGER,
    name_en TEXT,
    dong TEXT,
    address TEXT,
    image TEXT,
    source TEXT                        -- tour(관광공사) / sbiz(상가정보)
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    nationality TEXT NOT NULL,         -- KR 또는 국가 코드
    role TEXT NOT NULL DEFAULT 'tourist',  -- tourist / owner
    owner_place_id INTEGER REFERENCES places(id),
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    place_id INTEGER NOT NULL REFERENCES places(id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    body TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, place_id)         -- 1인 1리뷰
);
CREATE TABLE IF NOT EXISTS likes (
    user_id INTEGER NOT NULL REFERENCES users(id),
    place_id INTEGER NOT NULL REFERENCES places(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, place_id)
);
CREATE TABLE IF NOT EXISTS views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id INTEGER NOT NULL REFERENCES places(id),
    user_id INTEGER REFERENCES users(id),
    source TEXT NOT NULL,              -- list / map / direct (어디서 눌러 들어왔는지)
    query TEXT,                        -- 그때의 검색어
    created_at TEXT NOT NULL
);
"""


# ---------------------------------------------------------------- 준비

def now():
    return datetime.now().isoformat(timespec="seconds")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 결과를 row["name"]처럼 이름으로 꺼낼 수 있게
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset=False):
    """테이블을 만들고, 장소가 비어 있으면 places.json과 시연용 데이터를 넣는다."""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with connect() as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        if count == 0:
            load_places(conn, PLACES_PATH)
            seed_demo(conn)


def load_places(conn, path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for p in data["places"]:
        hours = json.dumps(p.get("hours")) if p.get("hours") is not None else None
        conn.execute(
            """INSERT OR REPLACE INTO places
               (id, name, categories, description, description_en, lat, lng, fee, hours,
                is_conglomerate, is_franchise, google_rating, google_reviews,
                name_en, dong, address, image, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["id"], p["name"], json.dumps(p["categories"], ensure_ascii=False),
             p.get("description"), p.get("description_en"), p["lat"], p["lng"], p.get("fee", 0), hours,
             int(p.get("is_conglomerate", False)), int(p.get("is_franchise", False)),
             p.get("google_rating"), p.get("google_reviews"),
             p.get("name_en"), p.get("dong"), p.get("address"), p.get("image"), p.get("source", "sample")),
        )


# ---------------------------------------------------------------- 시연용 데이터 (사업자 대시보드가 빈 화면이 되지 않게)

def pick_demo_place(conn):
    row = conn.execute("SELECT id FROM places WHERE name = ?", (DEMO_PLACE,)).fetchone()
    if row:
        return row[0]
    row = conn.execute(
        """SELECT id FROM places WHERE source = 'tour' AND is_conglomerate = 0 AND is_franchise = 0
           AND categories LIKE '%음식%' ORDER BY id LIMIT 1""").fetchone()
    return row[0] if row else None


def insert_view(conn, place_id, user_id, source, query, when):
    conn.execute("INSERT INTO views (place_id, user_id, source, query, created_at) VALUES (?, ?, ?, ?, ?)",
                 (place_id, user_id, source, query, when.isoformat(timespec="seconds")))


def seed_demo(conn):
    """시연용 계정·리뷰·찜·최근 7일 조회 기록을 넣는다. 이미 있거나 꺼져 있으면 넣지 않는다. 넣었으면 True"""
    if os.environ.get("TRIPPIN_DEMO") == "0":
        return False
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (DEMO_OWNER,)).fetchone():
        return False
    place_id = pick_demo_place(conn)
    if place_id is None:
        return False

    rng = random.Random(42)  # 씨앗(42)을 고정해 매번 같은 시연 화면이 나오게 (10주차 random 모듈)
    today = datetime.now()
    pw = generate_password_hash(DEMO_PASSWORD)
    stamp = today.isoformat(timespec="seconds")

    conn.execute("INSERT INTO users (username, pw_hash, nationality, role, owner_place_id, created_at) "
                 "VALUES (?, ?, 'KR', 'owner', ?, ?)", (DEMO_OWNER, pw, place_id, stamp))
    ids = {}  # 관광객 아이디 → 회원 번호
    for name, nationality in DEMO_TOURISTS:
        cur = conn.execute("INSERT INTO users (username, pw_hash, nationality, role, created_at) "
                           "VALUES (?, ?, ?, 'tourist', ?)", (name, pw, nationality, stamp))
        ids[name] = cur.lastrowid

    # 최근 7일 조회 기록 (하루 3~7번, 주말은 3번 더)
    visitors = list(ids.values()) + [None]  # None = 로그인 안 한 방문자
    for day in range(7):
        d = today - timedelta(days=6 - day)
        n = rng.randint(3, 7)
        if d.weekday() >= 5:
            n += 3
        for _ in range(n):
            user = rng.choice(visitors)
            source = rng.choices(["list", "map", "direct"], weights=[5, 3, 1])[0]
            when = d.replace(hour=rng.randint(10, 20), minute=rng.randint(0, 59), second=0)
            query = rng.choice(DEMO_QUERIES) if source == "list" else None
            insert_view(conn, place_id, user, source, query, when)

    # 같은 업종 다른 가게 40곳에도 조회를 조금씩 (업종 평균이 0이 되지 않게)
    others = conn.execute(
        "SELECT id FROM places WHERE id != ? AND categories LIKE '[\"음식\"%' AND is_franchise = 0 "
        "AND is_conglomerate = 0 ORDER BY id LIMIT 40", (place_id,)).fetchall()
    for row in others:
        for _ in range(rng.randint(1, 9)):
            when = today - timedelta(days=rng.randint(0, 6), hours=rng.randint(0, 8))
            insert_view(conn, row[0], None, "list", None, when)

    for name in DEMO_LIKERS:
        conn.execute("INSERT INTO likes (user_id, place_id, created_at) VALUES (?, ?, ?)", (ids[name], place_id, stamp))
    for name, rating, body in DEMO_REVIEWS:
        conn.execute("INSERT INTO reviews (user_id, place_id, rating, body, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?)", (ids[name], place_id, rating, body, stamp, stamp))
    return True


# ---------------------------------------------------------------- 장소

def place_from_row(row):
    """DB 한 줄 → 장소 딕셔너리 (JSON 글자는 목록·딕셔너리로, 0/1은 True/False로)"""
    p = dict(row)
    p["categories"] = json.loads(p["categories"])
    p["hours"] = json.loads(p["hours"]) if p["hours"] else None
    p["is_conglomerate"] = bool(p["is_conglomerate"])
    p["is_franchise"] = bool(p["is_franchise"])
    return p


def all_places_with_stats():
    """검색에 쓰는 장소 정보 + 트립핀 리뷰 평균·개수 + 찜 수"""
    with connect() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      (SELECT AVG(rating) FROM reviews r WHERE r.place_id = p.id) AS own_avg,
                      (SELECT COUNT(*) FROM reviews r WHERE r.place_id = p.id) AS own_count,
                      (SELECT COUNT(*) FROM likes l WHERE l.place_id = p.id) AS likes
               FROM places p ORDER BY p.id"""
        ).fetchall()
    places = []
    for r in rows:
        places.append(place_from_row(r))
    return places


def get_place(place_id):
    """장소 번호로 하나 찾기. 없으면 None"""
    for p in all_places_with_stats():
        if p["id"] == place_id:
            return p
    return None


def site_average():
    """사이트 전체 평균 별점 (S6의 C). 리뷰가 없으면 None"""
    with connect() as conn:
        return conn.execute("SELECT AVG(rating) FROM reviews").fetchone()[0]


# ---------------------------------------------------------------- 회원

def create_user(username, pw_hash, nationality, role="tourist", owner_place_id=None):
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO users (username, pw_hash, nationality, role, owner_place_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (username, pw_hash, nationality, role, owner_place_id, now()),
        )
        return cur.lastrowid


def get_user_by_name(username):
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user(user_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- 리뷰·찜

def upsert_review(user_id, place_id, rating, body):
    """같은 가게에 다시 쓰면 수정으로 처리한다 (1인 1리뷰)."""
    t = now()
    with connect() as conn:
        conn.execute(
            """INSERT INTO reviews (user_id, place_id, rating, body, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, place_id)
               DO UPDATE SET rating = excluded.rating, body = excluded.body,
                             updated_at = excluded.updated_at""",
            (user_id, place_id, rating, body, t, t),
        )


def reviews_for_place(place_id):
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.*, u.username, u.nationality FROM reviews r
               JOIN users u ON u.id = r.user_id
               WHERE r.place_id = ? ORDER BY r.updated_at DESC""",
            (place_id,),
        ).fetchall()
    reviews = []
    for r in rows:
        reviews.append(dict(r))
    return reviews


def user_review(user_id, place_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE user_id = ? AND place_id = ?", (user_id, place_id)).fetchone()
    return dict(row) if row else None


def toggle_like(user_id, place_id):
    """찜이 있으면 지우고 없으면 넣는다. 결과로 찜 상태(True/False)를 돌려준다."""
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM likes WHERE user_id = ? AND place_id = ?", (user_id, place_id)).fetchone()
        if exists:
            conn.execute("DELETE FROM likes WHERE user_id = ? AND place_id = ?", (user_id, place_id))
            return False
        conn.execute("INSERT INTO likes (user_id, place_id, created_at) VALUES (?, ?, ?)", (user_id, place_id, now()))
        return True


def has_liked(user_id, place_id):
    with connect() as conn:
        row = conn.execute("SELECT 1 FROM likes WHERE user_id = ? AND place_id = ?", (user_id, place_id)).fetchone()
    return row is not None


# ---------------------------------------------------------------- 조회 기록·사업자 대시보드

def log_view(place_id, user_id, source, query):
    with connect() as conn:
        conn.execute("INSERT INTO views (place_id, user_id, source, query, created_at) VALUES (?, ?, ?, ?, ?)",
                     (place_id, user_id, source, query or None, now()))


def dashboard_stats(place_id, days=7):
    """사업자 대시보드 지표: 일별 조회수, 찜 수, 유입 경로, 내·외국인 비율, 많이 걸린 검색어, 업종 평균 조회수"""
    since = (datetime.now() - timedelta(days=days - 1)).date().isoformat()
    with connect() as conn:
        daily_rows = conn.execute(
            """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n FROM views
               WHERE place_id = ? AND substr(created_at, 1, 10) >= ? GROUP BY day""",
            (place_id, since)).fetchall()
        source_rows = conn.execute(
            "SELECT source, COUNT(*) AS n FROM views WHERE place_id = ? GROUP BY source", (place_id,)).fetchall()
        visitor_rows = conn.execute(
            """SELECT CASE WHEN u.nationality = 'KR' THEN 'domestic' ELSE 'foreign' END AS kind, COUNT(*) AS n
               FROM views v JOIN users u ON u.id = v.user_id
               WHERE v.place_id = ? GROUP BY kind""",
            (place_id,)).fetchall()
        query_rows = conn.execute(
            """SELECT query, COUNT(*) AS n FROM views
               WHERE place_id = ? AND query IS NOT NULL GROUP BY query ORDER BY n DESC LIMIT 5""",
            (place_id,)).fetchall()
        total_views = conn.execute("SELECT COUNT(*) FROM views WHERE place_id = ?", (place_id,)).fetchone()[0]
        likes = conn.execute("SELECT COUNT(*) FROM likes WHERE place_id = ?", (place_id,)).fetchone()[0]
        per_place = conn.execute(
            """SELECT p.id, p.categories,
                      (SELECT COUNT(*) FROM views v WHERE v.place_id = p.id AND substr(v.created_at, 1, 10) >= ?) AS n
               FROM places p""",
            (since,)).fetchall()

    # 최근 7일을 하루씩: 조회가 없는 날은 0
    by_day = {}
    for r in daily_rows:
        by_day[r["day"]] = r["n"]
    daily = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=days - 1 - i)).date().isoformat()
        daily.append({"day": d, "n": by_day.get(d, 0)})

    # 같은 업종(대표 카테고리) 평균 조회수: 최근 7일 동안 조회가 있었던 같은 업종 가게끼리 평균
    # (수천 곳의 0을 섞으면 평균이 0에 가까워진다)
    main_cat = None
    for r in per_place:
        if r["id"] == place_id:
            main_cat = json.loads(r["categories"])[0]
    same = []
    for r in per_place:
        if r["n"] > 0 and r["id"] != place_id and json.loads(r["categories"])[0] == main_cat:
            same.append(r["n"])
    category_avg = sum(same) / len(same) if same else 0

    sources = {}
    for r in source_rows:
        sources[r["source"]] = r["n"]
    visitors = {}
    for r in visitor_rows:
        visitors[r["kind"]] = r["n"]
    top_queries = []
    for r in query_rows:
        top_queries.append((r["query"], r["n"]))

    return {
        "daily": daily,
        "total_views": total_views,
        "likes": likes,
        "sources": sources,
        "visitors": visitors,
        "top_queries": top_queries,
        "main_category": main_cat,
        "category_avg": category_avg,
    }


def feedback_rules(stats):
    """지표에 따라 개선 방향 안내 문구(번역 키)를 고른다 (정해 둔 규칙)"""
    tips = []
    views = stats["total_views"]
    likes = stats["likes"]
    if views == 0:
        tips.append("tip_no_views")
    elif views >= 10 and likes / views < 0.05:
        tips.append("tip_low_like_rate")
    if stats["category_avg"] and views < stats["category_avg"] * 0.5:
        tips.append("tip_below_category")
    foreign = stats["visitors"].get("foreign", 0)
    domestic = stats["visitors"].get("domestic", 0)
    if foreign + domestic >= 5 and foreign > domestic:
        tips.append("tip_foreign_majority")
    return tips
