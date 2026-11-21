# 트립핀(Trippin) - Flask 진입 파일 (화면 라우트)
#
# 버전 기록
# v0.1 (2026-11-18) Vercel 배포 확인용 최소 Flask 앱 생성 (메인 페이지 + 상태 확인 경로)
# v0.2 (2026-11-18) 로고·파비콘 적용, 로컬 실행 시 public/ 폴더를 정적 파일로 제공 (Vercel에서는 CDN이 제공)
# v0.3 (2026-11-18) Vercel 빌드 실패 수정: app = Flask(...) 를 if 문 밖 최상위 한 줄로 정의
# v0.4 (2026-11-18) MVP 뼈대: 필터링 검색·장소 상세(점수표)·리뷰·찜·회원가입/로그인·사업자 대시보드·다국어 연결
# v0.5 (2026-11-18) 실제 데이터(수천 곳) 대응: 결과 목록·지도는 상위 30곳만, 첫 화면 지도는 관광공사 등록 장소만 표시
# v0.6 (2026-11-18) 첫 화면 지도·사업자 가게 선택에서 대형 프랜차이즈도 제외
# v0.7 (2026-11-19) 현재 위치 반영: 검색 폼의 숨은 칸 lat·lng → 출발점 (중구 밖·거부 시 기본 위치), 지도에 출발점 전달
# v0.8 (2026-11-19) 네이버 지도: 환경 변수 NAVER_MAP_CLIENT_ID를 템플릿에 내려줌 (없으면 지도는 OSM으로 자동 전환)
# v0.9 (2026-11-19) 결과 화면: 동네별 개수 요약·동네 필터(dong, 결과 목록에서 거름)·카테고리 칩(조건 유지하고 카테고리만 바꿔 재검색)
# v0.10 (2026-11-21) 사용자 테스트 반영: 사업자는 자기 가게에 리뷰·찜 불가(5번), 사업자 본인 조회 제외·같은 사람 같은 날 조회는 1회(6번),
#                    로그인 안 한 채 찜 → 로그인 후 보던 가게로 돌아오고 찜 처리(7번), 사업자 가입 가게 목록 가나다순, 지도 이름 외국어 화면은 영문
# v0.11 (2026-11-21) 검색어가 카테고리 이름(카페, cafe, 咖啡馆 등 4개 언어)이면 그 카테고리로 바꿔 검색 (검색어 칸에 '카페'를 쓰면 이름에 '카페'가 든 식당이 위에 오던 문제)
# v0.12 (2026-11-21) 영어·중국어·일본어 화면: 영문 이름이 없는 가게·동네는 로마자로 표시 (place_name, dong_name)

import os
import re
from datetime import datetime
from collections import Counter
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
from core.geo import resolve_origin
from core.i18n import DEFAULT_LANG, LANGS, translate
from core.romanize import romanize, romanize_dong
from core.reviews import DEFAULT_SITE_AVG, summarize
from core.search import WEIGHTS, Conditions, search

# Vercel에서는 public/** 를 CDN이 직접 제공하므로 Flask 정적 폴더를 쓰지 않는다.
# 로컬(flask run)에서만 public/ 를 루트 경로(/style.css 등)로 제공해 배포 환경과 주소를 맞춘다.
ON_VERCEL = os.environ.get("VERCEL") == "1"

app = Flask(
    __name__,
    static_folder=None if ON_VERCEL else "public",
    static_url_path="",
)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret")

# 네이버 지도 Client ID (환경 변수로만 받는다. 비어 있으면 지도는 Leaflet + OpenStreetMap)
NAVER_MAP_CLIENT_ID = (os.environ.get("NAVER_MAP_CLIENT_ID") or "").strip() or None

CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]
DISTANCE_OPTIONS = [1, 2, 5, 10]
BUDGET_OPTIONS = [0, 5000, 10000, 20000]
RESULT_LIMIT = 30  # 결과 목록·지도에 보여 줄 최대 개수 (점수 계산은 전체 대상)
NATIONALITIES = ["KR", "US", "CN", "JP", "TW", "VN", "TH", "PH", "ID", "OTHER"]

db.init_db()


# ---------------------------------------------------------------- 공통

@app.before_request
def load_context():
    g.lang = session.get("lang", DEFAULT_LANG)
    uid = session.get("user_id")
    g.user = db.get_user(uid) if uid else None


@app.context_processor
def inject_helpers():
    def t(key, **kwargs):
        return translate(g.lang, key, **kwargs)

    # 출발점은 모든 화면(검색 폼 문구·지도 출발점 표시)에서 같은 값을 쓴다
    origin, origin_state = resolve_origin(request.args.get("lat"), request.args.get("lng"))
    def place_name(p):
        """한국어 화면은 한글 이름, 다른 언어는 영문 이름 → 없으면 로마자"""
        if g.lang == "ko":
            return p["name"]
        return p.get("name_en") or romanize(p["name"])

    def dong_name(d):
        return d if g.lang == "ko" else romanize_dong(d)

    return {"t": t, "lang": g.lang, "LANGS": LANGS, "user": g.user, "place_name": place_name, "dong_name": dong_name,
            "CATEGORIES": CATEGORIES, "WEIGHTS": WEIGHTS,
            "origin": origin, "origin_state": origin_state,
            "naver_map_client_id": NAVER_MAP_CLIENT_ID}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if request.method == "POST":
                # 폼(리뷰·찜)에서 왔으면 로그인 후 보던 화면으로 돌아간다. 찜은 로그인 후 이어서 처리
                back = request.form.get("next") or ""
                if not back.startswith("/") or back.startswith("//"):
                    back = url_for("index")
                if view.__name__ == "like" and "place_id" in kwargs:
                    session["pending_like"] = kwargs["place_id"]
                return redirect(url_for("login", next=back))
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


# 검색어 칸에 카테고리 이름을 쓰면 카테고리로 찾는다. 4개 언어 번역 + 자주 쓰는 다른 말
CATEGORY_WORDS = {"카페": ["커피", "coffee", "cafe", "cafes", "café", "咖啡", "コーヒー"],
                  "음식": ["맛집", "식당", "음식점", "restaurant", "restaurants", "food", "餐厅", "レストラン"],
                  "야경": ["night view", "nightview", "night"], "자연": ["공원", "park", "parks"],
                  "쇼핑": ["shopping", "shop"], "역사": ["history", "historic"]}


def category_from_query(q):
    """검색어가 카테고리 이름과 같으면 그 카테고리 (대소문자·앞뒤 공백 무시). 아니면 None"""
    word = (q or "").strip().lower()
    if not word:
        return None
    for c in CATEGORIES:
        names = {c} | {translate(lang, "cat_" + c).lower() for lang in LANGS} | set(CATEGORY_WORDS.get(c, []))
        if word in names:
            return c
    return None


def parse_conditions(args):
    """주소창 파라미터(request.args)에서 검색 조건을 읽는다."""
    def to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    budget = to_int(args.get("budget"))
    day = to_int(args.get("day"))
    dist = to_int(args.get("dist")) or 5
    # 브라우저 위치(숨은 칸 lat, lng). 대전 중구 밖이거나 없으면 기본 위치(대전 중구청 앞)
    origin, _state = resolve_origin(args.get("lat"), args.get("lng"))
    categories = [c for c in args.getlist("cat") if c in CATEGORIES]
    query = (args.get("q") or "").strip()
    as_cat = category_from_query(query)
    g.query_as_category = None
    if as_cat:
        # '카페'처럼 카테고리 이름이면 검색어 대신 카테고리로 찾는다 (화면에 안내)
        g.query_as_category = query
        query = ""
        if as_cat not in categories:
            categories.append(as_cat)
    return Conditions(
        categories=categories,
        query=query,
        max_km=float(dist),
        budget=budget,
        day=day if day is not None and 0 <= day <= 6 else None,
        time=args.get("time") if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", args.get("time") or "") else None,
        origin=origin,
    )


def parse_dong(args):
    """동네 필터(dong 파라미터). 검색 로직(core/search.py)은 그대로 두고, 순위가 정해진 결과 목록에서만 거른다."""
    return (args.get("dong") or "").strip() or None


def dong_counts(ranked):
    """결과 목록의 동네별 개수 (많은 순). 동네 정보가 없는 곳은 세지 않는다."""
    return Counter(p["dong"] for p in ranked if p.get("dong")).most_common()


def search_url(args, **changes):
    """지금 검색 조건(args)에서 일부만 바꾼 검색 주소. 값이 None이면 그 조건을 뺀다."""
    out = {k: v for k, v in args.items() if k not in changes}
    out.update({k: v for k, v in changes.items() if v is not None})
    return url_for("search_view", **out)


def search_args():
    """결과 → 상세로 넘어갈 때 검색 조건을 그대로 넘기기 위한 값"""
    keys = ["q", "dist", "budget", "day", "time", "lat", "lng", "dong"]
    out = {k: request.args.get(k) for k in keys if request.args.get(k)}
    if request.args.getlist("cat"):
        out["cat"] = request.args.getlist("cat")
    return out


def map_points(items, src):
    use_en = getattr(g, "lang", DEFAULT_LANG) != "ko"
    return [{"id": p["id"], "name": ((p.get("name_en") or romanize(p["name"])) if use_en else p["name"]),
             "lat": p["lat"], "lng": p["lng"],
             "rank": p.get("rank"), "src": src} for p in items]


# ---------------------------------------------------------------- 검색

@app.route("/")
def index():
    places = [p for p in db.all_places_with_stats() if not p["is_conglomerate"] and not p.get("is_franchise")]
    # 상가정보 점포까지 다 찍으면 수천 개라, 첫 화면은 관광공사 등록 장소(또는 샘플)만 보여 준다
    landmarks = [p for p in places if p.get("source") != "sbiz"]
    places = landmarks or places
    return render_template("index.html", points=map_points(places, "map"),
                           distance_options=DISTANCE_OPTIONS, budget_options=BUDGET_OPTIONS,
                           cond=Conditions())


@app.route("/search")
def search_view():
    cond = parse_conditions(request.args)
    ranked, excluded = search(db.all_places_with_stats(), cond, site_avg=db.site_average())
    args = search_args()

    # 동네별 요약은 동네로 거르기 전 전체 결과 기준 (다른 동네로 바로 옮겨 갈 수 있게)
    dong = parse_dong(request.args)
    dong_links = [(d, n, search_url(args, dong=d)) for d, n in dong_counts(ranked)]
    if dong:
        # 순위·다양성 보정은 전체 결과 기준 그대로 두고 그 동네만 남긴다 (순위 번호도 전체 기준)
        ranked = [p for p in ranked if p.get("dong") == dong]

    # 카테고리 칩: 다른 조건은 그대로 두고 카테고리만 하나로 바꿔 다시 검색
    cat_links = [(c, search_url(args, cat=[c])) for c in CATEGORIES]

    shown = ranked[:RESULT_LIMIT]
    return render_template("results.html", cond=cond, ranked=shown, total=len(ranked),
                           excluded=excluded, points=map_points(shown, "map"), args=args,
                           dong=dong, dong_links=dong_links, dong_all_url=search_url(args, dong=None),
                           cat_links=cat_links, cat_all_url=search_url(args, cat=None),
                           distance_options=DISTANCE_OPTIONS, budget_options=BUDGET_OPTIONS)


# ---------------------------------------------------------------- 장소 상세·리뷰·찜

@app.route("/place/<int:place_id>")
def place_detail(place_id):
    place = db.get_place(place_id)
    if place is None:
        abort(404)

    args = search_args()
    src = request.args.get("src", "direct")
    if src not in ("list", "map", "direct"):
        src = "direct"
    if should_log_view(place_id):
        db.log_view(place_id, g.user["id"] if g.user else None, src, request.args.get("q"))

    # 검색에서 넘어왔으면 같은 조건으로 다시 계산해 점수표를 보여 준다
    scored, excluded_reasons = None, None
    if args:
        cond = parse_conditions(request.args)
        ranked, excluded = search(db.all_places_with_stats(), cond, site_avg=db.site_average())
        scored = next((p for p in ranked if p["id"] == place_id), None)
        excluded_reasons = next((r for p, r in excluded if p["id"] == place_id), None)

    reviews = db.reviews_for_place(place_id)
    site_avg = db.site_average() or DEFAULT_SITE_AVG
    summary = summarize([r["rating"] for r in reviews], site_avg=site_avg)
    mine = db.user_review(g.user["id"], place_id) if g.user else None
    liked = db.has_liked(g.user["id"], place_id) if g.user else False

    return render_template("place.html", place=place, scored=scored,
                           excluded_reasons=excluded_reasons, args=args, reviews=reviews,
                           summary=summary, mine=mine, liked=liked, own_place=is_own_place(place_id),
                           points=map_points([place], "map"))


def is_own_place(place_id):
    """사업자가 자기 가게를 보고 있는지 (자기 가게에는 리뷰·찜을 못 하고, 조회수에도 넣지 않는다)"""
    return bool(g.user and g.user["role"] == "owner" and g.user["owner_place_id"] == place_id)


def should_log_view(place_id):
    """같은 사람(같은 브라우저)이 같은 날 다시 본 것은 세지 않는다. 사업자 본인 조회도 뺀다."""
    if is_own_place(place_id):
        return False
    key = f"{place_id}:{datetime.now().date().isoformat()}"
    seen = session.get("viewed", [])
    if key in seen:
        return False
    session["viewed"] = (seen + [key])[-100:]  # 쿠키가 커지지 않게 최근 100개만
    return True


def back_to_place(place_id):
    # 리뷰·찜 후 원래 보던 상세 화면(검색 조건 포함)으로 돌아간다
    target = request.form.get("next") or ""
    if target.startswith("/place/"):
        return redirect(target)
    return redirect(url_for("place_detail", place_id=place_id))


@app.post("/place/<int:place_id>/review")
@login_required
def write_review(place_id):
    if db.get_place(place_id) is None:
        abort(404)
    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0
    if 1 <= rating <= 5 and not is_own_place(place_id):
        db.upsert_review(g.user["id"], place_id, rating, (request.form.get("body") or "").strip()[:500])
    return back_to_place(place_id)


@app.post("/place/<int:place_id>/like")
@login_required
def like(place_id):
    if db.get_place(place_id) is None:
        abort(404)
    if not is_own_place(place_id):
        db.toggle_like(g.user["id"], place_id)
    return back_to_place(place_id)


# ---------------------------------------------------------------- 회원

@app.route("/signup", methods=["GET", "POST"])
def signup():
    places = sorted((p for p in db.all_places_with_stats() if not p["is_conglomerate"] and not p.get("is_franchise")),
                    key=lambda p: p["name"])  # 가나다순
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        nationality = request.form.get("nationality") or "KR"
        role = "owner" if request.form.get("role") == "owner" else "tourist"
        owner_place = request.form.get("owner_place_id")
        owner_place_id = int(owner_place) if role == "owner" and owner_place else None

        if len(username) < 3 or len(password) < 6:
            error = "err_fields"
        elif role == "owner" and owner_place_id is None:
            error = "err_owner_place"
        elif db.get_user_by_name(username):
            error = "err_exists"
        else:
            uid = db.create_user(username, generate_password_hash(password),
                                 nationality if nationality in NATIONALITIES else "OTHER",
                                 role, owner_place_id)
            session.clear()
            session["user_id"] = uid
            session["lang"] = g.lang
            return redirect(url_for("index"))
    return render_template("signup.html", error=error, places=places, nationalities=NATIONALITIES)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = db.get_user_by_name((request.form.get("username") or "").strip())
        if user and check_password_hash(user["pw_hash"], request.form.get("password") or ""):
            lang = g.lang
            pending = session.get("pending_like")
            session.clear()
            session["user_id"] = user["id"]
            session["lang"] = lang
            # 로그인 전에 누른 찜을 이어서 처리 (이미 찜했거나 자기 가게면 그대로 둔다)
            if pending and db.get_place(pending) and not db.has_liked(user["id"], pending) \
                    and not (user["role"] == "owner" and user["owner_place_id"] == pending):
                db.toggle_like(user["id"], pending)
            target = request.args.get("next") or ""
            return redirect(target if target.startswith("/") and not target.startswith("//")
                            else url_for("index"))
        error = "err_login"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    lang = g.lang
    session.clear()
    session["lang"] = lang
    return redirect(url_for("index"))


# ---------------------------------------------------------------- 사업자 대시보드

@app.route("/dashboard")
@login_required
def dashboard():
    if g.user["role"] != "owner" or not g.user["owner_place_id"]:
        return render_template("dashboard.html", place=None, stats=None, tips=[]), 403
    place = db.get_place(g.user["owner_place_id"])
    stats = db.dashboard_stats(place["id"])
    tips = db.feedback_rules(stats) or ["tip_ok"]
    return render_template("dashboard.html", place=place, stats=stats, tips=tips)


# ---------------------------------------------------------------- 언어·상태

@app.route("/lang/<code>")
def set_lang(code):
    if code in LANGS:
        session["lang"] = code
    target = request.referrer or url_for("index")
    return redirect(target)


@app.cli.command("init-db")
def init_db_command():
    """DB를 지우고 샘플 데이터로 다시 만든다: flask --app app init-db"""
    db.init_db(reset=True)
    print(f"DB 초기화 완료: {db.DB_PATH}")


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True)
