# 트립핀(Trippin) - Flask 진입 파일
#
# 버전 기록
# v0.1 (2026-11-18) Vercel 배포 확인용 최소 Flask 앱 생성 (메인 페이지 + 상태 확인 경로)
# v0.2 (2026-11-18) 로고·파비콘 적용, 로컬 실행 시 public/ 폴더를 정적 파일로 제공 (Vercel에서는 CDN이 제공)
# v0.3 (2026-11-18) Vercel 빌드 실패 수정: app = Flask(...) 를 if 문 밖 최상위 한 줄로 정의

import os

from flask import Flask

# Vercel에서는 public/** 를 CDN이 직접 제공하므로 Flask 정적 폴더를 쓰지 않는다.
# 로컬(flask run)에서만 public/ 를 루트 경로(/logo.png 등)로 제공해 배포 환경과 주소를 맞춘다.
ON_VERCEL = os.environ.get("VERCEL") == "1"

app = Flask(
    __name__,
    static_folder=None if ON_VERCEL else "public",
    static_url_path="",
)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret")


@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html lang="ko">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>트립핀 Trippin</title>
      <link rel="icon" type="image/png" href="/favicon.png">
      <link rel="apple-touch-icon" href="/apple-touch-icon.png">
    </head>
    <body style="font-family: sans-serif; text-align: center; padding-top: 80px; color: #0B1A4A;">
      <img src="/logo-wordmark.png" alt="Trippin" style="width: min(480px, 80vw);">
      <p>대전 중구 로컬 관광 지도 — 배포 테스트 페이지</p>
    </body>
    </html>
    """


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True)
