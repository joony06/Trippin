# 트립핀(Trippin) - Flask 진입 파일 (화면 라우트)
#
# 버전 기록
# v0.1 (2026-11-18) Vercel 배포 확인용 최소 Flask 앱 생성 (메인 페이지 + 상태 확인 경로)
# v0.2 (2026-11-18) 로고·파비콘 적용, 로컬 실행 시 public/ 폴더를 정적 파일로 제공 (Vercel에서는 CDN이 제공)
# v0.3 (2026-11-18) Vercel 빌드 실패 수정: app = Flask(...) 를 if 문 밖 최상위 한 줄로 정의
# v0.4 (2026-11-18) MVP 뼈대: 필터링 검색·장소 상세(점수표)·리뷰·찜·회원가입/로그인·사업자 대시보드·다국어 연결

import os
import re
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
from core.i18n import DEFAULT_LANG, LANGS, translate
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

CATEGORIES = ["역사", "자연", "음식", "카페", "사진명소", "야경", "쇼핑", "문화", "액티비티", "가족"]
DISTANCE_OPTIONS = [1, 2, 5, 10]
BUDGET_OPTIONS = [0, 5000, 10000, 20000]
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

    return {"t": t, "lang": g.lang, "LANGS": LANGS, "user": g.user,
            "CATEGORIES": CATEGORIES, "WEIGHTS": WEIGHTS}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


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
    return Conditions(
        categories=[c for c in args.getlist("cat") if c in CATEGORIES],
        query=(args.get("q") or "").strip(),
        max_km=float(dist),
        budget=budget,
        day=day if day is not None and 0 <= day <= 6 else None,
        time=args.get("time") if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", args.get("time") or "") else None,
    )


def search_args():
    """결과 → 상세로 넘어갈 때 검색 조건을 그대로 넘기기 위한 값"""
    keys = ["q", "dist", "budget", "day", "time"]
    out = {k: request.args.get(k) for k in keys if request.args.get(k)}
    if request.args.getlist("cat"):
        out["cat"] = request.args.getlist("cat")
    return out


def map_points(items, src):
    return [{"id": p["id"], "name": p["name"], "lat": p["lat"], "lng": p["lng"],
             "rank": p.get("rank"), "src": src} for p in items]


# ---------------------------------------------------------------- 검색

@app.route("/")
def index():
    places = [p for p in db.all_places_with_stats() if not p["is_conglomerate"]]
    return render_template("index.html", points=map_points(places, "map"),
                           distance_options=DISTANCE_OPTIONS, budget_options=BUDGET_OPTIONS,
                           cond=Conditions())


@app.route("/search")
def search_view():
    cond = parse_conditions(request.args)
    ranked, excluded = search(db.all_places_with_stats(), cond, site_avg=db.site_average())
    return render_template("results.html", cond=cond, ranked=ranked, excluded=excluded,
                           points=map_points(ranked, "map"), args=search_args(),
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
                           summary=summary, mine=mine, liked=liked,
                           points=map_points([place], "map"))


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
    if 1 <= rating <= 5:
        db.upsert_review(g.user["id"], place_id, rating, (request.form.get("body") or "").strip()[:500])
    return back_to_place(place_id)


@app.post("/place/<int:place_id>/like")
@login_required
def like(place_id):
    if db.get_place(place_id) is None:
        abort(404)
    db.toggle_like(g.user["id"], place_id)
    return back_to_place(place_id)


# ---------------------------------------------------------------- 회원

@app.route("/signup", methods=["GET", "POST"])
def signup():
    places = [p for p in db.all_places_with_stats() if not p["is_conglomerate"]]
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
            session.clear()
            session["user_id"] = user["id"]
            session["lang"] = lang
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
