"""
=====================================================
사용자 인증 및 마이페이지 라우트 모듈 (routes/auth.py)
=====================================================
이메일 회원가입, 로그인, 이메일 인증, 비밀번호 재설정, 마이페이지 기능 및
네이버 / 카카오 간편 소셜 로그인 연동(OAuth 2.0 및 개발 모드 지원)을 제공합니다.
Supabase Python 클라이언트를 사용하여 인증 상태를 안전하게 관리합니다.
"""

import os
import sys
import uuid
import json
import secrets
import logging
import smtplib
import urllib.request
import urllib.parse
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, current_app
from supabase import create_client, Client

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# =====================================================
# 한국어 에러 및 성공 메시지 매핑
# =====================================================
AUTH_MESSAGES = {
    # 에러 메시지
    "email_not_confirmed": "이메일 인증이 완료되지 않았습니다. 메일함의 인증 링크를 클릭하여 인증을 완료해주세요.",
    "invalid_credentials": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "login_required": "로그인이 필요한 서비스입니다.",
    "user_exists": "이미 가입된 이메일 계정입니다. 로그인해주세요.",
    "password_mismatch": "비밀번호와 비밀번호 확인이 일치하지 않습니다.",
    "password_too_short": "비밀번호는 최소 6자 이상이어야 합니다.",
    "missing_fields": "모든 필수 항목을 입력해주세요.",
    "terms_required": "이용약관 및 개인정보 처리방침에 동의해주세요.",
    "invalid_token": "인증 토큰이 유효하지 않거나 만료되었습니다.",
    "confirm_failed": "이메일 인증 처리에 실패했습니다. 유효하지 않거나 이미 사용된 링크입니다.",
    "reset_failed": "비밀번호 변경 처리 중 오류가 발생했습니다. 다시 시도해주세요.",
    "rate_limit": "이메일 발송 한도(시간당 3~4건)가 초과되었습니다. 잠시 후 다시 시도해주세요.",
    "resend_failed": "인증 메일 재발송에 실패했습니다. 이메일 주소를 다시 확인해주세요.",
    "delete_failed": "회원 탈퇴 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "login_failed": "로그인 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "signup_failed": "회원가입 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    "profile_updated": "회원 정보가 성공적으로 수정되었습니다.",
    "update_failed": "회원 정보 수정 중 오류가 발생했습니다. 다시 시도해주세요.",
    "current_password_incorrect": "현재 비밀번호가 일치하지 않습니다.",
    "password_same_as_old": "새로운 비밀번호가 현재 비밀번호와 동일합니다.",
    "password_changed": "비밀번호가 변경되었습니다.",
    # 성공 메시지
    "confirmed": "이메일 인증이 성공적으로 완료되었습니다! 환영합니다.",
    "resend_success": "인증 메일이 재발송되었습니다. 메일함을 확인해주세요.",
    "account_deleted": "회원 탈퇴가 완료되었습니다. 그동안 이용해주셔서 감사합니다.",
    "password_reset_sent": "비밀번호 재설정 링크를 입력하신 이메일로 전송했습니다. 메일함을 확인해주세요.",
    "password_reset_success": "비밀번호가 성공적으로 변경되었습니다. 새 비밀번호로 로그인해주세요.",
    "logged_out": "정상적으로 로그아웃되었습니다.",
    "social_login_success": "소셜 계정으로 성공적으로 로그인되었습니다!",
    "social_config_missing": "소셜 로그인 API 키 설정이 필요합니다. .env 파일을 확인해주세요.",
    "social_cancelled": "소셜 로그인이 취소되었습니다.",
    "social_token_failed": "소셜 인증 토큰 발급에 실패했습니다. Client ID 및 Secret, Redirect URI를 확인해주세요.",
    "social_user_failed": "소셜 회원 정보를 가져오는데 실패했습니다.",
    "unsupported_provider": "지원하지 않는 소셜 로그인 방식입니다."
}


def get_site_url() -> str:
    """사이트 URL 반환 (환경변수 또는 현재 요청의 호스트를 기반으로 동적 생성, 끝의 슬래시 제거)"""
    env_url = os.getenv("SITE_URL")
    if env_url:
        return env_url.rstrip("/")

    # 배포 환경(Azure 등)에서 환경변수가 미지정되어 있거나 요청 기반으로 감지해야 할 때
    try:
        from flask import has_request_context, request
        if has_request_context():
            # X-Forwarded-Proto 및 Host 헤더 반영
            scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
            host = request.headers.get("X-Forwarded-Host", request.host)
            return f"{scheme}://{host}".rstrip("/")
    except Exception:
        pass

    return "http://localhost:5000"


def get_alert_messages():
    """
    URL 파라미터에서 error 및 success 코드를 읽어
    사용자에게 표시할 한국어 메시지를 반환합니다.
    """
    error_code = request.args.get("error")
    success_code = request.args.get("success")

    error_msg = AUTH_MESSAGES.get(error_code, error_code) if error_code else None
    success_msg = AUTH_MESSAGES.get(success_code, success_code) if success_code else None

    return error_msg, success_msg, error_code, success_code


def get_supabase_client() -> Client | None:
    """Supabase Anon 클라이언트 반환 (사용자 인증 및 공개 API용)"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase 클라이언트 생성 실패: {e}")
        return None


def get_supabase_admin_client() -> Client | None:
    """Supabase 서비스 키 클라이언트 반환 (관리자 작업 및 프로필 동기화용)"""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase 관리자 클라이언트 생성 실패: {e}")
        return None


# =====================================================
# Gmail SMTP 발송 헬퍼 함수
# =====================================================
def send_email_via_gmail_smtp(to_email: str, subject: str, html_content: str) -> bool:
    """
    Gmail SMTP 서버를 통해 인증 및 안내 이메일을 발송합니다.
    환경변수:
      - SMTP_USER 또는 GMAIL_USER (Gmail 계정)
      - SMTP_PASSWORD 또는 GMAIL_APP_PASSWORD (구글 앱 비밀번호 16자리)
    """
    smtp_user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
    smtp_password = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    if not smtp_user or not smtp_password:
        logger.info("Gmail SMTP 환경변수(SMTP_USER, SMTP_PASSWORD)가 설정되지 않아 Supabase 기본 메일 경로를 유지합니다.")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"VIBE-FASHION <{smtp_user}>"
        msg["To"] = to_email

        html_part = MIMEText(html_content, "html", "utf-8")
        msg.attach(html_part)

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password.replace(" ", ""))
            server.sendmail(smtp_user, to_email, msg.as_string())

        logger.info(f"Gmail SMTP를 통해 {to_email} 주소로 이메일 발송 성공: {subject}")
        return True
    except Exception as e:
        logger.error(f"Gmail SMTP 발송 실패: {e}")
        return False


def send_signup_confirmation_email(to_email: str, user_name: str, confirm_url: str) -> bool:
    """회원가입 인증 링크 이메일 발송"""
    subject = "[VIBE-FASHION] 회원가입 이메일 인증을 완료해주세요"
    html_content = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width: 580px; margin: 0 auto; padding: 40px 20px; color: #222;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #111; font-size: 26px; font-weight: 800; letter-spacing: -0.5px; margin: 0;">VIBE-FASHION</h1>
            <p style="color: #666; font-size: 14px; margin-top: 6px;">나만의 스타일 셀렉트샵</p>
        </div>
        <div style="background-color: #ffffff; border: 1px solid #eaeaea; border-radius: 16px; padding: 36px 28px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
            <h2 style="font-size: 20px; font-weight: bold; margin-top: 0; color: #111;">안녕하세요, {user_name}님!</h2>
            <p style="font-size: 15px; line-height: 1.6; color: #444;">
                VIBE-FASHION에 회원가입해 주셔서 진심으로 감사드립니다.<br>
                아래 버튼을 클릭하여 이메일 인증을 완료하시면 회원가입이 완료됩니다.
            </p>
            <div style="text-align: center; margin: 35px 0;">
                <a href="{confirm_url}" style="background-color: #111111; color: #ffffff; padding: 14px 32px; border-radius: 50px; text-decoration: none; font-weight: bold; font-size: 15px; display: inline-block;">
                    이메일 인증 완료하기
                </a>
            </div>
            <p style="font-size: 13px; color: #888; line-height: 1.5; margin-bottom: 0;">
                버튼이 클릭되지 않는다면 아래 링크를 브라우저 주소창에 직접 복사하여 접속해주세요:<br>
                <a href="{confirm_url}" style="color: #0d6efd; word-break: break-all;">{confirm_url}</a>
            </p>
        </div>
        <div style="text-align: center; margin-top: 25px; font-size: 12px; color: #999;">
            본 메일은 발신 전용이며, 요청하지 않은 경우 무시하셔도 됩니다.<br>
            &copy; VIBE-FASHION. All rights reserved.
        </div>
    </div>
    """
    return send_email_via_gmail_smtp(to_email, subject, html_content)


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """비밀번호 재설정 링크 이메일 발송"""
    subject = "[VIBE-FASHION] 비밀번호 재설정 링크 안내"
    html_content = f"""
    <div style="font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width: 580px; margin: 0 auto; padding: 40px 20px; color: #222;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h1 style="color: #111; font-size: 26px; font-weight: 800; letter-spacing: -0.5px; margin: 0;">VIBE-FASHION</h1>
            <p style="color: #666; font-size: 14px; margin-top: 6px;">나만의 스타일 셀렉트샵</p>
        </div>
        <div style="background-color: #ffffff; border: 1px solid #eaeaea; border-radius: 16px; padding: 36px 28px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
            <h2 style="font-size: 20px; font-weight: bold; margin-top: 0; color: #111;">비밀번호 재설정 요청</h2>
            <p style="font-size: 15px; line-height: 1.6; color: #444;">
                고객님의 계정으로 비밀번호 재설정 요청이 접수되었습니다.<br>
                아래 버튼을 클릭하여 새로운 비밀번호를 설정해주세요.
            </p>
            <div style="text-align: center; margin: 35px 0;">
                <a href="{reset_url}" style="background-color: #111111; color: #ffffff; padding: 14px 32px; border-radius: 50px; text-decoration: none; font-weight: bold; font-size: 15px; display: inline-block;">
                    새 비밀번호 설정하기
                </a>
            </div>
            <p style="font-size: 13px; color: #888; line-height: 1.5; margin-bottom: 0;">
                본인이 요청하지 않은 경우 계정 정보가 노출되지 않도록 주의해 주시기 바랍니다.<br>
                <a href="{reset_url}" style="color: #0d6efd; word-break: break-all;">{reset_url}</a>
            </p>
        </div>
        <div style="text-align: center; margin-top: 25px; font-size: 12px; color: #999;">
            본 메일은 발신 전용 메일입니다.<br>
            &copy; VIBE-FASHION. All rights reserved.
        </div>
    </div>
    """
    return send_email_via_gmail_smtp(to_email, subject, html_content)


# =====================================================
# 세션 유효성 검증 (탈퇴/삭제된 계정의 자동 로그인 방지)
# =====================================================
@auth_bp.before_app_request
def validate_session_user():
    """
    모든 요청 전 Flask 세션의 사용자가 Supabase DB에 실제로 존재하는지 확인합니다.
    (탈퇴/삭제된 계정의 세션이 브라우저에 남아있어 자동으로 로그인된 것처럼 보이는 문제를 원천 차단)
    """
    if request.endpoint and (request.endpoint.startswith("static") or request.endpoint in ["auth.logout", "auth.delete_account"]):
        return
    user_id = session.get("user_id")
    if user_id:
        supabase = get_supabase_client()
        admin_client = get_supabase_admin_client()
        client = admin_client or supabase
        if client:
            try:
                prof_resp = client.table("profiles").select("id").eq("id", user_id).execute()
                if not prof_resp.data:
                    logger.info(f"Supabase에 존재하지 않는 계정 세션 감지 (user_id={user_id}) -> 세션 즉시 파기")
                    session.clear()
            except Exception as e:
                logger.warning(f"세션 유저 검증 오류: {e}")


# =====================================================
# 로그인 필수 데코레이터 (login_required)
# =====================================================
def login_required(f):
    """
    Flask session에서 user_id를 확인하여 미로그인 사용자를 로그인 페이지로 안내합니다.
    Supabase DB에 유저가 존재하지 않는 경우 세션을 즉시 파기합니다.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = session.get("user_id")
        if not user_id:
            # session['user'] 딕셔너리에 id가 있는 경우 session['user_id'] 동기화
            user_obj = session.get("user")
            if isinstance(user_obj, dict) and user_obj.get("id"):
                user_id = user_obj["id"]
                session["user_id"] = user_id
            else:
                return redirect(url_for("auth.login", error="login_required"))

        # DB에 유저가 실제 존재하는지 검증 (삭제된 유저 세션 방지)
        supabase = get_supabase_client()
        admin_client = get_supabase_admin_client()
        client = admin_client or supabase
        if client and user_id:
            try:
                prof_resp = client.table("profiles").select("id").eq("id", user_id).execute()
                if not prof_resp.data:
                    logger.info(f"Supabase에서 삭제된 사용자 세션 감지 (user_id={user_id}) -> 세션 파기")
                    session.clear()
                    return redirect(url_for("auth.login", error="login_required"))
            except Exception as e:
                logger.warning(f"login_required 사용자 확인 오류: {e}")

        return f(*args, **kwargs)
    return decorated_function


# =====================================================
# [1] GET/POST /auth/login - 로그인 폼 및 로그인 처리
# =====================================================
@auth_bp.route("/login", methods=["GET", "POST"])
@auth_bp.route("/auth/login", methods=["GET", "POST"])
def login():
    """
    로그인 폼 표시 및 로그인 요청을 처리합니다.
    - 이메일 미인증 상태일 경우 error=email_not_confirmed 파라미터와 함께 리다이렉트합니다.
    """
    user_id = session.get("user_id")
    if user_id:
        supabase = get_supabase_client()
        admin_client = get_supabase_admin_client()
        client = admin_client or supabase
        user_exists = False
        if client:
            try:
                prof_resp = client.table("profiles").select("id").eq("id", user_id).execute()
                if prof_resp.data:
                    user_exists = True
            except Exception:
                pass
        if user_exists:
            return redirect(url_for("auth.mypage"))
        else:
            session.clear()

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            return redirect(url_for("auth.login", error="missing_fields", email=email))

        supabase = get_supabase_client()
        if not supabase:
            # Supabase 미설정 로컬 개발 환경 대비 가상 로그인 세션 제공
            user_id = str(uuid.uuid4())
            user_data = {
                "id": user_id,
                "email": email,
                "name": email.split("@")[0],
                "grade": "BRONZE",
                "role": "customer",
                "provider": "email"
            }
            session["user_id"] = user_id
            session["user"] = user_data
            return redirect(url_for("auth.mypage"))

        try:
            resp = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            user = resp.user
            auth_session = resp.session

            if not user:
                return redirect(url_for("auth.login", error="login_failed", email=email))

            user_id = str(user.id)
            user_email = user.email or email
            user_meta = user.user_metadata or {}
            user_name = user_meta.get("full_name") or user_meta.get("name") or user_email.split("@")[0]

            user_data = {
                "id": user_id,
                "email": user_email,
                "name": user_name,
                "grade": "BRONZE",
                "role": "customer",
                "provider": "email"
            }

            # profiles 테이블 조회 및 동기화
            try:
                prof_resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
                if prof_resp.data:
                    profile = prof_resp.data[0]
                    user_data["name"] = profile.get("full_name") or user_data["name"]
                    user_data["grade"] = profile.get("grade", "BRONZE")
                    user_data["role"] = profile.get("role", "customer")
                else:
                    admin_client = get_supabase_admin_client() or supabase
                    admin_client.table("profiles").upsert({
                        "id": user_id,
                        "email": user_email,
                        "full_name": user_data["name"],
                        "grade": "BRONZE",
                        "role": "customer"
                    }).execute()
            except Exception as pe:
                logger.warning(f"프로필 동기화 경고: {pe}")

            # Flask session에 user_id 및 user 정보 저장
            session["user_id"] = user_id
            session["user"] = user_data
            if auth_session and hasattr(auth_session, "access_token") and auth_session.access_token:
                session["access_token"] = auth_session.access_token
                session["refresh_token"] = getattr(auth_session, "refresh_token", None)

            return redirect(url_for("auth.mypage"))

        except Exception as e:
            logger.error(f"로그인 처리 실패: {e}")
            err_str = str(e).lower()
            code = getattr(e, "code", "") or ""

            # 이메일 미인증 시 error=email_not_confirmed
            if code == "email_not_confirmed" or "email not confirmed" in err_str or "email_not_confirmed" in err_str:
                return redirect(url_for("auth.login", error="email_not_confirmed", email=email))
            elif code == "invalid_credentials" or "invalid login credentials" in err_str:
                return redirect(url_for("auth.login", error="invalid_credentials", email=email))
            else:
                return redirect(url_for("auth.login", error="login_failed", email=email))

    error_msg, success_msg, error_code, success_code = get_alert_messages()
    return render_template(
        "auth/login.html",
        error_message=error_msg,
        success_message=success_msg,
        error_code=error_code,
        success_code=success_code,
        email=request.args.get("email", "")
    )


# =====================================================
# [2] GET/POST /auth/signup - 회원가입 폼 및 회원가입 처리
# =====================================================
@auth_bp.route("/signup", methods=["GET", "POST"])
@auth_bp.route("/auth/signup", methods=["GET", "POST"])
def signup():
    """
    회원가입 폼을 제공하고 신규 회원 가입을 처리합니다.
    가입 성공 시 /auth/signup-complete 페이지로 이동합니다.
    """
    if session.get("user_id"):
        return redirect(url_for("auth.mypage"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        password_confirm = request.form.get("password_confirm", "").strip()

        if not name or not email or not password:
            return redirect(url_for("auth.signup", error="missing_fields", name=name, email=email))

        if len(password) < 6:
            return redirect(url_for("auth.signup", error="password_too_short", name=name, email=email))

        if password != password_confirm:
            return redirect(url_for("auth.signup", error="password_mismatch", name=name, email=email))

        supabase = get_supabase_client()
        site_url = get_site_url()
        email_redirect_to = f"{site_url}/auth/confirm"

        if not supabase:
            # Supabase 미설정 환경 대비 가상 완료 처리
            return redirect(url_for("auth.signup_complete"))

        # Gmail SMTP 설정이 있는 경우, Supabase 기본 메일 제한(429)을 거치지 않고 직접 Gmail로 전송
        smtp_user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
        admin_client = get_supabase_admin_client()

        if smtp_user and admin_client:
            try:
                # 1. 관리자 API로 안전하게 사용자 계정 및 인증 토큰 발급
                link_resp = admin_client.auth.admin.generate_link({
                    "type": "signup",
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {
                            "full_name": name,
                            "name": name,
                        },
                        "redirect_to": email_redirect_to
                    }
                })
                hashed_token = getattr(link_resp.properties, "hashed_token", "")
                confirm_url = f"{site_url}/auth/confirm?token_hash={hashed_token}&type=signup"

                # 2. Gmail SMTP를 통해 실제 인증 이메일 직접 발송
                email_sent = send_signup_confirmation_email(email, name, confirm_url)
                if not email_sent:
                    # SMTP 실패 시 백업 링크 세션 저장
                    session["dev_confirm_url"] = confirm_url

                session["signup_email"] = email
                return redirect(url_for("auth.signup_complete", email=email))
            except Exception as se:
                logger.error(f"Gmail SMTP 가입 처리 중 오류: {se}")
                err_str = str(se).lower()
                if "already registered" in err_str or "user already exists" in err_str:
                    return redirect(url_for("auth.signup", error="user_exists", email=email))

        try:
            resp = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "email_redirect_to": email_redirect_to,
                    "data": {
                        "full_name": name,
                        "name": name,
                    }
                }
            })

            # 중복 가입 체크 (Supabase는 동일 이메일 재가입 시 빈 identities 반환)
            if resp.user and getattr(resp.user, "identities", None) == []:
                return redirect(url_for("auth.signup", error="user_exists", email=email))

            session["signup_email"] = email
            # 가입 성공 시 /auth/signup-complete 페이지 이동
            return redirect(url_for("auth.signup_complete", email=email))

        except Exception as e:
            logger.error(f"회원가입 실패: {e}")
            err_str = str(e).lower()
            code = getattr(e, "code", "") or ""
            status = getattr(e, "status", None)

            if "already registered" in err_str or "user already exists" in err_str or code == "user_already_exists":
                return redirect(url_for("auth.signup", error="user_exists", email=email))

            # Supabase 무료 티어 기본 이메일 발송 제한(시간당 3~4건) 초과 시 안전하게 대체 인증 링크 발급
            if "rate limit" in err_str or code == "over_email_send_rate_limit" or status == 429:
                if admin_client:
                    try:
                        link_resp = admin_client.auth.admin.generate_link({
                            "type": "signup",
                            "email": email,
                            "password": password,
                            "options": {
                                "data": {
                                    "full_name": name,
                                    "name": name,
                                },
                                "redirect_to": email_redirect_to
                            }
                        })
                        hashed_token = getattr(link_resp.properties, "hashed_token", "")
                        confirm_url = f"{site_url}/auth/confirm?token_hash={hashed_token}&type=signup"
                        
                        # Gmail SMTP 발송 시도
                        email_sent = send_signup_confirmation_email(email, name, confirm_url)
                        if not email_sent:
                            session["dev_confirm_url"] = confirm_url
                            session["dev_rate_limited"] = True

                        session["signup_email"] = email
                        return redirect(url_for("auth.signup_complete", email=email))
                    except Exception as ge:
                        logger.error(f"admin.generate_link 실패: {ge}")
                return redirect(url_for("auth.signup", error="rate_limit", name=name, email=email))

            return redirect(url_for("auth.signup", error="signup_failed", name=name, email=email))

    error_msg, success_msg, error_code, success_code = get_alert_messages()
    return render_template(
        "auth/register.html",
        error_message=error_msg,
        success_message=success_msg,
        error_code=error_code,
        success_code=success_code,
        name=request.args.get("name", ""),
        email=request.args.get("email", "")
    )


@auth_bp.route("/auth/register", methods=["GET", "POST"])
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """회원가입 별칭 라우트 (url_for('auth.register') 하위 호환성 유지)"""
    return signup()



# =====================================================
# [3] GET /auth/signup-complete - 인증 메일 발송 안내
# =====================================================
@auth_bp.route("/signup-complete", methods=["GET"])
@auth_bp.route("/auth/signup-complete", methods=["GET"])
def signup_complete():
    """
    회원가입 완료 후 '인증 메일을 보냈습니다' 안내 페이지를 표시합니다.
    """
    dev_confirm_url = session.pop("dev_confirm_url", None)
    is_rate_limited = session.pop("dev_rate_limited", False)
    email = request.args.get("email") or session.get("signup_email") or ""
    return render_template(
        "auth/signup_complete.html",
        email=email,
        dev_confirm_url=dev_confirm_url,
        is_rate_limited=is_rate_limited
    )


# =====================================================
# [3-1] POST /auth/resend-confirmation - 인증 메일 재발송
# =====================================================
@auth_bp.route("/resend-confirmation", methods=["POST"])
@auth_bp.route("/auth/resend-confirmation", methods=["POST"])
def resend_confirmation():
    """
    회원가입 인증 메일을 재발송합니다.
    """
    email = request.form.get("email", "").strip()
    if not email:
        return redirect(url_for("auth.login", error="missing_fields"))

    supabase = get_supabase_client()
    site_url = get_site_url()
    email_redirect_to = f"{site_url}/auth/confirm"
    smtp_user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
    admin_client = get_supabase_admin_client()

    # Gmail SMTP가 설정되어 있는 경우 직접 링크를 생성하여 발송
    if smtp_user and admin_client:
        try:
            link_resp = admin_client.auth.admin.generate_link({
                "type": "signup",
                "email": email,
                "options": {
                    "redirect_to": email_redirect_to
                }
            })
            hashed_token = getattr(link_resp.properties, "hashed_token", "")
            confirm_url = f"{site_url}/auth/confirm?token_hash={hashed_token}&type=signup"
            sent = send_signup_confirmation_email(email, "회원", confirm_url)
            if sent:
                return redirect(url_for("auth.login", success="resend_success", email=email))
        except Exception as se:
            logger.error(f"Gmail SMTP 재발송 실패: {se}")

    if supabase:
        try:
            supabase.auth.resend({
                "type": "signup",
                "email": email,
                "options": {
                    "email_redirect_to": email_redirect_to
                }
            })
            return redirect(url_for("auth.login", success="resend_success", email=email))
        except Exception as e:
            logger.error(f"인증메일 재발송 실패: {e}")
            err_str = str(e).lower()
            code = getattr(e, "code", "") or ""
            if "rate limit" in err_str or code == "over_email_send_rate_limit":
                if admin_client:
                    try:
                        link_resp = admin_client.auth.admin.generate_link({
                            "type": "signup",
                            "email": email,
                            "options": {
                                "redirect_to": email_redirect_to
                            }
                        })
                        hashed_token = getattr(link_resp.properties, "hashed_token", "")
                        confirm_url = f"{site_url}/auth/confirm?token_hash={hashed_token}&type=signup"
                        sent = send_signup_confirmation_email(email, "회원", confirm_url)
                        if sent:
                            return redirect(url_for("auth.login", success="resend_success", email=email))
                    except Exception as re_err:
                        logger.error(f"대체 재발송 링크 생성 실패: {re_err}")
                return redirect(url_for("auth.login", error="rate_limit", email=email))
            return redirect(url_for("auth.login", error="resend_failed", email=email))

    return redirect(url_for("auth.login", success="resend_success", email=email))


# =====================================================
# [4] GET /auth/confirm - 이메일 인증 링크 클릭 처리
# =====================================================
@auth_bp.route("/confirm", methods=["GET"])
@auth_bp.route("/auth/confirm", methods=["GET"])
def confirm():
    """
    이메일 인증 링크의 토큰을 검증하고,
    성공 시 Flask session에 저장한 후 /mypage 로 이동합니다.
    - URL 쿼리 파라미터 (token_hash, access_token) 처리
    - 브라우저 URL 해시(#access_token=...) 대응 자동 스크립트 제공
    """
    token_hash = request.args.get("token_hash")
    token = request.args.get("token")
    email = request.args.get("email")
    otp_type = request.args.get("type", "signup")
    access_token = request.args.get("access_token")
    refresh_token = request.args.get("refresh_token")

    # [1] 쿼리에 토큰 파라미터가 전혀 없는 경우:
    # Supabase가 해시 프래그먼트(#access_token=...)로 리다이렉트했을 수 있으므로 클라이언트 자바스크립트로 쿼리로 전환
    if not token_hash and not token and not access_token:
        return """
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><title>이메일 인증 처리 중...</title></head>
        <body>
        <script>
            if (window.location.hash) {
                var hash = window.location.hash.substring(1);
                var params = new URLSearchParams(hash);
                var at = params.get('access_token');
                var rt = params.get('refresh_token');
                var ty = params.get('type') || 'signup';
                if (at) {
                    window.location.href = '/auth/confirm?access_token=' + encodeURIComponent(at) + (rt ? '&refresh_token=' + encodeURIComponent(rt) : '') + '&type=' + encodeURIComponent(ty);
                } else {
                    window.location.href = '/auth/login?error=invalid_token';
                }
            } else {
                window.location.href = '/auth/login?error=invalid_token';
            }
        </script>
        <p style="text-align:center; padding: 50px; font-family: sans-serif; color: #555;">이메일 인증을 처리 중입니다. 잠시만 기다려주세요...</p>
        </body>
        </html>
        """

    supabase = get_supabase_client()
    admin_client = get_supabase_admin_client()
    if not supabase:
        return redirect(url_for("auth.login", error="confirm_failed"))

    user = None
    auth_session = None

    try:
        # 1. access_token이 직접 전달된 경우
        if access_token:
            try:
                user_res = supabase.auth.get_user(access_token)
                user = getattr(user_res, "user", None)
            except Exception as e:
                logger.warning(f"access_token으로 get_user 실패: {e}")

        # 2. token_hash 검증 (verify_otp)
        if not user:
            if token_hash:
                resp = supabase.auth.verify_otp({
                    "token_hash": token_hash,
                    "type": otp_type
                })
                user = resp.user
                auth_session = resp.session
            elif token and email:
                resp = supabase.auth.verify_otp({
                    "email": email,
                    "token": token,
                    "type": otp_type
                })
                user = resp.user
                auth_session = resp.session
            elif token:
                resp = supabase.auth.verify_otp({
                    "token_hash": token,
                    "type": otp_type
                })
                user = resp.user
                auth_session = resp.session

        if not user:
            return redirect(url_for("auth.login", error="confirm_failed"))

        # 비밀번호 재설정 링크로 들어온 경우 새 비밀번호 설정 페이지로 전환
        if otp_type == "recovery":
            session["user_id"] = str(user.id)
            if auth_session and hasattr(auth_session, "access_token"):
                session["access_token"] = auth_session.access_token
                session["refresh_token"] = getattr(auth_session, "refresh_token", None)
            elif access_token:
                session["access_token"] = access_token
                session["refresh_token"] = refresh_token
            return redirect(url_for("auth.reset_password"))

        # 이메일 인증 완료 사용자 데이터 구성
        user_id = str(user.id)
        user_email = user.email or ""
        user_meta = user.user_metadata or {}
        user_name = user_meta.get("full_name") or user_meta.get("name") or (user_email.split("@")[0] if user_email else "회원")

        user_data = {
            "id": user_id,
            "email": user_email,
            "name": user_name,
            "grade": "BRONZE",
            "role": "customer",
            "provider": "email"
        }

        # profiles 테이블 조회 및 동기화
        try:
            prof_resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
            if prof_resp.data:
                profile = prof_resp.data[0]
                user_data["name"] = profile.get("full_name") or user_data["name"]
                user_data["grade"] = profile.get("grade", "BRONZE")
                user_data["role"] = profile.get("role", "customer")
            else:
                db_admin = admin_client or supabase
                db_admin.table("profiles").upsert({
                    "id": user_id,
                    "email": user_email,
                    "full_name": user_data["name"],
                    "grade": "BRONZE",
                    "role": "customer"
                }).execute()
        except Exception as pe:
            logger.warning(f"인증 후 프로필 동기화 경고: {pe}")

        # Flask session 저장
        session["user_id"] = user_id
        session["user"] = user_data
        if auth_session and hasattr(auth_session, "access_token"):
            session["access_token"] = auth_session.access_token
            session["refresh_token"] = getattr(auth_session, "refresh_token", None)
        elif access_token:
            session["access_token"] = access_token
            session["refresh_token"] = refresh_token

        # 성공 시 Flask session 저장 → /mypage
        return redirect(url_for("auth.mypage", success="confirmed"))

    except Exception as e:
        logger.error(f"이메일 인증 verify_otp 실패: {e}")
        # 이미 인증이 완료된 유저인 경우 로그인 페이지로 안내 (이메일 파라미터 보존)
        if email:
            return redirect(url_for("auth.login", success="confirmed", email=email))
        return redirect(url_for("auth.login", error="confirm_failed"))


# =====================================================
# [5] GET/POST /auth/forgot-password - 비밀번호 재설정 메일 발송
# =====================================================
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@auth_bp.route("/auth/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    비밀번호 재설정 요청 폼을 표시하고, 재설정 링크 이메일을 발송합니다.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        if not email:
            return redirect(url_for("auth.forgot_password", error="missing_fields"))

        supabase = get_supabase_client()
        site_url = get_site_url()
        redirect_url = f"{site_url}/auth/reset-password"
        smtp_user = os.getenv("SMTP_USER") or os.getenv("GMAIL_USER")
        admin_client = get_supabase_admin_client()

        # Gmail SMTP 설정이 있는 경우 복구 링크를 생성하여 직접 Gmail로 발송
        if smtp_user and admin_client:
            try:
                link_resp = admin_client.auth.admin.generate_link({
                    "type": "recovery",
                    "email": email,
                    "options": {"redirect_to": redirect_url}
                })
                hashed_token = getattr(link_resp.properties, "hashed_token", "")
                reset_url = f"{site_url}/auth/reset-password?token_hash={hashed_token}"
                sent = send_password_reset_email(email, reset_url)
                if sent:
                    return redirect(url_for("auth.forgot_password", success="password_reset_sent"))
            except Exception as se:
                logger.error(f"Gmail SMTP 재설정 발송 실패: {se}")

        if supabase:
            try:
                supabase.auth.reset_password_for_email(
                    email,
                    options={"redirect_to": redirect_url}
                )
            except Exception as e:
                logger.error(f"비밀번호 재설정 메일 발송 실패: {e}")
                err_str = str(e).lower()
                code = getattr(e, "code", "") or ""
                status = getattr(e, "status", None)

                # 메일 발송 한도 초과 시 안전하게 대체 재설정 링크 발급
                if "rate limit" in err_str or code == "over_email_send_rate_limit" or status == 429:
                    if admin_client:
                        try:
                            link_resp = admin_client.auth.admin.generate_link({
                                "type": "recovery",
                                "email": email,
                                "options": {"redirect_to": redirect_url}
                            })
                            hashed_token = getattr(link_resp.properties, "hashed_token", "")
                            reset_url = f"{site_url}/auth/reset-password?token_hash={hashed_token}"
                            
                            sent = send_password_reset_email(email, reset_url)
                            if not sent:
                                session["dev_reset_url"] = reset_url
                                session["dev_rate_limited"] = True
                            return redirect(url_for("auth.forgot_password", success="password_reset_sent"))
                        except Exception as ge:
                            logger.error(f"admin.generate_link recovery 실패: {ge}")
                    return redirect(url_for("auth.forgot_password", error="rate_limit"))

                return redirect(url_for("auth.forgot_password", error="reset_failed"))

        return redirect(url_for("auth.forgot_password", success="password_reset_sent"))

    error_msg, success_msg, error_code, success_code = get_alert_messages()
    dev_reset_url = session.pop("dev_reset_url", None)
    is_rate_limited = session.pop("dev_rate_limited", False)
    return render_template(
        "auth/forgot_password.html",
        error_message=error_msg,
        success_message=success_msg,
        error_code=error_code,
        success_code=success_code,
        dev_reset_url=dev_reset_url,
        is_rate_limited=is_rate_limited
    )


# =====================================================
# [6] GET/POST /auth/reset-password - 새 비밀번호 설정
# =====================================================
@auth_bp.route("/reset-password", methods=["GET", "POST"])
@auth_bp.route("/auth/reset-password", methods=["GET", "POST"])
def reset_password():
    """
    비밀번호 재설정 링크를 통해 접속하여 새로운 비밀번호를 설정합니다.
    """
    supabase = get_supabase_client()

    # GET 요청: 토큰 확인 및 폼 렌더링
    if request.method == "GET":
        token_hash = request.args.get("token_hash")
        if token_hash and supabase:
            try:
                resp = supabase.auth.verify_otp({
                    "token_hash": token_hash,
                    "type": "recovery"
                })
                if resp.user:
                    session["user_id"] = str(resp.user.id)
                    if resp.session:
                        session["access_token"] = resp.session.access_token
                        session["refresh_token"] = getattr(resp.session, "refresh_token", None)
            except Exception as e:
                logger.warning(f"reset-password verify_otp 실패: {e}")

        error_msg, success_msg, error_code, success_code = get_alert_messages()
        return render_template(
            "auth/reset_password.html",
            error_message=error_msg,
            success_message=success_msg,
            error_code=error_code,
            success_code=success_code,
            token_hash=token_hash or ""
        )

    # POST 요청: 새 비밀번호 적용
    password = request.form.get("password", "").strip()
    password_confirm = request.form.get("password_confirm", "").strip()
    token_hash = request.form.get("token_hash", "").strip()
    access_token = request.form.get("access_token", "").strip()
    refresh_token = request.form.get("refresh_token", "").strip()

    if not password:
        return redirect(url_for("auth.reset_password", error="missing_fields", token_hash=token_hash))

    if len(password) < 6:
        return redirect(url_for("auth.reset_password", error="password_too_short", token_hash=token_hash))

    if password != password_confirm:
        return redirect(url_for("auth.reset_password", error="password_mismatch", token_hash=token_hash))

    if not supabase:
        return redirect(url_for("auth.login", success="password_reset_success"))

    try:
        # 1. token_hash가 넘어온 경우 OTP 검증으로 세션 확립
        if token_hash:
            try:
                v_resp = supabase.auth.verify_otp({
                    "token_hash": token_hash,
                    "type": "recovery"
                })
                if v_resp.session:
                    access_token = v_resp.session.access_token
                    refresh_token = getattr(v_resp.session, "refresh_token", "")
                    session["user_id"] = str(v_resp.user.id)
                    session["access_token"] = access_token
                    session["refresh_token"] = refresh_token
            except Exception as ve:
                logger.warning(f"비밀번호 재설정 POST 토큰 검증 예외: {ve}")

        # 2. 클라이언트 전달 또는 세션의 access_token 설정
        current_token = access_token or session.get("access_token")
        current_refresh = refresh_token or session.get("refresh_token", "")
        if current_token:
            try:
                supabase.auth.set_session(current_token, current_refresh)
            except Exception as se:
                logger.warning(f"set_session 예외: {se}")

        # 3. 사용자 비밀번호 갱신
        try:
            supabase.auth.update_user({"password": password})
        except Exception as ue:
            admin_client = get_supabase_admin_client()
            user_id = session.get("user_id")
            if admin_client and user_id:
                admin_client.auth.admin.update_user_by_id(user_id, {"password": password})
            else:
                raise ue

        # 임시 토큰 정리
        session.pop("access_token", None)
        session.pop("refresh_token", None)

        return redirect(url_for("auth.login", success="password_reset_success"))

    except Exception as e:
        logger.error(f"비밀번호 재설정 처리 실패: {e}")
        return redirect(url_for("auth.reset_password", error="reset_failed", token_hash=token_hash))


# =====================================================
# 마이페이지 및 회원 관리
# =====================================================
@auth_bp.route("/auth/mypage", methods=["GET", "POST"])
@auth_bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    """마이페이지 라우트 (로그인 필수, 프로필 조회 및 정보 수정)"""
    user_id = session.get("user_id")
    user = session.get("user") or {}
    supabase = get_supabase_client()
    admin_client = get_supabase_admin_client()
    client = admin_client or supabase

    # [POST] 내 정보 수정 폼 처리
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        address_detail = request.form.get("address_detail", "").strip()

        update_payload = {}
        if full_name:
            update_payload["full_name"] = full_name
        update_payload["phone"] = phone

        # 기본 배송지 주소 합성 (기본주소 + 상세주소)
        combined_address = f"{address} {address_detail}".strip() if address else ""

        if client and user_id:
            try:
                # profiles 테이블 컬럼 확인 후 안전하게 업데이트
                client.table("profiles").update(update_payload).eq("id", user_id).execute()
                
                # 세션 데이터 동기화
                if full_name:
                    user["name"] = full_name
                user["phone"] = phone
                user["address"] = address
                user["address_detail"] = address_detail
                session["user"] = user

                # auth.users 메타데이터에도 배송지 및 이름 보관
                if admin_client:
                    try:
                        admin_client.auth.admin.update_user_by_id(user_id, {
                            "user_metadata": {
                                "full_name": full_name or user.get("name"),
                                "phone": phone,
                                "address": address,
                                "address_detail": address_detail,
                                "shipping_address": combined_address
                            }
                        })
                    except Exception as me:
                        logger.warning(f"메타데이터 배송지 저장 경고: {me}")

                return redirect(url_for("auth.mypage", success="profile_updated"))
            except Exception as e:
                logger.error(f"프로필 수정 실패: {e}")
                return redirect(url_for("auth.mypage", error="update_failed"))

    # [GET] Supabase profiles 및 메타데이터에서 최신 정보 조회
    error_msg, success_msg, error_code, success_code = get_alert_messages()

    if user_id and client:
        try:
            # 1. profiles 테이블 조회
            prof_resp = client.table("profiles").select("*").eq("id", user_id).execute()
            if not prof_resp.data:
                logger.info(f"마이페이지 접근 중 삭제된 계정 감지: user_id={user_id} -> 세션 파기")
                session.clear()
                return redirect(url_for("auth.login", error="login_required"))

            profile = prof_resp.data[0]
            user["name"] = profile.get("full_name") or user.get("name")
            user["email"] = profile.get("email") or user.get("email")
            user["phone"] = profile.get("phone") or user.get("phone") or ""
            user["grade"] = profile.get("grade") or user.get("grade", "BRONZE")
            user["role"] = profile.get("role") or user.get("role", "customer")

            # 2. auth.users 메타데이터에서 기본 배송지 정보 로드
            if admin_client:
                try:
                    auth_user_resp = admin_client.auth.admin.get_user_by_id(user_id)
                    if auth_user_resp and auth_user_resp.user:
                        meta = auth_user_resp.user.user_metadata or {}
                        app_meta = getattr(auth_user_resp.user, "app_metadata", {}) or {}
                        user["provider"] = app_meta.get("provider") or user.get("provider") or "email"
                        user["address"] = meta.get("address") or user.get("address") or ""
                        user["address_detail"] = meta.get("address_detail") or user.get("address_detail") or ""
                        if not user.get("phone"):
                            user["phone"] = meta.get("phone") or ""
                        if not user.get("name") or user.get("name") == "회원":
                            meta_name = meta.get("full_name") or meta.get("name")
                            if meta_name:
                                user["name"] = meta_name
                except Exception as ae:
                    logger.warning(f"auth.users 메타데이터 조회 경고: {ae}")

            if not user.get("name") and user.get("email"):
                user["name"] = user["email"].split("@")[0]
            session["user"] = user
        except Exception as e:
            logger.warning(f"마이페이지 프로필 로드 경고: {e}")

    # 3. 마이페이지 장바구니 데이터 조회
    cart_items = []
    cart_total = 0
    try:
        if supabase and user_id:
            cart_resp = supabase.table("carts")\
                .select("id, product_id, option_id, quantity, products(id, name, price, thumbnail_url), product_options(id, color, size, stock)")\
                .eq("user_id", user_id)\
                .execute()
            
            if cart_resp.data:
                for cart in cart_resp.data:
                    product = cart.get("products") or {}
                    option = cart.get("product_options") or {}
                    quantity = int(cart.get("quantity") or 1)
                    product_price = int(product.get("price") or 0)
                    item_total = product_price * quantity
                    cart_total += item_total
                    
                    cart_items.append({
                        "cart_id": cart.get("id"),
                        "product_id": product.get("id"),
                        "option_id": option.get("id"),
                        "product_name": product.get("name"),
                        "color": option.get("color"),
                        "size": option.get("size"),
                        "price": product_price,
                        "quantity": quantity,
                        "item_total": item_total,
                        "formatted_price": f"{product_price:,}원",
                        "formatted_item_total": f"{item_total:,}원",
                        "thumbnail_url": product.get("thumbnail_url") or f"https://picsum.photos/seed/{product.get('id', 'item')}/200/200"
                    })
    except Exception as e:
        logger.warning(f"마이페이지 장바구니 조회 경고: {e}")

    return render_template(
        "auth/mypage.html",
        user=user,
        error_message=error_msg,
        success_message=success_msg,
        cart_items=cart_items,
        cart_total=cart_total,
        formatted_cart_total=f"{cart_total:,}원"
    )


@auth_bp.route("/mypage/change-password", methods=["POST"])
@auth_bp.route("/auth/mypage/change-password", methods=["POST"])
@login_required
def change_password():
    """
    마이페이지 비밀번호 변경 처리 라우트 (POST /mypage/change-password)
    - 기존 비밀번호 검증 (재로그인 방식)
    - 새 비밀번호 검증 (최소 6자 이상, 확인 비밀번호 일치)
    - 새 비밀번호와 기존 비밀번호 동일 여부 검사
    - Supabase update_user_by_id() 호출
    """
    user_id = session.get("user_id")
    user = session.get("user") or {}
    email = user.get("email")

    if not user_id:
        return redirect(url_for("auth.login", error="login_required"))

    # 이메일 주소가 세션에 없다면 DB에서 조회
    if not email:
        supabase = get_supabase_client()
        admin_client = get_supabase_admin_client()
        client = admin_client or supabase
        if client:
            try:
                prof_resp = client.table("profiles").select("email").eq("id", user_id).execute()
                if prof_resp.data:
                    email = prof_resp.data[0].get("email")
            except Exception:
                pass

    current_password = request.form.get("current_password", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    # 필수값 입력 확인
    if not current_password or not new_password or not confirm_password:
        return redirect(url_for("auth.mypage", error="missing_fields"))

    # 1. 기존 비밀번호 검증 (Supabase 재로그인 방식으로 확인)
    supabase = get_supabase_client()
    if not supabase or not email:
        return redirect(url_for("auth.mypage", error="update_failed"))

    try:
        supabase.auth.sign_in_with_password({
            "email": email,
            "password": current_password
        })
    except Exception as e:
        logger.warning(f"현재 비밀번호 불일치: email={email}, err={e}")
        return redirect(url_for("auth.mypage", error="current_password_incorrect"))

    # 2. 새 비밀번호와 기존 비밀번호 동일 여부 확인
    if new_password == current_password:
        return redirect(url_for("auth.mypage", error="password_same_as_old"))

    # 3. 새 비밀번호 유효성 검사 (Day 4 조건: 최소 6자 이상)
    if len(new_password) < 6:
        return redirect(url_for("auth.mypage", error="password_too_short"))

    # 4. 새 비밀번호 일치 확인
    if new_password != confirm_password:
        return redirect(url_for("auth.mypage", error="password_mismatch"))

    # 5. Supabase update_user_by_id()를 통한 새 비밀번호 반영
    admin_client = get_supabase_admin_client()
    if admin_client:
        try:
            admin_client.auth.admin.update_user_by_id(user_id, {"password": new_password})
            logger.info(f"비밀번호 변경 성공: user_id={user_id}")
            return redirect(url_for("auth.mypage", success="password_changed"))
        except Exception as ue:
            logger.error(f"update_user_by_id 실패: {ue}")
            return redirect(url_for("auth.mypage", error="update_failed"))
    else:
        return redirect(url_for("auth.mypage", error="update_failed"))


@auth_bp.route("/auth/delete-account", methods=["GET", "POST"])
@auth_bp.route("/delete-account", methods=["GET", "POST"])
def delete_account():
    """
    회원 탈퇴 / 소셜 연동 해제 처리 라우트
    - 카카오, 네이버, 구글 등 소셜 연동 계정인 경우:
      기존 이메일 계정(auth.users 및 이메일 profiles)을 삭제하지 않고,
      해당 소셜 세션 및 소셜 전용 프로필만 정리(연동 해제)합니다.
    - 일반 이메일 가입 계정인 경우에만:
      본인 요청 시에만 Auth 및 프로필을 삭제합니다.
    """
    # 1. user_id 및 provider 확인
    user_id = session.get("user_id")
    user_obj = session.get("user") or {}
    if not user_id and isinstance(user_obj, dict) and user_obj.get("id"):
        user_id = user_obj["id"]

    if not user_id:
        return redirect(url_for("auth.login", error="login_required"))

    provider = user_obj.get("provider", "email")
    admin_client = get_supabase_admin_client()
    supabase = get_supabase_client()
    db_client = admin_client or supabase

    try:
        # 소셜 연동(카카오, 네이버, 구글) 및 일반 이메일 회원 모두 완전 탈퇴 처리
        # 1. profiles 및 연관 데이터 정리
        if db_client:
            try:
                db_client.table("profiles").delete().eq("id", user_id).execute()
            except Exception as pe:
                logger.warning(f"profiles 삭제 경고: {pe}")

        # 2. Supabase Auth(auth.users) 계정 완전 삭제 (대시보드 Users 목록에서 영구 제거)
        if admin_client:
            try:
                admin_client.auth.admin.delete_user(user_id)
                logger.info(f"Supabase auth.users 삭제 완료: user_id={user_id}, provider={provider}")
            except Exception as ae:
                logger.warning(f"auth.admin.delete_user 경고: {ae}")

        # 3. Supabase 클라이언트 로그아웃
        if supabase:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass

        # 4. 세션 데이터 완전 초기화 및 브라우저 세션 쿠키 파기
        session.clear()
        response = redirect(url_for("auth.login", success="account_deleted"))
        session_cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
        response.delete_cookie(session_cookie_name)
        return response

    except Exception as e:
        logger.error(f"회원 탈퇴 처리 실패: {e}")
        # 세션은 안전하게 로그아웃 처리 후 로그인 페이지로 이동
        session.clear()
        response = redirect(url_for("auth.login", error="delete_failed"))
        session_cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
        response.delete_cookie(session_cookie_name)
        return response


@auth_bp.route("/auth/logout", methods=["GET"])
@auth_bp.route("/logout", methods=["GET"])
def logout():
    """로그아웃 처리"""
    supabase = get_supabase_client()
    if supabase and session.get("access_token"):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass

    session.clear()
    response = redirect(url_for("auth.login", success="logged_out"))
    session_cookie_name = current_app.config.get("SESSION_COOKIE_NAME", "session")
    response.delete_cookie(session_cookie_name)
    return response


# =====================================================
# Supabase OAuth 소셜 로그인 (카카오 / MS Azure / callback)
# =====================================================
@auth_bp.route("/auth/kakao", methods=["GET"])
@auth_bp.route("/kakao", methods=["GET"])
def kakao_login():
    """
    카카오 소셜 로그인 시작 라우트
    - Supabase의 sign_in_with_oauth(provider='kakao')를 호출하여 인증 URL을 받아 리다이렉트합니다.
    - redirect_to는 환경변수 SITE_URL + '/auth/callback'을 사용합니다.
    - PKCE code_verifier를 Flask 세션에 보관하여 콜백에서 세션 교환 시 사용합니다.
    """
    # 기존 로그인 세션이 남아있다면 초기화
    session.pop("user_id", None)
    session.pop("user", None)
    session.pop("access_token", None)
    session.pop("refresh_token", None)

    supabase = get_supabase_client()
    if not supabase:
        return redirect(url_for("auth.login", error="social_config_missing"))

    redirect_to = f"{get_site_url()}/auth/callback"
    try:
        # dict 인자 및 keyword arguments 호환성 처리
        # scope에 이메일, 닉네임, 프로필 사진을 명시하여 첫 가입 동의창에서 모든 항목을 한번에 받도록 설정
        res = supabase.auth.sign_in_with_oauth({
            "provider": "kakao",
            "options": {
                "redirect_to": redirect_to,
                "scopes": "account_email profile_nickname profile_image",
                "query_params": {
                    "scope": "account_email,profile_nickname,profile_image"
                }
            }
        })

        # PKCE flow code_verifier 저장 (GoTrue client storage)
        storage = getattr(supabase.auth, "_storage", None)
        if storage and hasattr(storage, "get_item"):
            verifier = storage.get_item("supabase.auth.token-code-verifier")
            if verifier:
                session["code_verifier"] = verifier

        oauth_url = getattr(res, "url", None) or (res.get("url") if isinstance(res, dict) else None)
        if oauth_url:
            return redirect(oauth_url)
        return redirect(url_for("auth.login", error="social_token_failed"))
    except Exception as e:
        logger.error(f"카카오 OAuth 요청 실패: {e}")
        return redirect(url_for("auth.login", error="social_token_failed"))


@auth_bp.route("/auth/azure", methods=["GET"])
@auth_bp.route("/auth/ms", methods=["GET"])
@auth_bp.route("/auth/microsoft", methods=["GET"])
def ms_login():
    """
    MS(Azure) 소셜 로그인 라우트 (카카오와 동일한 패턴)
    - supabase.auth.sign_in_with_oauth(provider='azure') 호출
    """
    supabase = get_supabase_client()
    if not supabase:
        return redirect(url_for("auth.login", error="social_config_missing"))

    redirect_to = f"{get_site_url()}/auth/callback"
    try:
        res = supabase.auth.sign_in_with_oauth({
            "provider": "azure",
            "options": {
                "redirect_to": redirect_to
            }
        })
        storage = getattr(supabase.auth, "_storage", None)
        if storage and hasattr(storage, "get_item"):
            verifier = storage.get_item("supabase.auth.token-code-verifier")
            if verifier:
                session["code_verifier"] = verifier

        oauth_url = getattr(res, "url", None) or (res.get("url") if isinstance(res, dict) else None)
        if oauth_url:
            return redirect(oauth_url)
        return redirect(url_for("auth.login", error="social_token_failed"))
    except Exception as e:
        logger.error(f"MS OAuth 요청 실패: {e}")
        return redirect(url_for("auth.login", error="social_token_failed"))


@auth_bp.route("/auth/google", methods=["GET"])
@auth_bp.route("/google", methods=["GET"])
def google_login():
    """
    구글 소셜 로그인 라우트 (Supabase OAuth 연동)
    - supabase.auth.sign_in_with_oauth(provider='google') 호출
    - redirect_to: SITE_URL + '/auth/callback'
    """
    supabase = get_supabase_client()
    if not supabase:
        return redirect(url_for("auth.login", error="social_config_missing"))

    redirect_to = f"{get_site_url()}/auth/callback"
    try:
        res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": redirect_to,
                "scopes": "openid email profile",
                "query_params": {
                    "prompt": "select_account"
                }
            }
        })
        storage = getattr(supabase.auth, "_storage", None)
        if storage and hasattr(storage, "get_item"):
            verifier = storage.get_item("supabase.auth.token-code-verifier")
            if verifier:
                session["code_verifier"] = verifier

        oauth_url = getattr(res, "url", None) or (res.get("url") if isinstance(res, dict) else None)
        if oauth_url:
            return redirect(oauth_url)
        return redirect(url_for("auth.login", error="social_token_failed"))
    except Exception as e:
        logger.error(f"구글 OAuth 요청 실패: {e}")
        return redirect(url_for("auth.login", error="social_token_failed"))


@auth_bp.route("/auth/callback", methods=["GET"])
@auth_bp.route("/callback", methods=["GET"])
def auth_callback():
    """
    Supabase OAuth 공통 콜백 라우트 (카카오, MS, 기타 소셜)
    - Supabase로부터 전달된 authorization code 또는 토큰을 세션으로 교환
    - 사용자 정보 및 profiles 동기화 후 마이페이지로 이동
    """
    err = request.args.get("error")
    err_desc = request.args.get("error_description", "")
    err_code = request.args.get("error_code", "")
    if err:
        logger.warning(f"OAuth 콜백 error 파라미터 감지: err={err}, code={err_code}, desc={err_desc}")
        # 카카오 사용자가 직접 취소한 경우(access_denied)에만 social_cancelled로 처리
        if err == "access_denied" or "cancel" in err_desc.lower():
            return redirect(url_for("auth.login", error="social_cancelled"))
        # 서버 오류나 일시적 문제의 경우 토큰 재시도 안내
        logger.error(f"OAuth 인증 실패: {err} ({err_desc})")
        return redirect(url_for("auth.login", error="social_token_failed"))

    code = request.args.get("code")
    access_token = request.args.get("access_token")
    supabase = get_supabase_client()
    admin_client = get_supabase_admin_client()

    if not supabase:
        return redirect(url_for("auth.login", error="social_config_missing"))

    auth_user = None
    auth_session = None

    try:
        # 1. Authorization Code가 있는 경우 (PKCE / OAuth 교환)
        if code:
            code_verifier = session.pop("code_verifier", None)
            exchange_params = {"auth_code": code}
            if code_verifier:
                exchange_params["code_verifier"] = code_verifier

            # Supabase GoTrue storage에 code_verifier 복원
            storage = getattr(supabase.auth, "_storage", None)
            if storage and hasattr(storage, "set_item") and code_verifier:
                storage.set_item("supabase.auth.token-code-verifier", code_verifier)

            try:
                res = supabase.auth.exchange_code_for_session(exchange_params)
                auth_user = getattr(res, "user", None)
                auth_session = getattr(res, "session", None)
            except Exception as ce:
                logger.warning(f"exchange_code_for_session 실패: {ce}")

        # 2. 이미 access_token이 전달된 경우 (Implicit flow)
        if not auth_user and access_token:
            try:
                user_res = supabase.auth.get_user(access_token)
                auth_user = getattr(user_res, "user", None)
            except Exception as ae:
                logger.warning(f"get_user 실패: {ae}")

        # 3. 브라우저 해시(#access_token=...) 대응 (클라이언트 JS에서 쿼리로 전달할 수 있는 안전 장치)
        if not auth_user and not code and not access_token:
            # 해시 프래그먼트 처리를 위한 헬퍼 스크립트 렌더링
            return """
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"><title>로그인 처리 중...</title></head>
            <body>
            <script>
                if (window.location.hash) {
                    var hash = window.location.hash.substring(1);
                    var params = new URLSearchParams(hash);
                    var access_token = params.get('access_token');
                    var refresh_token = params.get('refresh_token');
                    var error = params.get('error');
                    var error_desc = params.get('error_description');
                    if (access_token) {
                        window.location.href = '/auth/callback?access_token=' + encodeURIComponent(access_token) + (refresh_token ? '&refresh_token=' + encodeURIComponent(refresh_token) : '');
                    } else if (error === 'access_denied') {
                        window.location.href = '/auth/login?error=social_cancelled';
                    } else if (error) {
                        console.error('OAuth hash error:', error, error_desc);
                        window.location.href = '/auth/login?error=social_token_failed';
                    } else {
                        window.location.href = '/auth/login?error=social_token_failed';
                    }
                } else {
                    window.location.href = '/auth/login?error=social_token_failed';
                }
            </script>
            <p style="text-align:center; padding: 50px; font-family: sans-serif;">로그인 정보를 처리 중입니다. 잠시만 기다려주세요...</p>
            </body>
            </html>
            """

        if not auth_user:
            return redirect(url_for("auth.login", error="social_token_failed"))

        user_id = str(auth_user.id)
        user_meta = getattr(auth_user, "user_metadata", {}) or {}
        user_email = getattr(auth_user, "email", "") or user_meta.get("email") or f"user_{user_id[:6]}@vibe.kr"
        user_name = user_meta.get("full_name") or user_meta.get("name") or user_meta.get("user_name") or user_email.split("@")[0]
        user_avatar = user_meta.get("avatar_url") or user_meta.get("picture") or ""
        provider = getattr(auth_user, "app_metadata", {}).get("provider") or "kakao"

        user_grade = "SILVER"
        user_role = "customer"

        # profiles 테이블 동기화
        db_client = admin_client or supabase
        if db_client:
            try:
                prof_resp = db_client.table("profiles").select("*").eq("id", user_id).execute()
                if prof_resp.data:
                    profile = prof_resp.data[0]
                    user_grade = profile.get("grade", "SILVER")
                    user_role = profile.get("role", "customer")
                    user_name = profile.get("full_name") or user_name
                    user_avatar = profile.get("avatar_url") or user_avatar
                else:
                    db_client.table("profiles").upsert({
                        "id": user_id,
                        "email": user_email,
                        "full_name": user_name,
                        "avatar_url": user_avatar,
                        "grade": "SILVER",
                        "role": "customer"
                    }).execute()
            except Exception as pe:
                logger.warning(f"콜백 프로필 동기화 경고: {pe}")

        user_data = {
            "id": user_id,
            "email": user_email,
            "name": user_name,
            "avatar_url": user_avatar,
            "grade": user_grade,
            "role": user_role,
            "provider": provider
        }

        session["user_id"] = user_id
        session["user"] = user_data
        if auth_session and hasattr(auth_session, "access_token"):
            session["access_token"] = auth_session.access_token
            session["refresh_token"] = getattr(auth_session, "refresh_token", None)

        return redirect(url_for("auth.mypage", success="social_login_success"))

    except Exception as e:
        logger.error(f"OAuth 콜백 처리 예외: {e}")
        return redirect(url_for("auth.login", error="social_token_failed"))


# =====================================================
# 소셜 간편 로그인 (카카오 / 네이버 / 구글)
# =====================================================
def http_post_form_json(url: str, form_data: dict, headers: dict = None) -> dict:
    """x-www-form-urlencoded 형식으로 POST 요청을 보내고 JSON 응답을 반환합니다."""
    encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")
    req_headers = {
        "User-Agent": "VIBE-FASHION-OAuth/1.0",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        "Accept": "application/json"
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def http_get_json(url: str, headers: dict = None) -> dict:
    """GET 요청을 보내고 JSON 응답을 반환합니다."""
    req_headers = {
        "User-Agent": "VIBE-FASHION-OAuth/1.0",
        "Accept": "application/json"
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body)


def get_social_redirect_uri(provider: str) -> str:
    """소셜 로그인 콜백 리다이렉트 URI를 생성합니다."""
    site_url = get_site_url()
    return f"{site_url}/auth/social-callback/{provider}"


@auth_bp.route("/auth/social-login/<provider>")
@auth_bp.route("/social-login/<provider>")
def social_login(provider):
    """
    카카오, 네이버, 구글 실제 OAuth 인증창으로 리다이렉트합니다.
    API 키가 설정되지 않은 경우 오류 안내 메시지를 표시합니다.
    """
    provider = provider.lower()
    if provider not in ["kakao", "naver", "google"]:
        return redirect(url_for("auth.login", error="unsupported_provider"))

    redirect_uri = get_social_redirect_uri(provider)
    state = secrets.token_urlsafe(16)
    session[f"oauth_state_{provider}"] = state

    # [1] 카카오톡 로그인 연동
    if provider == "kakao":
        kakao_client_id = os.getenv("KAKAO_CLIENT_ID")
        if not kakao_client_id:
            logger.warning("KAKAO_CLIENT_ID 환경변수가 설정되지 않았습니다.")
            return redirect(url_for("auth.login", error="social_config_missing"))

        kakao_scope = "account_email,profile_nickname,profile_image"
        auth_url = (
            f"https://kauth.kakao.com/oauth/authorize?response_type=code"
            f"&client_id={kakao_client_id}"
            f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
            f"&scope={kakao_scope}"
            f"&state={state}"
        )
        return redirect(auth_url)

    # [2] 네이버 아이디 로그인 연동
    if provider == "naver":
        naver_client_id = os.getenv("NAVER_CLIENT_ID")
        if not naver_client_id:
            logger.warning("NAVER_CLIENT_ID 환경변수가 설정되지 않았습니다.")
            return redirect(url_for("auth.login", error="social_config_missing"))

        auth_url = (
            f"https://nid.naver.com/oauth2.0/authorize?response_type=code"
            f"&client_id={naver_client_id}"
            f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
            f"&state={state}"
        )
        return redirect(auth_url)

    # [3] 구글 로그인 연동
    if provider == "google":
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        if not google_client_id:
            logger.warning("GOOGLE_CLIENT_ID 환경변수가 설정되지 않았습니다.")
            return redirect(url_for("auth.login", error="social_config_missing"))

        scope = urllib.parse.quote("openid email profile")
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code"
            f"&client_id={google_client_id}"
            f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
            f"&scope={scope}"
            f"&state={state}"
            f"&access_type=online"
            f"&prompt=select_account"
        )
        return redirect(auth_url)

    return redirect(url_for("auth.login", error="unsupported_provider"))


@auth_bp.route("/auth/social-callback/<provider>")
@auth_bp.route("/social-callback/<provider>")
def social_callback(provider):
    """
    실제 소셜 로그인 콜백 핸들러
    - 각 제공자(카카오, 네이버, 구글)로부터 authorization code를 받아 토큰을 발급받고,
    - 실제 사용자 프로필(ID, 이름/닉네임, 이메일, 프로필 이미지)을 조회하여
    - Supabase 및 Flask 세션에 안전하게 연동 및 로그인 처리합니다.
    """
    provider = provider.lower()
    if provider not in ["kakao", "naver", "google"]:
        return redirect(url_for("auth.login", error="unsupported_provider"))

    # 사용자 취소 또는 오류 파라미터 확인
    err = request.args.get("error")
    if err:
        logger.warning(f"{provider} 소셜 로그인 취소 또는 오류: {err} ({request.args.get('error_description')})")
        return redirect(url_for("auth.login", error="social_cancelled"))

    code = request.args.get("code")
    if not code:
        logger.error(f"{provider} 콜백에 code 파라미터가 없습니다.")
        return redirect(url_for("auth.login", error="social_token_failed"))

    redirect_uri = get_social_redirect_uri(provider)
    user_info = None

    try:
        # -----------------------------------------------------------------
        # 1. 카카오톡 실제 토큰 발급 및 사용자 정보 조회
        # -----------------------------------------------------------------
        if provider == "kakao":
            kakao_client_id = os.getenv("KAKAO_CLIENT_ID")
            kakao_client_secret = os.getenv("KAKAO_CLIENT_SECRET")
            if not kakao_client_id:
                return redirect(url_for("auth.login", error="social_config_missing"))

            token_data = {
                "grant_type": "authorization_code",
                "client_id": kakao_client_id,
                "redirect_uri": redirect_uri,
                "code": code
            }
            if kakao_client_secret:
                token_data["client_secret"] = kakao_client_secret

            token_res = http_post_form_json("https://kauth.kakao.com/oauth/token", token_data)
            access_token = token_res.get("access_token")
            if not access_token:
                logger.error(f"카카오 토큰 발급 실패 응답: {token_res}")
                return redirect(url_for("auth.login", error="social_token_failed"))

            # 사용자 정보 조회 API 호출
            me_res = http_get_json(
                "https://kapi.kakao.com/v2/user/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            social_id = str(me_res.get("id"))
            kakao_account = me_res.get("kakao_account", {})
            profile = kakao_account.get("profile", {}) or me_res.get("properties", {}) or {}

            name = profile.get("nickname") or f"카카오회원_{social_id[:6]}"
            email = kakao_account.get("email") or f"kakao_{social_id}@kakao.user"
            avatar_url = profile.get("profile_image_url") or profile.get("thumbnail_image_url") or ""

            user_info = {
                "social_id": social_id,
                "email": email,
                "name": name,
                "avatar_url": avatar_url,
                "provider": "kakao"
            }

        # -----------------------------------------------------------------
        # 2. 네이버 실제 토큰 발급 및 사용자 정보 조회
        # -----------------------------------------------------------------
        elif provider == "naver":
            naver_client_id = os.getenv("NAVER_CLIENT_ID")
            naver_client_secret = os.getenv("NAVER_CLIENT_SECRET")
            if not naver_client_id or not naver_client_secret:
                return redirect(url_for("auth.login", error="social_config_missing"))

            state = request.args.get("state", "")
            token_params = {
                "grant_type": "authorization_code",
                "client_id": naver_client_id,
                "client_secret": naver_client_secret,
                "code": code,
                "state": state
            }
            token_url = f"https://nid.naver.com/oauth2.0/token?{urllib.parse.urlencode(token_params)}"
            token_res = http_get_json(token_url)
            access_token = token_res.get("access_token")
            if not access_token:
                logger.error(f"네이버 토큰 발급 실패 응답: {token_res}")
                return redirect(url_for("auth.login", error="social_token_failed"))

            # 네이버 사용자 프로필 조회
            me_res = http_get_json(
                "https://openapi.naver.com/v1/nid/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            naver_resp = me_res.get("response", {})
            social_id = str(naver_resp.get("id"))
            if not social_id:
                logger.error(f"네이버 사용자 정보 조회 실패 응답: {me_res}")
                return redirect(url_for("auth.login", error="social_user_failed"))

            name = naver_resp.get("name") or naver_resp.get("nickname") or f"네이버회원_{social_id[:6]}"
            email = naver_resp.get("email") or f"naver_{social_id}@naver.user"
            avatar_url = naver_resp.get("profile_image") or ""

            user_info = {
                "social_id": social_id,
                "email": email,
                "name": name,
                "avatar_url": avatar_url,
                "provider": "naver"
            }

        # -----------------------------------------------------------------
        # 3. 구글 실제 토큰 발급 및 사용자 정보 조회
        # -----------------------------------------------------------------
        elif provider == "google":
            google_client_id = os.getenv("GOOGLE_CLIENT_ID")
            google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
            if not google_client_id or not google_client_secret:
                return redirect(url_for("auth.login", error="social_config_missing"))

            token_data = {
                "code": code,
                "client_id": google_client_id,
                "client_secret": google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }
            token_res = http_post_form_json("https://oauth2.googleapis.com/token", token_data)
            access_token = token_res.get("access_token")
            if not access_token:
                logger.error(f"구글 토큰 발급 실패 응답: {token_res}")
                return redirect(url_for("auth.login", error="social_token_failed"))

            # 구글 사용자 프로필 조회
            me_res = http_get_json(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            social_id = str(me_res.get("id"))
            if not social_id:
                logger.error(f"구글 사용자 정보 조회 실패 응답: {me_res}")
                return redirect(url_for("auth.login", error="social_user_failed"))

            name = me_res.get("name") or f"구글회원_{social_id[:6]}"
            email = me_res.get("email") or f"google_{social_id}@google.user"
            avatar_url = me_res.get("picture") or ""

            user_info = {
                "social_id": social_id,
                "email": email,
                "name": name,
                "avatar_url": avatar_url,
                "provider": "google"
            }

    except Exception as e:
        logger.error(f"{provider} 소셜 로그인 인증 처리 중 예외 발생: {e}")
        return redirect(url_for("auth.login", error="social_token_failed"))

    if not user_info:
        return redirect(url_for("auth.login", error="social_user_failed"))

    # -----------------------------------------------------------------
    # 4. Supabase DB 및 Auth 사용자 연동
    # -----------------------------------------------------------------
    admin_client = get_supabase_admin_client()
    supabase = get_supabase_client()
    user_id = None

    if admin_client:
        try:
            # 1) 이메일로 기존 Auth 유저 검색
            existing_user_id = None
            try:
                users_resp = admin_client.auth.admin.list_users()
                user_list = getattr(users_resp, "users", users_resp if isinstance(users_resp, list) else [])
                for u in user_list:
                    if getattr(u, "email", None) == user_info["email"]:
                        existing_user_id = str(u.id)
                        break
            except Exception as le:
                logger.warning(f"소셜 로그인 사용자 목록 조회 예외: {le}")

            # 2) 계정이 없으면 신규 Auth 사용자 생성
            if not existing_user_id:
                try:
                    create_resp = admin_client.auth.admin.create_user({
                        "email": user_info["email"],
                        "email_confirm": True,
                        "user_metadata": {
                            "full_name": user_info["name"],
                            "avatar_url": user_info["avatar_url"],
                            "provider": provider
                        }
                    })
                    if create_resp and hasattr(create_resp, "user") and create_resp.user:
                        existing_user_id = str(create_resp.user.id)
                except Exception as ce:
                    logger.warning(f"소셜 로그인 Auth 계정 생성 중 예외 (중복 등): {ce}")

            if existing_user_id:
                user_id = existing_user_id
        except Exception as ae:
            logger.error(f"소셜 로그인 Supabase Auth 처리 실패: {ae}")

    # Auth 계정을 찾거나 생성하지 못한 경우 고유 결정론적 UUID 사용
    if not user_id:
        user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{provider}:{user_info['social_id']}"))

    # profiles 테이블 동기화
    db_client = admin_client or supabase
    user_grade = "SILVER"
    user_role = "customer"

    if db_client:
        try:
            # 기존 프로필 조회하여 기존 등급 유지
            prof_resp = db_client.table("profiles").select("*").eq("id", user_id).execute()
            if prof_resp.data:
                profile = prof_resp.data[0]
                user_grade = profile.get("grade", "SILVER")
                user_role = profile.get("role", "customer")
            else:
                db_client.table("profiles").upsert({
                    "id": user_id,
                    "email": user_info["email"],
                    "full_name": user_info["name"],
                    "avatar_url": user_info["avatar_url"],
                    "grade": "SILVER",
                    "role": "customer"
                }).execute()
        except Exception as pe:
            logger.warning(f"소셜 로그인 profiles 동기화 경고: {pe}")

    # Flask 세션에 사용자 정보 저장
    session_user_data = {
        "id": user_id,
        "email": user_info["email"],
        "name": user_info["name"],
        "avatar_url": user_info["avatar_url"],
        "grade": user_grade,
        "role": user_role,
        "provider": provider
    }
    session["user_id"] = user_id
    session["user"] = session_user_data

    logger.info(f"{provider} 소셜 로그인 성공: {user_info['name']} ({user_info['email']})")
    return redirect(url_for("auth.mypage", success="social_login_success"))


# 패키지 임포트 호환성 지원 (app.routes.auth 또는 routes.auth)
if "app.routes" not in sys.modules and "routes" in sys.modules:
    sys.modules["app.routes"] = sys.modules["routes"]
    sys.modules["app.routes.auth"] = sys.modules[__name__]

