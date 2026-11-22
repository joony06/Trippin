# 트립핀 실행 파일: 화면 주소(라우트)별 처리
#
# 버전 기록
# v0.1 Vercel 배포용 최소 Flask 앱
# v0.2 로고·파비콘, 로컬에서 public/ 제공
# v0.3 Vercel 빌드 오류 수정
# v0.4 검색·상세·리뷰·찜·회원·대시보드·다국어 연결
# v0.5 결과·지도는 상위 30곳, 첫 화면은 관광공사 장소만
# v0.6 대형 프랜차이즈 제외
# v0.7 현재 위치를 출발점으로
# v0.8 네이버 지도 키 전달 (없으면 OSM)
# v0.9 동네별 요약·동네 필터·카테고리 칩
# v0.10 사업자 자기 가게 리뷰·찜 금지, 같은 날 조회 1회, 로그인 전 찜 유지
# v0.11 카테고리 이름 검색어는 카테고리로 검색
# v0.12 외국어 화면에서 가게·동네 이름 로마자 표시
# v0.13 로그인·로그아웃 때 조회 기록 유지 (김가연)
# v0.14 python app.py로 실행, 빈 포트 자동 선택
#
# 실행: python app.py

import os
import socket
import webbrowser
from datetime import datetime

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import database
import search
import texts


# Vercel에서는 public/를 CDN이 제공
ON_VERCEL = os.environ.get("VERCEL") == "1"

if ON_VERCEL:
    STATIC_FOLDER = None
else:
    STATIC_FOLDER = "public"
app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret")

# 없으면 OpenStreetMap
NAVER_MAP_CLIENT_ID = (os.environ.get("NAVER_MAP_CLIENT_ID") or "").strip() or None

CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]
DISTANCE_OPTIONS = [1, 2, 5, 10]       # km
BUDGET_OPTIONS = [0, 5000, 10000, 20000]  # 원
RESULT_LIMIT = 30
NATIONALITIES = ["KR", "US", "CN", "JP", "TW", "VN", "TH", "PH", "ID", "OTHER"]
SEARCH_KEYS = ["q", "dist", "budget", "day", "time", "lat", "lng", "dong"]

# 검색어가 카테고리 이름이면 카테고리로 검색
CATEGORY_WORDS = {"카페": ["커피", "coffee", "cafe", "cafes", "café", "咖啡", "コーヒー"],
                  "음식": ["맛집", "식당", "음식점", "restaurant", "restaurants", "food", "餐厅", "レストラン"],
                  "야경": ["night view", "nightview", "night"], "자연": ["공원", "park", "parks"],
                  "쇼핑": ["shopping", "shop"], "역사": ["history", "historic"]}

database.init_db()


@app.before_request
def load_context():
    g.lang = session.get("lang", texts.DEFAULT_LANG)
    uid = session.get("user_id")
    if uid:
        g.user = database.get_user(uid)
    else:
        g.user = None


def t(key, **values):
    return texts.translate(g.lang, key, **values)


def place_name(p):
    if g.lang == "ko":
        return p["name"]
    return p.get("name_en") or texts.romanize(p["name"])


def dong_name(d):
    if g.lang == "ko":
        return d
    return texts.romanize_dong(d)


@app.context_processor
def inject_helpers():
    origin, origin_state = search.resolve_origin(request.args.get("lat"), request.args.get("lng"))
    return {"t": t, "lang": g.lang, "LANGS": texts.LANGS, "user": g.user,
            "place_name": place_name, "dong_name": dong_name,
            "CATEGORIES": CATEGORIES, "WEIGHTS": search.WEIGHTS,
            "origin": origin, "origin_state": origin_state,
            "naver_map_client_id": NAVER_MAP_CLIENT_ID}


def safe_next(target):
    """로그인 후 이동 주소는 사이트 내부만 허용 ('//'는 외부 사이트)"""
    return target.startswith("/") and not target.startswith("//")


def login_redirect(like_place_id=None):
    if g.user is not None:
        return None
    if request.method == "POST":
        back = request.form.get("next") or ""
        if not safe_next(back):
            back = url_for("index")
        if like_place_id is not None:
            session["pending_like"] = like_place_id
        return redirect(url_for("login", next=back))
    return redirect(url_for("login", next=request.path))


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def valid_time(text):
    if len(text) != 5 or text[2] != ":":
        return False
    h1, h2, m1, m2 = text[0], text[1], text[3], text[4]
    if not (h2.isdecimal() and m2.isdecimal()):
        return False
    hour_ok = h1 in "01" or (h1 == "2" and h2 in "0123")
    return hour_ok and m1 in "012345"


def category_from_query(q):
    word = (q or "").strip().lower()
    if not word:
        return None
    for c in CATEGORIES:
        names = {c}
        for lang in texts.LANGS:
            names.add(texts.translate(lang, "cat_" + c).lower())
        for other in CATEGORY_WORDS.get(c, []):
            names.add(other)
        if word in names:
            return c
    return None


def parse_conditions(args):
    budget = to_int(args.get("budget"))
    day = to_int(args.get("day"))
    if day is not None and not (0 <= day <= 6):
        day = None
    dist = to_int(args.get("dist")) or 5
    time = args.get("time") or ""
    if not valid_time(time):
        time = None
    origin, _state = search.resolve_origin(args.get("lat"), args.get("lng"))

    categories = []
    for c in args.getlist("cat"):
        if c in CATEGORIES:
            categories.append(c)
    query = (args.get("q") or "").strip()
    as_cat = category_from_query(query)
    g.query_as_category = None
    if as_cat:
        g.query_as_category = query
        query = ""
        if as_cat not in categories:
            categories.append(as_cat)
    return search.Conditions(categories=categories, query=query, max_km=float(dist), budget=budget,
                             day=day, time=time, origin=origin)


def search_args():
    out = {}
    for k in SEARCH_KEYS:
        if request.args.get(k):
            out[k] = request.args.get(k)
    if request.args.getlist("cat"):
        out["cat"] = request.args.getlist("cat")
    return out


def search_url(args, changes):
    out = {}
    for k in args:
        if k not in changes:
            out[k] = args[k]
    for k in changes:
        if changes[k] is not None:
            out[k] = changes[k]
    return url_for("search_view", **out)


def dong_counts(ranked):
    counts = {}
    for p in ranked:
        if p.get("dong"):
            counts[p["dong"]] = counts.get(p["dong"], 0) + 1
    pairs = list(counts.items())
    pairs.sort(key=pair_count, reverse=True)
    return pairs


def pair_count(pair):
    return pair[1]


def map_points(items, src):
    points = []
    for p in items:
        points.append({"id": p["id"], "name": place_name(p), "lat": p["lat"], "lng": p["lng"],
                       "rank": p.get("rank"), "src": src})
    return points


def local_places():
    out = []
    for p in database.all_places_with_stats():
        if not p["is_conglomerate"] and not p.get("is_franchise"):
            out.append(p)
    return out


def run_search_with(args):
    cond = parse_conditions(args)
    ranked, excluded = search.run_search(database.all_places_with_stats(), cond, site_avg=database.site_average())
    return cond, ranked, excluded


@app.route("/")
def index():
    places = local_places()
    # 첫 화면은 관광공사 장소만
    landmarks = []
    for p in places:
        if p.get("source") != "sbiz":
            landmarks.append(p)
    if landmarks:
        places = landmarks
    return render_template("index.html", points=map_points(places, "map"),
                           distance_options=DISTANCE_OPTIONS, budget_options=BUDGET_OPTIONS,
                           cond=search.Conditions())


@app.route("/search")
def search_view():
    cond, ranked, excluded = run_search_with(request.args)
    args = search_args()

    dong = (request.args.get("dong") or "").strip() or None
    dong_links = []
    for d, n in dong_counts(ranked):
        dong_links.append((d, n, search_url(args, {"dong": d})))
    if dong:
        # 순위는 전체 기준 유지
        in_dong = []
        for p in ranked:
            if p.get("dong") == dong:
                in_dong.append(p)
        ranked = in_dong

    cat_links = []
    for c in CATEGORIES:
        cat_links.append((c, search_url(args, {"cat": [c]})))

    shown = ranked[:RESULT_LIMIT]
    return render_template("results.html", cond=cond, ranked=shown, total=len(ranked),
                           excluded=excluded, points=map_points(shown, "map"), args=args,
                           dong=dong, dong_links=dong_links, dong_all_url=search_url(args, {"dong": None}),
                           cat_links=cat_links, cat_all_url=search_url(args, {"cat": None}),
                           distance_options=DISTANCE_OPTIONS, budget_options=BUDGET_OPTIONS)


def is_own_place(place_id):
    return bool(g.user and g.user["role"] == "owner" and g.user["owner_place_id"] == place_id)


def should_log_view(place_id):
    """같은 브라우저의 같은 날 재조회는 제외"""
    if is_own_place(place_id):
        return False
    key = str(place_id) + ":" + datetime.now().date().isoformat()
    seen = session.get("viewed", [])
    if key in seen:
        return False
    session["viewed"] = (seen + [key])[-100:]
    return True


@app.route("/place/<int:place_id>")
def place_detail(place_id):
    place = database.get_place(place_id)
    if place is None:
        abort(404)

    args = search_args()
    src = request.args.get("src", "direct")
    if src not in ("list", "map", "direct"):
        src = "direct"
    if should_log_view(place_id):
        viewer_id = None
        if g.user:
            viewer_id = g.user["id"]
        database.log_view(place_id, viewer_id, src, request.args.get("q"))

    # 검색에서 온 경우 점수표 재계산
    scored = None
    excluded_reasons = None
    if args:
        _cond, ranked, excluded = run_search_with(request.args)
        for p in ranked:
            if p["id"] == place_id:
                scored = p
                break
        for p, reasons in excluded:
            if p["id"] == place_id:
                excluded_reasons = reasons
                break

    reviews = database.reviews_for_place(place_id)
    ratings = []
    for r in reviews:
        ratings.append(r["rating"])
    summary = search.summarize(ratings, site_avg=database.site_average() or search.DEFAULT_SITE_AVG)
    if g.user:
        mine = database.user_review(g.user["id"], place_id)
    else:
        mine = None
    if g.user:
        liked = database.has_liked(g.user["id"], place_id)
    else:
        liked = False

    return render_template("place.html", place=place, scored=scored,
                           excluded_reasons=excluded_reasons, args=args, reviews=reviews,
                           summary=summary, mine=mine, liked=liked, own_place=is_own_place(place_id),
                           points=map_points([place], "map"))


def back_to_place(place_id):
    target = request.form.get("next") or ""
    if target.startswith("/place/"):
        return redirect(target)
    return redirect(url_for("place_detail", place_id=place_id))


@app.post("/place/<int:place_id>/review")
def write_review(place_id):
    need_login = login_redirect()
    if need_login:
        return need_login
    if database.get_place(place_id) is None:
        abort(404)
    rating = to_int(request.form.get("rating", 0)) or 0
    if 1 <= rating <= 5 and not is_own_place(place_id):
        body = (request.form.get("body") or "").strip()[:500]
        database.upsert_review(g.user["id"], place_id, rating, body)
    return back_to_place(place_id)


@app.post("/place/<int:place_id>/like")
def like(place_id):
    need_login = login_redirect(like_place_id=place_id)
    if need_login:
        return need_login
    if database.get_place(place_id) is None:
        abort(404)
    if not is_own_place(place_id):
        database.toggle_like(g.user["id"], place_id)
    return back_to_place(place_id)


def reset_session(user_id=None):
    lang = g.lang
    viewed = session.get("viewed", [])
    session.clear()
    session["lang"] = lang
    if viewed:
        session["viewed"] = viewed
    if user_id is not None:
        session["user_id"] = user_id


def place_name_key(p):
    return p["name"]


@app.route("/signup", methods=["GET", "POST"])
def signup():
    places = sorted(local_places(), key=place_name_key)
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        nationality = request.form.get("nationality") or "KR"
        if nationality not in NATIONALITIES:
            nationality = "OTHER"
        if request.form.get("role") == "owner":
            role = "owner"
        else:
            role = "tourist"
        owner_place = request.form.get("owner_place_id")
        if role == "owner" and owner_place:
            owner_place_id = int(owner_place)
        else:
            owner_place_id = None

        if len(username) < 3 or len(password) < 6:
            error = "err_fields"
        elif role == "owner" and owner_place_id is None:
            error = "err_owner_place"
        elif database.get_user_by_name(username):
            error = "err_exists"
        else:
            uid = database.create_user(username, generate_password_hash(password), nationality, role, owner_place_id)
            reset_session(uid)
            return redirect(url_for("index"))
    return render_template("signup.html", error=error, places=places, nationalities=NATIONALITIES)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        user = database.get_user_by_name((request.form.get("username") or "").strip())
        if user and check_password_hash(user["pw_hash"], request.form.get("password") or ""):
            pending = session.get("pending_like")
            reset_session(user["id"])
            # 로그인 전에 누른 찜 처리
            own = user["role"] == "owner" and user["owner_place_id"] == pending
            if pending and database.get_place(pending) and not database.has_liked(user["id"], pending) and not own:
                database.toggle_like(user["id"], pending)
            target = request.args.get("next") or ""
            if safe_next(target):
                return redirect(target)
            return redirect(url_for("index"))
        error = "err_login"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    reset_session()
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    need_login = login_redirect()
    if need_login:
        return need_login
    if g.user["role"] != "owner" or not g.user["owner_place_id"]:
        return render_template("dashboard.html", place=None, stats=None, tips=[]), 403
    place = database.get_place(g.user["owner_place_id"])
    stats = database.dashboard_stats(place["id"])
    tips = database.feedback_rules(stats) or ["tip_ok"]
    return render_template("dashboard.html", place=place, stats=stats, tips=tips)


@app.route("/lang/<code>")
def set_lang(code):
    if code in texts.LANGS:
        session["lang"] = code
    return redirect(request.referrer or url_for("index"))


@app.route("/health")
def health():
    return {"status": "ok"}


@app.cli.command("init-db")
def init_db_command():
    """DB 초기화: flask --app app init-db"""
    database.init_db(reset=True)
    print("DB 초기화 완료:", database.DB_PATH)


def free_port(start):
    for port in range(start, start + 20):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
        finally:
            sock.close()
    return start


def choose_port():
    fixed = int(os.environ.get("PORT") or os.environ.get("TRIPPIN_PORT") or 0)
    if fixed:
        return fixed
    if os.environ.get("TRIPPIN_RUN_PORT"):
        return int(os.environ["TRIPPIN_RUN_PORT"])
    return free_port(5000)


if __name__ == "__main__":
    port = choose_port()
    os.environ["TRIPPIN_RUN_PORT"] = str(port)
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":  # 재시작 시 브라우저 중복 열림 방지
        print(f"트립핀 실행 중: http://127.0.0.1:{port}  (끄려면 Ctrl+C)")
        webbrowser.open(f"http://127.0.0.1:{port}")
    app.run(debug=True, port=port)
