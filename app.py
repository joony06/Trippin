# 트립핀(Trippin) - 실행 파일. 웹 화면의 주소(라우트)마다 무엇을 보여 줄지 정한다 (Flask, 10주차 라이브러리)
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
# v0.9 (2026-11-19) 결과 화면: 동네별 개수 요약·동네 필터·카테고리 칩(조건 유지하고 카테고리만 바꿔 재검색)
# v0.10 (2026-11-21) 사용자 테스트 반영: 사업자는 자기 가게에 리뷰·찜 불가, 사업자 본인 조회 제외·같은 사람 같은 날 조회는 1회,
#                    로그인 안 한 채 찜 → 로그인 후 보던 가게로 돌아오고 찜 처리, 사업자 가입 가게 목록 가나다순, 지도 이름 외국어 화면은 영문
# v0.11 (2026-11-21) 검색어가 카테고리 이름(카페, cafe, 咖啡馆 등 4개 언어)이면 그 카테고리로 바꿔 검색
# v0.12 (2026-11-21) 영어·중국어·일본어 화면: 영문 이름이 없는 가게·동네는 로마자로 표시
# v0.13 (2026-11-22) 로그인·로그아웃·가입 때 "오늘 본 가게" 기록을 지우지 않음 (김가연)
# v0.14 (2026-11-22) `python app.py`로 바로 실행: 주소 안내·브라우저 자동 열기, 5000번이 쓰이면 비어 있는 다음 포트 사용
# v0.15 (2026-11-22) 수업 수준으로 다시 정리 (화면·기능은 v0.14와 같음)
#                    - 계산은 search.py, 저장은 database.py, 화면 글자는 texts.py로 나눔 (2주차 분해, 10주차 사용자 정의 모듈)
#                    - 직접 만든 데코레이터(@login_required) 대신 함수 login_redirect()를 화면마다 먼저 부름
#                    - 정규식·lambda·Counter 대신 if 문과 for 반복문 (6·7주차)
#
# 실행 방법: 이 파일을 VS Code에서 실행(▶)하거나, 터미널에서  python app.py
#           브라우저가 자동으로 열린다. 처음 실행하면 trippin.db 가 만들어진다.

import os
import socket
import webbrowser
from datetime import datetime

from flask import Flask, abort, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import database
import search
import texts

# ---------------------------------------------------------------- 설정·상수

# Vercel에서는 public/ 폴더를 CDN이 직접 제공하므로 Flask가 제공하지 않는다.
# 내 컴퓨터에서는 public/ 를 /style.css 같은 주소로 제공해 배포 환경과 주소를 맞춘다.
ON_VERCEL = os.environ.get("VERCEL") == "1"

app = Flask(__name__, static_folder=None if ON_VERCEL else "public", static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret")

# 네이버 지도 Client ID (환경 변수로만 받는다. 비어 있으면 지도는 Leaflet + OpenStreetMap)
NAVER_MAP_CLIENT_ID = (os.environ.get("NAVER_MAP_CLIENT_ID") or "").strip() or None

CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]
DISTANCE_OPTIONS = [1, 2, 5, 10]       # km
BUDGET_OPTIONS = [0, 5000, 10000, 20000]  # 원
RESULT_LIMIT = 30  # 결과 목록·지도에 보여 줄 최대 개수 (점수 계산은 전체 대상)
NATIONALITIES = ["KR", "US", "CN", "JP", "TW", "VN", "TH", "PH", "ID", "OTHER"]
SEARCH_KEYS = ["q", "dist", "budget", "day", "time", "lat", "lng", "dong"]  # 결과 → 상세로 넘기는 검색 조건

# 검색어 칸에 카테고리 이름을 쓰면 카테고리로 찾는다. 4개 언어 번역 + 자주 쓰는 다른 말
CATEGORY_WORDS = {"카페": ["커피", "coffee", "cafe", "cafes", "café", "咖啡", "コーヒー"],
                  "음식": ["맛집", "식당", "음식점", "restaurant", "restaurants", "food", "餐厅", "レストラン"],
                  "야경": ["night view", "nightview", "night"], "자연": ["공원", "park", "parks"],
                  "쇼핑": ["shopping", "shop"], "역사": ["history", "historic"]}

database.init_db()


# ---------------------------------------------------------------- 모든 화면에 공통

@app.before_request
def load_context():
    """요청마다: 화면 언어와 로그인한 회원을 읽어 둔다"""
    g.lang = session.get("lang", texts.DEFAULT_LANG)
    uid = session.get("user_id")
    g.user = database.get_user(uid) if uid else None


def t(key, **values):
    """화면 문구 번역 (템플릿에서 {{ t('키') }} 로 쓴다)"""
    return texts.translate(g.lang, key, **values)


def place_name(p):
    """한국어 화면은 한글 이름, 다른 언어는 영문 이름 → 없으면 로마자"""
    if g.lang == "ko":
        return p["name"]
    return p.get("name_en") or texts.romanize(p["name"])


def dong_name(d):
    if g.lang == "ko":
        return d
    return texts.romanize_dong(d)


@app.context_processor
def inject_helpers():
    """템플릿(HTML)에서 쓸 수 있는 값과 함수"""
    # 출발점은 모든 화면(검색 폼 문구·지도 출발점 표시)에서 같은 값을 쓴다
    origin, origin_state = search.resolve_origin(request.args.get("lat"), request.args.get("lng"))
    return {"t": t, "lang": g.lang, "LANGS": texts.LANGS, "user": g.user,
            "place_name": place_name, "dong_name": dong_name,
            "CATEGORIES": CATEGORIES, "WEIGHTS": search.WEIGHTS,
            "origin": origin, "origin_state": origin_state,
            "naver_map_client_id": NAVER_MAP_CLIENT_ID}


def safe_next(target):
    """로그인 뒤 돌아갈 주소는 우리 사이트 안('/'로 시작, '//'는 다른 사이트라 안 됨)만 허용"""
    return target.startswith("/") and not target.startswith("//")


def login_redirect(like_place_id=None):
    """로그인이 안 되어 있으면 로그인 화면으로 보내는 응답을, 되어 있으면 None을 돌려준다.
    폼(리뷰·찜)에서 왔으면 로그인 후 보던 화면으로 돌아오고, 찜은 로그인 후 이어서 처리한다."""
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


# ---------------------------------------------------------------- 검색 조건 읽기

def to_int(value):
    """글자를 정수로. 숫자가 아니면 None"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def valid_time(text):
    """'HH:MM' 형식의 올바른 시각(00:00~23:59)인지"""
    if len(text) != 5 or text[2] != ":":
        return False
    h1, h2, m1, m2 = text[0], text[1], text[3], text[4]
    if not (h2.isdecimal() and m2.isdecimal()):
        return False
    hour_ok = h1 in "01" or (h1 == "2" and h2 in "0123")
    return hour_ok and m1 in "012345"


def category_from_query(q):
    """검색어가 카테고리 이름과 같으면 그 카테고리 (대소문자·앞뒤 공백 무시). 아니면 None"""
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
    """주소창의 값(request.args)에서 검색 조건을 읽는다."""
    budget = to_int(args.get("budget"))
    day = to_int(args.get("day"))
    if day is not None and not (0 <= day <= 6):
        day = None
    dist = to_int(args.get("dist")) or 5
    time = args.get("time") or ""
    if not valid_time(time):
        time = None
    # 브라우저 위치(숨은 칸 lat, lng). 대전 중구 밖이거나 없으면 기본 위치(대전 중구청 앞)
    origin, _state = search.resolve_origin(args.get("lat"), args.get("lng"))

    categories = []
    for c in args.getlist("cat"):
        if c in CATEGORIES:
            categories.append(c)
    query = (args.get("q") or "").strip()
    as_cat = category_from_query(query)
    g.query_as_category = None
    if as_cat:
        # '카페'처럼 카테고리 이름이면 검색어 대신 카테고리로 찾는다 (화면에 안내)
        g.query_as_category = query
        query = ""
        if as_cat not in categories:
            categories.append(as_cat)
    return search.Conditions(categories=categories, query=query, max_km=float(dist), budget=budget,
                             day=day, time=time, origin=origin)


def search_args():
    """결과 → 상세로 넘어갈 때 검색 조건을 그대로 넘기기 위한 값"""
    out = {}
    for k in SEARCH_KEYS:
        if request.args.get(k):
            out[k] = request.args.get(k)
    if request.args.getlist("cat"):
        out["cat"] = request.args.getlist("cat")
    return out


def search_url(args, **changes):
    """지금 검색 조건(args)에서 일부만 바꾼 검색 주소. 바꿀 값이 None이면 그 조건을 뺀다."""
    out = {}
    for k in args:
        if k not in changes:
            out[k] = args[k]
    for k in changes:
        if changes[k] is not None:
            out[k] = changes[k]
    return url_for("search_view", **out)


def dong_counts(ranked):
    """결과 목록의 동네별 개수 (많은 순, 개수가 같으면 먼저 나온 동네 먼저)"""
    counts = {}
    for p in ranked:
        if p.get("dong"):
            counts[p["dong"]] = counts.get(p["dong"], 0) + 1
    pairs = list(counts.items())
    pairs.sort(key=pair_count, reverse=True)  # sort는 같은 값의 순서를 유지한다
    return pairs


def pair_count(pair):
    return pair[1]


def map_points(items, src):
    """지도에 찍을 점 목록 (지도 스크립트가 읽는다)"""
    points = []
    for p in items:
        points.append({"id": p["id"], "name": place_name(p), "lat": p["lat"], "lng": p["lng"],
                       "rank": p.get("rank"), "src": src})
    return points


def local_places():
    """대기업 계열·대형 프랜차이즈를 뺀 장소 (첫 화면 지도, 사업자 가입 가게 목록)"""
    out = []
    for p in database.all_places_with_stats():
        if not p["is_conglomerate"] and not p.get("is_franchise"):
            out.append(p)
    return out


def run_search_with(args):
    """주소창 조건으로 검색. 돌려주는 값: (조건, 순위 목록, 제외 목록)"""
    cond = parse_conditions(args)
    ranked, excluded = search.run_search(database.all_places_with_stats(), cond, site_avg=database.site_average())
    return cond, ranked, excluded


# ---------------------------------------------------------------- 첫 화면·검색 결과

@app.route("/")
def index():
    places = local_places()
    # 상가정보 점포까지 다 찍으면 수천 개라, 첫 화면은 관광공사 등록 장소만 보여 준다
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

    # 동네별 요약은 동네로 거르기 전 전체 결과 기준 (다른 동네로 바로 옮겨 갈 수 있게)
    dong = (request.args.get("dong") or "").strip() or None
    dong_links = []
    for d, n in dong_counts(ranked):
        dong_links.append((d, n, search_url(args, dong=d)))
    if dong:
        # 순위·다양성 보정은 전체 결과 기준 그대로 두고 그 동네만 남긴다 (순위 번호도 전체 기준)
        in_dong = []
        for p in ranked:
            if p.get("dong") == dong:
                in_dong.append(p)
        ranked = in_dong

    # 카테고리 칩: 다른 조건은 그대로 두고 카테고리만 하나로 바꿔 다시 검색
    cat_links = []
    for c in CATEGORIES:
        cat_links.append((c, search_url(args, cat=[c])))

    shown = ranked[:RESULT_LIMIT]
    return render_template("results.html", cond=cond, ranked=shown, total=len(ranked),
                           excluded=excluded, points=map_points(shown, "map"), args=args,
                           dong=dong, dong_links=dong_links, dong_all_url=search_url(args, dong=None),
                           cat_links=cat_links, cat_all_url=search_url(args, cat=None),
                           distance_options=DISTANCE_OPTIONS, budget_options=BUDGET_OPTIONS)


# ---------------------------------------------------------------- 장소 상세·리뷰·찜

def is_own_place(place_id):
    """사업자가 자기 가게를 보고 있는지 (자기 가게에는 리뷰·찜을 못 하고, 조회수에도 넣지 않는다)"""
    return bool(g.user and g.user["role"] == "owner" and g.user["owner_place_id"] == place_id)


def should_log_view(place_id):
    """같은 사람(같은 브라우저)이 같은 날 다시 본 것은 세지 않는다. 사업자 본인 조회도 뺀다."""
    if is_own_place(place_id):
        return False
    key = str(place_id) + ":" + datetime.now().date().isoformat()
    seen = session.get("viewed", [])
    if key in seen:
        return False
    session["viewed"] = (seen + [key])[-100:]  # 쿠키가 커지지 않게 최근 100개만
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
        database.log_view(place_id, g.user["id"] if g.user else None, src, request.args.get("q"))

    # 검색에서 넘어왔으면 같은 조건으로 다시 계산해 점수표를 보여 준다
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
    mine = database.user_review(g.user["id"], place_id) if g.user else None
    liked = database.has_liked(g.user["id"], place_id) if g.user else False

    return render_template("place.html", place=place, scored=scored,
                           excluded_reasons=excluded_reasons, args=args, reviews=reviews,
                           summary=summary, mine=mine, liked=liked, own_place=is_own_place(place_id),
                           points=map_points([place], "map"))


def back_to_place(place_id):
    """리뷰·찜 후 원래 보던 상세 화면(검색 조건 포함)으로 돌아간다"""
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


# ---------------------------------------------------------------- 회원

def reset_session(user_id=None):
    """로그인·로그아웃·가입 때 세션을 새로 만든다. 언어와 '오늘 본 가게' 기록(조회수 중복 방지)은 남긴다."""
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
    places = sorted(local_places(), key=place_name_key)  # 가나다순
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        nationality = request.form.get("nationality") or "KR"
        if nationality not in NATIONALITIES:
            nationality = "OTHER"
        role = "owner" if request.form.get("role") == "owner" else "tourist"
        owner_place = request.form.get("owner_place_id")
        owner_place_id = int(owner_place) if role == "owner" and owner_place else None

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
            # 로그인 전에 누른 찜을 이어서 처리 (이미 찜했거나 자기 가게면 그대로 둔다)
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


# ---------------------------------------------------------------- 사업자 대시보드

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


# ---------------------------------------------------------------- 언어·상태

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
    """DB를 지우고 다시 만든다: flask --app app init-db"""
    database.init_db(reset=True)
    print("DB 초기화 완료:", database.DB_PATH)


# ---------------------------------------------------------------- 직접 실행 (python app.py)

def free_port(start):
    """start번부터 20개 중 비어 있는 포트 번호 (macOS는 5000번을 AirPlay가 쓰는 경우가 있음)"""
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(("127.0.0.1", port)) != 0:  # 연결이 안 되면 비어 있는 것
                return port
    return start


def choose_port():
    """포트 번호: 환경 변수 PORT(또는 TRIPPIN_PORT) → 자동 재시작 전에 쓰던 번호 → 5000부터 빈 번호"""
    fixed = int(os.environ.get("PORT") or os.environ.get("TRIPPIN_PORT") or 0)
    if fixed:
        return fixed
    if os.environ.get("TRIPPIN_RUN_PORT"):
        return int(os.environ["TRIPPIN_RUN_PORT"])
    return free_port(5000)


if __name__ == "__main__":
    port = choose_port()
    os.environ["TRIPPIN_RUN_PORT"] = str(port)  # 코드를 고쳐 자동 재시작될 때도 같은 포트를 쓰게
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true":  # 자동 재시작 때 브라우저가 두 번 열리지 않게
        print(f"트립핀 실행 중: http://127.0.0.1:{port}  (끄려면 Ctrl+C)")
        webbrowser.open(f"http://127.0.0.1:{port}")
    app.run(debug=True, port=port)
