# 트립핀(Trippin) - Flask 진입 파일
#
# 버전 기록
# v0.1 (2026-11-18) Vercel 배포 확인용 최소 Flask 앱 생성 (메인 페이지 + 상태 확인 경로)

import os

from flask import Flask

app = Flask(__name__)
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
    </head>
    <body style="font-family: sans-serif; text-align: center; padding-top: 80px;">
      <h1>트립핀 Trippin</h1>
      <p>대전 중구 로컬 관광 지도 — 배포 테스트 페이지</p>
    </body>
    </html>
    """


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=True)
