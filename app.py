"""
=====================================================
VIBE-FASHION 애플리케이션 팩토리 모듈 (app.py)
=====================================================
이 파일은 Flask 앱 팩토리 패턴(Application Factory Pattern)을 구현한 곳입니다.
글로벌 app 객체를 바로 생성하지 않고, create_app() 함수를 통해
필요할 때마다 설정이 적용된 Flask 인스턴스를 생성하여 반환합니다.

[장점]
1. 테스트 코드 작성 시 서로 다른 설정으로 앱 인스턴스를 쉽게 생성 가능
2. 순환 참조(Circular Import) 문제 예방
3. 대규모 프로젝트로 확장 시 구조적 유지보수 용이
"""

import os
from flask import Flask
from dotenv import load_dotenv

# .env 파일에서 환경 변수를 자동으로 불러옵니다 (기존 환경변수 override).
load_dotenv(override=True)


def create_app(config_override=None):
    """
    Flask 애플리케이션 팩토리 함수

    :param config_override: 테스트 또는 특정 환경을 위한 추가 설정 딕셔너리
    :return: 설정 및 블루프린트가 등록된 Flask app 객체
    """
    # 현재 파일(app.py)이 위치한 디렉터리 경로를 기준으로 templates와 static 폴더를 지정합니다.
    base_dir = os.path.abspath(os.path.dirname(__file__))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    # Flask 앱 인스턴스 생성
    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )

    # 기본 설정 적용
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "vibe-fashion-default-secret-key-2026"),
        # 추후 Supabase 연동 시 사용할 수 있도록 환경 변수를 설정에 등록합니다.
        SUPABASE_URL=os.getenv("SUPABASE_URL", ""),
        SUPABASE_KEY=os.getenv("SUPABASE_KEY", ""),
    )

    # 추가적인 설정 오버라이드가 있다면 반영
    if config_override:
        app.config.update(config_override)

    # ---------------------------------------------------------
    # 블루프린트(Blueprint) 등록
    # routes/ 폴더의 라우트 모듈들을 가져와서 앱에 연결합니다.
    # ---------------------------------------------------------
    from routes.main import main_bp
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # 404 에러 핸들러 (사용자가 잘못된 경로 또는 기존 /admin으로 접근했을 때 안내)
    @app.errorhandler(404)
    def page_not_found(error):
        from flask import render_template
        return render_template("404.html"), 404

    # 이전의 /admin 및 하위 경로 직접 접근 시 완전 차단 (쇼핑몰 로그인으로 리다이렉트)
    @app.route("/admin", defaults={"subpath": ""})
    @app.route("/admin/<path:subpath>")
    def block_legacy_admin(subpath):
        from flask import redirect, url_for
        return redirect(url_for("auth.login"))

    return app


# Azure App Service 및 Gunicorn 기본 진입점 (app:app 지원)
app = create_app()
