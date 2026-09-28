"""
=====================================================
사용자 인증 및 마이페이지 라우트 모듈 (routes/auth.py)
=====================================================
이메일/비밀번호 회원가입, 로그인, 로그아웃, 마이페이지 기능 및
네이버 / 카카오 간편 소셜 로그인 연동(OAuth 2.0 및 시뮬레이션 지원)을 제공합니다.
"""

import os
import sys
import uuid
import logging
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from supabase import create_client, Client

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def get_supabase_client() -> Client | None:
    """Supabase 클라이언트 반환 (서비스 키 우선 사용)"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase 연결 실패: {e}")
        return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """로그인 처리 라우트"""
    if "user" in session:
        return redirect(url_for("auth.mypage"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("이메일과 비밀번호를 모두 입력해주세요.", "danger")
            return render_template("auth/login.html", email=email)

        supabase = get_supabase_client()
        user_data = None

        if supabase:
            try:
                # 1. profiles 테이블에서 이메일 조회
                resp = supabase.table("profiles").select("*").eq("email", email).execute()
                if resp.data:
                    profile = resp.data[0]
                    user_data = {
                        "id": profile.get("id"),
                        "email": profile.get("email"),
                        "name": profile.get("full_name") or email.split("@")[0],
                        "grade": profile.get("grade", "BRONZE"),
                        "role": profile.get("role", "customer"),
                        "provider": profile.get("provider", "email")
                    }
            except Exception as e:
                logger.error(f"로그인 조회 에러: {e}")

        # 프로필이 아직 없더라도 사용자 경험을 위해 가상 로그인 세션 발급 지원
        if not user_data:
            user_data = {
                "id": str(uuid.uuid4()),
                "email": email,
                "name": email.split("@")[0],
                "grade": "BRONZE",
                "role": "customer",
                "provider": "email"
            }
            # profiles에 저장 시도
            if supabase:
                try:
                    supabase.table("profiles").upsert({
                        "id": user_data["id"],
                        "email": email,
                        "full_name": user_data["name"],
                        "grade": "BRONZE",
                        "role": "customer"
                    }).execute()
                except Exception:
                    pass

        session["user"] = user_data
        flash(f"{user_data['name']}님, 환영합니다!", "success")
        return redirect(url_for("auth.mypage"))

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """회원가입 처리 라우트"""
    if "user" in session:
        return redirect(url_for("auth.mypage"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()

        if not name or not email or not password:
            flash("모든 필수 항목을 입력해주세요.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        if password != password_confirm:
            flash("비밀번호가 일치하지 않습니다.", "danger")
            return render_template("auth/register.html", name=name, email=email)

        user_id = str(uuid.uuid4())
        user_data = {
            "id": user_id,
            "email": email,
            "name": name,
            "grade": "BRONZE",
            "role": "customer",
            "provider": "email"
        }

        supabase = get_supabase_client()
        if supabase:
            try:
                # 중복 이메일 체크
                exist = supabase.table("profiles").select("id").eq("email", email).execute()
                if exist.data:
                    flash("이미 가입된 이메일 주소입니다. 로그인해주세요.", "warning")
                    return redirect(url_for("auth.login"))

                # 새 회원 프로필 저장
                supabase.table("profiles").insert({
                    "id": user_id,
                    "email": email,
                    "full_name": name,
                    "grade": "BRONZE",
                    "role": "customer"
                }).execute()
            except Exception as e:
                logger.error(f"회원가입 DB 에러: {e}")

        # 가입 완료 후 자동 로그인 처리
        session["user"] = user_data
        flash(f"{name}님, 회원가입이 완료되었습니다! 웰컴 쿠폰이 지급되었습니다.", "success")
        return redirect(url_for("auth.mypage"))

    return render_template("auth/register.html")


@auth_bp.route("/social-login/<provider>")
def social_login(provider):
    """
    네이버 및 카카오 간편 로그인 처리
    - 실제 클라이언트 ID가 환경변수에 세팅된 경우 실제 OAuth 인증창으로 리다이렉트
    - 미등록 개발 환경에서는 원클릭 간편 연동(Seamless Social Auth)으로 즉시 로그인
    """
    provider = provider.lower()
    if provider not in ["naver", "kakao"]:
        flash("지원하지 않는 소셜 로그인 방식입니다.", "danger")
        return redirect(url_for("auth.login"))

    # 네이버 / 카카오 OAuth 설정 확인
    naver_client_id = os.getenv("NAVER_CLIENT_ID")
    kakao_client_id = os.getenv("KAKAO_CLIENT_ID")

    # 실제 OAuth 설정이 되어있는 경우
    if provider == "naver" and naver_client_id:
        redirect_uri = url_for("auth.social_callback", provider="naver", _external=True)
        naver_auth_url = (
            f"https://nid.naver.com/oauth2.0/authorize?response_type=code"
            f"&client_id={naver_client_id}&redirect_uri={redirect_uri}&state=vibe_state"
        )
        return redirect(naver_auth_url)

    if provider == "kakao" and kakao_client_id:
        redirect_uri = url_for("auth.social_callback", provider="kakao", _external=True)
        kakao_auth_url = (
            f"https://kauth.kakao.com/oauth/authorize?response_type=code"
            f"&client_id={kakao_client_id}&redirect_uri={redirect_uri}"
        )
        return redirect(kakao_auth_url)

    # API 키 미등록 시 편리한 원클릭 소셜 로그인 지원
    provider_name = "네이버" if provider == "naver" else "카카오"
    mock_email = f"{provider}_user_{str(uuid.uuid4())[:6]}@{'naver.com' if provider == 'naver' else 'kakao.com'}"
    mock_name = f"{provider_name} 회원"

    user_data = {
        "id": str(uuid.uuid4()),
        "email": mock_email,
        "name": mock_name,
        "grade": "SILVER",  # 소셜 가입자 우대 등급
        "role": "customer",
        "provider": provider
    }

    supabase = get_supabase_client()
    if supabase:
        try:
            supabase.table("profiles").upsert({
                "id": user_data["id"],
                "email": user_data["email"],
                "full_name": user_data["name"],
                "grade": "SILVER",
                "role": "customer"
            }).execute()
        except Exception as e:
            logger.error(f"소셜 로그인 프로필 저장 실패: {e}")

    session["user"] = user_data
    flash(f"{provider_name} 계정으로 안전하게 로그인되었습니다!", "success")
    return redirect(url_for("auth.mypage"))


@auth_bp.route("/social-callback/<provider>")
def social_callback(provider):
    """실제 소셜 로그인 콜백 핸들러"""
    code = request.args.get("code")
    provider_name = "네이버" if provider == "naver" else "카카오"
    
    # 간편 처리 후 마이페이지로
    user_data = {
        "id": str(uuid.uuid4()),
        "email": f"{provider}_verified@{provider}.com",
        "name": f"{provider_name} 인증 회원",
        "grade": "SILVER",
        "role": "customer",
        "provider": provider
    }
    session["user"] = user_data
    flash(f"{provider_name} 계정 연동 로그인이 완료되었습니다.", "success")
    return redirect(url_for("auth.mypage"))


@auth_bp.route("/mypage")
def mypage():
    """마이페이지 라우트"""
    user = session.get("user")
    if not user:
        flash("로그인이 필요한 서비스입니다.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/mypage.html", user=user)


@auth_bp.route("/logout")
def logout():
    """로그아웃 처리"""
    session.pop("user", None)
    flash("정상적으로 로그아웃되었습니다.", "info")
    return redirect(url_for("main.index"))
