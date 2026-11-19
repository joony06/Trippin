# 데이터베이스 (SQLite, 파이썬 기본 sqlite3 모듈)
#
# 버전 기록
# v0.1 (2026-11-18) 테이블 생성(장소·회원·리뷰·찜·조회 기록), 샘플 데이터 적재, 조회·저장 함수 작성
# v0.2 (2026-11-18) 실제 데이터(data/places.json)가 있으면 샘플 대신 적재, 장소에 영문 이름·동·주소·사진·출처 열 추가
# v0.3 (2026-11-18) 대형 프랜차이즈 여부(is_franchise) 열 추가
# v0.4 (2026-11-19) 영문 설명문(description_en) 열 추가
#
# 저장 위치
# - 로컬: 프로젝트 폴더의 trippin.db (환경 변수 TRIPPIN_DB로 바꿀 수 있음)
# - Vercel: /tmp/trippin.db. 서버리스라 함수가 새로 뜨면 초기화된다 (시연용).
#   리뷰·회원을 계속 남기려면 다음 단계에서 Postgres(Neon)로 옮긴다.

import json
import os
import sqlite3
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(BASE_DIR, "data", "sample_places.json")
PLACES_PATH = os.path.join(BASE_DIR, "data", "places.json")  # build_places.py 결과

if os.environ.get("TRIPPIN_DB"):
    DB_PATH = os.environ["TRIPPIN_DB"]
elif os.environ.get("VERCEL") == "1":
    DB_PATH = "/tmp/trippin.db"
else:
    DB_PATH = os.path.join(BASE_DIR, "trippin.db")

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
    is_franchise INTEGER DEFAULT 0,      -- 대형 프랜차이즈 (하드 필터)
    google_rating REAL,
    google_reviews INTEGER,
    name_en TEXT,
    dong TEXT,
    address TEXT,
    image TEXT,
    source TEXT                        -- tour / sbiz / sample
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
    source TEXT NOT NULL,              -- list / map / direct
    query TEXT,                        -- 그때의 검색어
    created_at TEXT NOT NULL
);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset=False):
    """테이블을 만들고, 장소가 비어 있으면 샘플 데이터를 넣는다."""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    with connect() as conn:
        conn.executescript(SCHEMA)
        count = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        if count == 0:
            load_places(conn, PLACES_PATH if os.path.exists(PLACES_PATH) else SAMPLE_PATH)


def load_places(conn, path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for p in data["places"]:
        conn.execute(
            """INSERT OR REPLACE INTO places
               (id, name, categories, description, description_en, lat, lng, fee, hours,
                is_conglomerate, is_franchise, google_rating, google_reviews,
                name_en, dong, address, image, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (p["id"], p["name"], json.dumps(p["categories"], ensure_ascii=False),
             p.get("description"), p.get("description_en"), p["lat"], p["lng"], p.get("fee", 0),
             json.dumps(p.get("hours")) if p.get("hours") is not None else None,
             int(p.get("is_conglomerate", False)), int(p.get("is_franchise", False)),
             p.get("google_rating"),
             p.get("google_reviews"), p.get("name_en"), p.get("dong"), p.get("address"),
             p.get("image"), p.get("source", "sample")),
        )


# ---------------------------------------------------------------- 장소

def _place_from_row(row):
    p = dict(row)
    p["categories"] = json.loads(p["categories"])
    p["hours"] = json.loads(p["hours"]) if p["hours"] else None
    p["is_conglomerate"] = bool(p["is_conglomerate"])
    p["is_franchise"] = bool(p["is_franchise"])
    return p


def all_places_with_stats():
    """검색에 필요한 장소 정보 + 자체 리뷰 평균·개수 + 찜 수"""
    with connect() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      (SELECT AVG(rating) FROM reviews r WHERE r.place_id = p.id) AS own_avg,
                      (SELECT COUNT(*) FROM reviews r WHERE r.place_id = p.id) AS own_count,
                      (SELECT COUNT(*) FROM likes l WHERE l.place_id = p.id) AS likes
               FROM places p ORDER BY p.id"""
        ).fetchall()
    return [_place_from_row(r) for r in rows]


def get_place(place_id):
    return next((p for p in all_places_with_stats() if p["id"] == place_id), None)


def site_average():
    """사이트 전체 평균 별점 (S6의 C). 리뷰가 없으면 None"""
    with connect() as conn:
        v = conn.execute("SELECT AVG(rating) FROM reviews").fetchone()[0]
    return v


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
    """같은 점포에 다시 쓰면 수정으로 처리한다 (1인 1리뷰)."""
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
    return [dict(r) for r in rows]


def user_review(user_id, place_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM reviews WHERE user_id = ? AND place_id = ?", (user_id, place_id)
        ).fetchone()
    return dict(row) if row else None


def toggle_like(user_id, place_id):
    """찜이 있으면 지우고 없으면 넣는다. 결과로 찜 상태(True/False)를 돌려준다."""
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND place_id = ?", (user_id, place_id)
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM likes WHERE user_id = ? AND place_id = ?", (user_id, place_id))
            return False
        conn.execute("INSERT INTO likes (user_id, place_id, created_at) VALUES (?, ?, ?)",
                     (user_id, place_id, now()))
        return True


def has_liked(user_id, place_id):
    with connect() as conn:
        return conn.execute(
            "SELECT 1 FROM likes WHERE user_id = ? AND place_id = ?", (user_id, place_id)
        ).fetchone() is not None


# ---------------------------------------------------------------- 조회 기록·대시보드 집계

def log_view(place_id, user_id, source, query):
    with connect() as conn:
        conn.execute(
            "INSERT INTO views (place_id, user_id, source, query, created_at) VALUES (?, ?, ?, ?, ?)",
            (place_id, user_id, source, query or None, now()),
        )


def dashboard_stats(place_id, days=7):
    """사업자 대시보드 지표: 일별 조회수, 찜 수, 유입 경로, 내·외국인 비율, 많이 걸린 검색어, 업종 평균 대비"""
    since = (datetime.now() - timedelta(days=days - 1)).date().isoformat()
    with connect() as conn:
        daily_rows = conn.execute(
            """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS n FROM views
               WHERE place_id = ? AND substr(created_at, 1, 10) >= ? GROUP BY day""",
            (place_id, since),
        ).fetchall()
        sources = conn.execute(
            "SELECT source, COUNT(*) AS n FROM views WHERE place_id = ? GROUP BY source",
            (place_id,),
        ).fetchall()
        visitors = conn.execute(
            """SELECT CASE WHEN u.nationality = 'KR' THEN 'domestic' ELSE 'foreign' END AS kind,
                      COUNT(*) AS n
               FROM views v JOIN users u ON u.id = v.user_id
               WHERE v.place_id = ? GROUP BY kind""",
            (place_id,),
        ).fetchall()
        queries = conn.execute(
            """SELECT query, COUNT(*) AS n FROM views
               WHERE place_id = ? AND query IS NOT NULL GROUP BY query ORDER BY n DESC LIMIT 5""",
            (place_id,),
        ).fetchall()
        total_views = conn.execute(
            "SELECT COUNT(*) FROM views WHERE place_id = ?", (place_id,)
        ).fetchone()[0]
        likes = conn.execute(
            "SELECT COUNT(*) FROM likes WHERE place_id = ?", (place_id,)
        ).fetchone()[0]
        per_place = conn.execute(
            """SELECT p.id, p.categories, (SELECT COUNT(*) FROM views v WHERE v.place_id = p.id) AS n
               FROM places p"""
        ).fetchall()

    by_day = {r["day"]: r["n"] for r in daily_rows}
    daily = []
    for i in range(days):
        d = (datetime.now() - timedelta(days=days - 1 - i)).date().isoformat()
        daily.append({"day": d, "n": by_day.get(d, 0)})

    # 같은 업종(대표 카테고리) 평균 조회수
    mine = next(r for r in per_place if r["id"] == place_id)
    main_cat = json.loads(mine["categories"])[0]
    same = [r["n"] for r in per_place if json.loads(r["categories"])[0] == main_cat]
    category_avg = sum(same) / len(same) if same else 0

    return {
        "daily": daily,
        "total_views": total_views,
        "likes": likes,
        "sources": {r["source"]: r["n"] for r in sources},
        "visitors": {r["kind"]: r["n"] for r in visitors},
        "top_queries": [(r["query"], r["n"]) for r in queries],
        "main_category": main_cat,
        "category_avg": category_avg,
    }


def feedback_rules(stats):
    """지표에 따른 개선 방향 안내 (정해 둔 규칙)"""
    tips = []
    views, likes = stats["total_views"], stats["likes"]
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
