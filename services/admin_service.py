"""
=====================================================
관리자 서비스 및 RBAC 권한/인증 모듈 (admin_service.py)
=====================================================
온라인 쇼핑몰 관리자 전용 인증, 역할 기반 접근 제어(RBAC),
관리자 계정 관리, 감사 활동 로그(Activity Logs), 시스템 설정을 담당합니다.

Supabase 클라이언트와 연동하며, 원격 테이블 미생성 시
로컬 SQLite(instance/admin.db)로 자동 폴백하여 무중단 동작을 보장합니다.
"""

import os
import sqlite3
import uuid
import json
import logging
from datetime import datetime, timezone
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, request, redirect, url_for, abort, render_template

logger = logging.getLogger(__name__)

# =====================================================
# 1. RBAC 역할 및 권한 매트릭스 정의
# =====================================================
ROLES = {
    "SUPER_ADMIN": "최고 관리자",
    "ADMIN": "운영 관리자",
    "STAFF": "상품/주문 담당자",
}

PERMISSIONS = {
    # 대시보드
    "dashboard_view": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    # 회원 관리
    "user_view": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "user_edit": ["SUPER_ADMIN", "ADMIN"],
    "user_delete": ["SUPER_ADMIN"],
    # 상품 관리
    "product_view": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "product_create": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "product_edit": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "product_delete": ["SUPER_ADMIN"],  # STAFF 불가, ADMIN 제한
    # 주문 관리
    "order_view": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "order_status_change": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "order_cancel": ["SUPER_ADMIN", "ADMIN"],  # STAFF 제한
    "order_refund": ["SUPER_ADMIN", "ADMIN"],  # STAFF 제한
    # 재고 관리
    "inventory_view": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    "inventory_edit": ["SUPER_ADMIN", "ADMIN", "STAFF"],
    # 통계
    "stats_view": ["SUPER_ADMIN", "ADMIN"],    # STAFF 제한
    # 관리자 계정 관리
    "admin_manage": ["SUPER_ADMIN"],
    # 시스템 설정
    "settings_manage": ["SUPER_ADMIN"],
    # 활동 로그
    "logs_view": ["SUPER_ADMIN", "ADMIN"],
}


def has_admin_permission(role: str, permission: str) -> bool:
    """특정 역할이 해당 권한을 가지고 있는지 검사"""
    if not role:
        return False
    allowed_roles = PERMISSIONS.get(permission, [])
    return role in allowed_roles


# =====================================================
# 2. 로컬 SQLite 폴백 및 데이터베이스 초기화
# =====================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
SQLITE_DB_PATH = os.path.join(INSTANCE_DIR, "admin.db")


def get_sqlite_conn():
    """로컬 SQLite 연결 객체 반환"""
    os.makedirs(INSTANCE_DIR, exist_ok=True)
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_sqlite_db():
    """SQLite에 관리자 관련 테이블 생성 및 기본 계정 시딩"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('SUPER_ADMIN', 'ADMIN', 'STAFF')),
        status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'locked')),
        must_change_password INTEGER NOT NULL DEFAULT 0,
        last_login_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs (
        id TEXT PRIMARY KEY,
        admin_id TEXT,
        admin_username TEXT NOT NULL,
        admin_name TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        details TEXT,
        result TEXT NOT NULL DEFAULT '성공',
        ip_address TEXT,
        created_at TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        description TEXT,
        updated_at TEXT NOT NULL
    );
    """)

    # 기본 관리자 계정 시딩 (비밀번호: admin1234!)
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        default_pw_hash = generate_password_hash("admin1234!")
        now_str = datetime.now(timezone.utc).isoformat()

        admins = [
            (str(uuid.uuid4()), "superadmin", "최고 관리자", "superadmin@vibe.com", default_pw_hash, "SUPER_ADMIN", "active", 0, None, now_str, now_str),
            (str(uuid.uuid4()), "admin", "운영 관리자", "admin@vibe.com", default_pw_hash, "ADMIN", "active", 0, None, now_str, now_str),
            (str(uuid.uuid4()), "staff", "상품/주문 담당자", "staff@vibe.com", default_pw_hash, "STAFF", "active", 0, None, now_str, now_str),
        ]
        cursor.executemany("""
            INSERT INTO admin_users (id, username, name, email, password_hash, role, status, must_change_password, last_login_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, admins)

    # 기본 시스템 설정 시딩
    cursor.execute("SELECT COUNT(*) FROM admin_settings")
    if cursor.fetchone()[0] == 0:
        now_str = datetime.now(timezone.utc).isoformat()
        defaults = [
            ("shop_name", "VIBE FASHION", "쇼핑몰 상호명"),
            ("company_name", "(주) 바이브 패션", "법인명"),
            ("cs_phone", "1588-0000", "고객센터 전화번호"),
            ("cs_email", "cs@vibefashion.com", "고객센터 이메일"),
            ("low_stock_threshold", "5", "재고 부족 알림 기준 수량"),
            ("free_shipping_min", "50000", "무료배송 최소 주문금액(원)"),
            ("default_shipping_fee", "3000", "기본 배송비(원)"),
        ]
        cursor.executemany("""
            INSERT OR IGNORE INTO admin_settings (key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
        """, [(k, v, d, now_str) for k, v, d in defaults])

    conn.commit()
    conn.close()


# 모듈 로드 시 기본 초기화
try:
    init_sqlite_db()
except Exception as e:
    logger.warning(f"SQLite 초기화 경고: {e}")


# =====================================================
# 로그인 실패 제한 (Rate Limiting / Brute-force 방지)
# =====================================================
MAX_LOGIN_FAILURES = 5
LOCKOUT_MINUTES = 15

# IP 및 username별 실패 기록: { key: [timestamp, ...] }
_login_failures = {}


def _get_failure_keys(username: str, ip_address: str | None) -> list[str]:
    keys = []
    if ip_address:
        keys.append(f"ip:{ip_address}")
    if username:
        keys.append(f"user:{username.strip().lower()}")
    return keys


def is_login_locked(username: str, ip_address: str | None) -> tuple[bool, int]:
    """
    로그인 시도 제한 상태인지 확인.
    잠금 상태인 경우 (True, 남은_대기_분) 반환.
    """
    now = datetime.now(timezone.utc)
    keys = _get_failure_keys(username, ip_address)

    for k in keys:
        attempts = _login_failures.get(k, [])
        # 만료된 시도(LOCKOUT_MINUTES 이전) 제거
        recent_attempts = [t for t in attempts if (now - t).total_seconds() < LOCKOUT_MINUTES * 60]
        _login_failures[k] = recent_attempts

        if len(recent_attempts) >= MAX_LOGIN_FAILURES:
            oldest = recent_attempts[0]
            remaining_seconds = int((LOCKOUT_MINUTES * 60) - (now - oldest).total_seconds())
            remaining_minutes = max(1, (remaining_seconds + 59) // 60)
            return True, remaining_minutes

    return False, 0


def record_login_failure(username: str, ip_address: str | None):
    """로그인 실패 타임스탬프 기록"""
    now = datetime.now(timezone.utc)
    keys = _get_failure_keys(username, ip_address)
    for k in keys:
        if k not in _login_failures:
            _login_failures[k] = []
        _login_failures[k].append(now)


def clear_login_failures(username: str, ip_address: str | None):
    """로그인 성공 시 실패 기록 초기화"""
    keys = _get_failure_keys(username, ip_address)
    for k in keys:
        _login_failures.pop(k, None)


# =====================================================
# 관리자 비밀번호 보안 정책 검증
# =====================================================
DISALLOWED_WEAK_PASSWORDS = {
    "123456789", "1234567890", "password", "admin123", "admin123!",
    "administrator", "qwerty", "qwerty123", "admin1234!", "adminadmin"
}


def validate_password_complexity(password: str, username: str = None) -> tuple[bool, list[str]]:
    """
    관리자 새 비밀번호 보안 조건 검사:
    - 최소 12자 이상, 최대 64자 이하
    - 영문 대문자 1개 이상
    - 영문 소문자 1개 이상
    - 숫자 1개 이상
    - 특수문자 1개 이상
    - 공백 금지
    - 약한 비밀번호 및 admin 관련 단어 금지
    - username 포함 금지
    - 동일 문자 3회 이상 연속 반복 금지
    """
    errors = []

    if len(password) < 12:
        errors.append("12자 이상 입력해주세요.")
    if len(password) > 64:
        errors.append("64자 이하로 입력해주세요.")

    if " " in password:
        errors.append("공백은 포함할 수 없습니다.")

    import re
    if not re.search(r"[A-Z]", password):
        errors.append("영문 대문자를 1개 이상 포함해주세요.")
    if not re.search(r"[a-z]", password):
        errors.append("영문 소문자를 1개 이상 포함해주세요.")
    if not re.search(r"[0-9]", password):
        errors.append("숫자를 1개 이상 포함해주세요.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\/'`~;]", password):
        errors.append("특수문자를 1개 이상 포함해주세요.")

    lower_pw = password.lower()
    if lower_pw in DISALLOWED_WEAK_PASSWORDS:
        errors.append("보안성이 취약하여 사용할 수 없는 비밀번호입니다.")

    if "admin" in lower_pw or "administrator" in lower_pw:
        errors.append("관리자와 관련된 단어('admin', 'administrator')는 포함할 수 없습니다.")

    if username and len(username) >= 3 and username.lower() in lower_pw:
        errors.append("관리자 ID를 포함하는 비밀번호는 사용할 수 없습니다.")

    if re.search(r"(.)\1\1", password):
        errors.append("동일한 문자가 3회 이상 연속으로 반복될 수 없습니다.")

    return (len(errors) == 0), errors


def _is_supabase_admin_table_ready() -> bool:
    """Supabase에 admin_users 테이블이 실존하는지 검사"""
    from routes.auth import get_supabase_admin_client
    client = get_supabase_admin_client()
    if not client:
        return False
    try:
        client.table("admin_users").select("id").limit(1).execute()
        return True
    except Exception:
        return False


# =====================================================
# 3. 관리자 계정 CRUD 및 인증
# =====================================================
def get_admin_by_username(username: str) -> dict | None:
    """사용자명(ID)으로 관리자 조회"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_admin_by_id(admin_id: str) -> dict | None:
    """ID로 관리자 조회"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users WHERE id = ?", (admin_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def list_admins() -> list[dict]:
    """모든 관리자 계정 목록 반환"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users ORDER BY created_at ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def authenticate_admin(username: str, password: str, ip_address: str = None) -> tuple[dict | None, str | None]:
    """
    관리자 로그인 인증 처리
    보안 지침:
    1. 로그인 실패 시 ID가 틀렸든 비밀번호가 틀렸든 동일한 모호한 에러 메시지 반환:
       「아이디 또는 비밀번호가 일치하지 않습니다.」
    2. 무차별 대입 공격(Brute-force) 방지: 반복 실패 시 잠금 안내
    3. 실패 시 보안 감사 로그에 로그인 실패 기록
    """
    locked, remaining_mins = is_login_locked(username, ip_address)
    if locked:
        log_admin_action(
            admin_id=None,
            username=username,
            name="인증 시도",
            action="로그인 차단",
            target="관리자 인증",
            details=f"반복 로그인 실패로 인한 임시 잠금 상태 ({remaining_mins}분 대기 필요)",
            result="실패",
            ip_address=ip_address
        )
        return None, f"반복적인 로그인 실패로 인해 로그인이 일시적으로 제한되었습니다. {remaining_mins}분 후 다시 시도해주세요."

    admin = get_admin_by_username(username)

    # 계정이 없거나 비활성/잠김이거나 비밀번호가 틀린 경우 모두 통합 에러 메시지 반환
    if not admin or admin.get("status") != "active" or not check_password_hash(admin.get("password_hash", ""), password):
        record_login_failure(username, ip_address)
        log_admin_action(
            admin_id=admin.get("id") if admin else None,
            username=username,
            name=admin.get("name") if admin else "알수없음",
            action="로그인 실패",
            target="관리자 인증",
            details="인증 정보 불일치",
            result="실패",
            ip_address=ip_address
        )
        return None, "아이디 또는 비밀번호가 일치하지 않습니다."

    # 로그인 성공: 실패 카운터 초기화
    clear_login_failures(username, ip_address)

    # 마지막 로그인 일시 갱신
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("UPDATE admin_users SET last_login_at = ? WHERE id = ?", (now_str, admin["id"]))
    conn.commit()
    conn.close()

    admin["last_login_at"] = now_str

    log_admin_action(
        admin_id=admin["id"],
        username=admin["username"],
        name=admin["name"],
        action="로그인",
        target="관리자 시스템",
        details="관리자 로그인 성공",
        result="성공",
        ip_address=ip_address
    )
    return admin, None


def create_admin(username: str, name: str, email: str, password: str, role: str,
                 status: str = "active", must_change_password: bool = False,
                 creator_info: dict = None) -> tuple[dict | None, str | list[str] | None]:
    """새로운 관리자 계정 생성 (SUPER_ADMIN 전용)"""
    if not username or not name or not email or not password or not role:
        return None, "모든 필수 항목을 입력해주세요."

    if role not in ROLES:
        return None, "올바르지 않은 역할입니다."

    is_valid, validation_errors = validate_password_complexity(password, username=username)
    if not is_valid:
        return None, validation_errors

    conn = get_sqlite_conn()
    cursor = conn.cursor()

    # 중복 확인
    cursor.execute("SELECT id FROM admin_users WHERE username = ? OR email = ?", (username, email))
    if cursor.fetchone():
        conn.close()
        return None, "이미 존재하는 관리자 ID 또는 이메일입니다."

    admin_id = str(uuid.uuid4())
    pw_hash = generate_password_hash(password)
    now_str = datetime.now(timezone.utc).isoformat()

    cursor.execute("""
        INSERT INTO admin_users (id, username, name, email, password_hash, role, status, must_change_password, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (admin_id, username, name, email, pw_hash, role, status, 1 if must_change_password else 0, now_str, now_str))
    conn.commit()
    conn.close()

    if creator_info:
        log_admin_action(
            admin_id=creator_info.get("id"),
            username=creator_info.get("username"),
            name=creator_info.get("name"),
            action="관리자 계정 생성",
            target=f"{username} ({name})",
            details=f"역할: {role}, 이메일: {email}, 상태: {status}",
            result="성공"
        )

    return get_admin_by_id(admin_id), None


def update_admin(admin_id: str, name: str, email: str, role: str, status: str,
                 updater_info: dict = None) -> tuple[bool, str | None]:
    """관리자 정보 수정 (SUPER_ADMIN 전용)"""
    target = get_admin_by_id(admin_id)
    if not target:
        return False, "관리자를 찾을 수 없습니다."

    # 최고 관리자 본인 계정의 역할 변경이나 비활성화 방지
    if updater_info and updater_info.get("id") == admin_id:
        if role != "SUPER_ADMIN":
            return False, "본인 계정의 최고 관리자 역할을 강등할 수 없습니다."
        if status != "active":
            return False, "본인 계정을 비활성화하거나 잠글 수 없습니다."

    conn = get_sqlite_conn()
    cursor = conn.cursor()

    # 이메일 중복 체크 (본인 제외)
    cursor.execute("SELECT id FROM admin_users WHERE email = ? AND id != ?", (email, admin_id))
    if cursor.fetchone():
        conn.close()
        return False, "이미 다른 관리자가 사용 중인 이메일입니다."

    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        UPDATE admin_users
        SET name = ?, email = ?, role = ?, status = ?, updated_at = ?
        WHERE id = ?
    """, (name, email, role, status, now_str, admin_id))
    conn.commit()
    conn.close()

    if updater_info:
        changes = []
        if target["name"] != name:
            changes.append(f"이름: {target['name']} -> {name}")
        if target["email"] != email:
            changes.append(f"이메일: {target['email']} -> {email}")
        if target["role"] != role:
            changes.append(f"역할: {target['role']} -> {role}")
        if target["status"] != status:
            changes.append(f"상태: {target['status']} -> {status}")

        log_admin_action(
            admin_id=updater_info.get("id"),
            username=updater_info.get("username"),
            name=updater_info.get("name"),
            action="관리자 권한/정보 변경",
            target=f"{target['username']} ({target['name']})",
            details=" / ".join(changes) if changes else "변경사항 없음",
            result="성공"
        )

    return True, None


def toggle_admin_status(admin_id: str, new_status: str, updater_info: dict = None) -> tuple[bool, str | None]:
    """관리자 계정 상태 변경 (active / inactive / locked)"""
    target = get_admin_by_id(admin_id)
    if not target:
        return False, "관리자를 찾을 수 없습니다."

    if updater_info and updater_info.get("id") == admin_id:
        return False, "본인 계정의 상태는 변경할 수 없습니다."

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    cursor.execute("UPDATE admin_users SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_str, admin_id))
    conn.commit()
    conn.close()

    if updater_info:
        action_name = "관리자 계정 활성화" if new_status == "active" else "관리자 계정 비활성화"
        log_admin_action(
            admin_id=updater_info.get("id"),
            username=updater_info.get("username"),
            name=updater_info.get("name"),
            action=action_name,
            target=f"{target['username']}",
            details=f"상태: {target['status']} -> {new_status}",
            result="성공"
        )
    return True, None


def delete_admin(admin_id: str, operator_info: dict = None) -> tuple[bool, str | None]:
    """관리자 계정 삭제 (SUPER_ADMIN 전용)"""
    target = get_admin_by_id(admin_id)
    if not target:
        return False, "관리자를 찾을 수 없습니다."

    if operator_info and operator_info.get("id") == admin_id:
        return False, "본인 계정은 삭제할 수 없습니다."

    # 마지막 SUPER_ADMIN 삭제 방지
    if target["role"] == "SUPER_ADMIN":
        conn = get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM admin_users WHERE role = 'SUPER_ADMIN'")
        count = cursor.fetchone()[0]
        conn.close()
        if count <= 1:
            return False, "쇼핑몰에 최소 1명 이상의 최고 관리자가 존재해야 합니다."

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admin_users WHERE id = ?", (admin_id,))
    conn.commit()
    conn.close()

    if operator_info:
        log_admin_action(
            admin_id=operator_info.get("id"),
            username=operator_info.get("username"),
            name=operator_info.get("name"),
            action="관리자 삭제",
            target=f"{target['username']} ({target['name']})",
            details=f"역할: {target['role']}, 이메일: {target['email']}",
            result="성공"
        )
    return True, None


def reset_admin_password(admin_id: str, new_password: str, must_change: bool = True,
                         operator_info: dict = None) -> tuple[bool, str | list[str] | None]:
    """관리자 비밀번호 초기화 (SUPER_ADMIN 전용)"""
    target = get_admin_by_id(admin_id)
    if not target:
        return False, "관리자를 찾을 수 없습니다."

    is_valid, validation_errors = validate_password_complexity(new_password, username=target["username"])
    if not is_valid:
        return False, validation_errors

    pw_hash = generate_password_hash(new_password)
    now_str = datetime.now(timezone.utc).isoformat()

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE admin_users
        SET password_hash = ?, must_change_password = ?, updated_at = ?
        WHERE id = ?
    """, (pw_hash, 1 if must_change else 0, now_str, admin_id))
    conn.commit()
    conn.close()

    if operator_info:
        log_admin_action(
            admin_id=operator_info.get("id"),
            username=operator_info.get("username"),
            name=operator_info.get("name"),
            action="비밀번호 초기화",
            target=f"{target['username']}",
            details="임시 비밀번호 설정 및 다음 로그인 시 변경 요구 플래그 설정",
            result="성공"
        )
    return True, None


def verify_admin_password(admin_id: str, password: str) -> bool:
    """중요 관리자 작업 전 본인 인증을 위한 비밀번호 재검증 함수"""
    admin = get_admin_by_id(admin_id)
    if not admin or admin.get("status") != "active":
        return False
    return check_password_hash(admin.get("password_hash", ""), password)


def change_own_password(admin_id: str, current_pw: str, new_pw: str) -> tuple[bool, str | list[str] | None]:
    """
    관리자 본인 비밀번호 변경:
    1. 현재 세션 및 관리자 계정 존재 여부 검증
    2. 현재 비밀번호 일치 여부 필수 확인 (불일치 시 "현재 비밀번호가 일치하지 않습니다.")
    3. 기존 비밀번호와 동일한지 확인
    4. 새 비밀번호 12자 이상 복합 보안 조건 확인 (불충족 시 상세 조건 목록 반환)
    5. 안전한 해시 방식으로 암호화하여 DB 저장
    6. 활동 로그 기록 (실제 비밀번호 문자열은 절대 저장하지 않음)
    """
    admin = get_admin_by_id(admin_id)
    if not admin or admin.get("status") != "active":
        return False, "관리자 인증 정보가 유효하지 않습니다."

    # 1. 현재 비밀번호 검증
    if not check_password_hash(admin.get("password_hash", ""), current_pw):
        log_admin_action(
            admin_id=admin["id"],
            username=admin["username"],
            name=admin["name"],
            action="비밀번호 변경 실패",
            target="보안 설정",
            details="현재 비밀번호 불일치",
            result="실패"
        )
        return False, "현재 비밀번호가 일치하지 않습니다."

    # 2. 기존 비밀번호와 동일 여부 확인
    if check_password_hash(admin.get("password_hash", ""), new_pw) or current_pw == new_pw:
        return False, "기존 비밀번호와 동일한 비밀번호는 사용할 수 없습니다."

    # 3. 새 비밀번호 보안 조건 검증
    is_valid, validation_errors = validate_password_complexity(new_pw, username=admin["username"])
    if not is_valid:
        return False, validation_errors

    # 4. 안전한 비밀번호 해시 생성 및 갱신
    pw_hash = generate_password_hash(new_pw)
    now_str = datetime.now(timezone.utc).isoformat()

    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE admin_users
        SET password_hash = ?, must_change_password = 0, updated_at = ?
        WHERE id = ?
    """, (pw_hash, now_str, admin_id))
    conn.commit()
    conn.close()

    # 5. 감사 활동 로그 기록 (실제 비밀번호 제외)
    log_admin_action(
        admin_id=admin["id"],
        username=admin["username"],
        name=admin["name"],
        action="관리자 비밀번호 변경",
        target="보안 설정",
        details="비밀번호 변경 성공 및 기존 세션 종료 처리",
        result="성공"
    )
    return True, None


# =====================================================
# 4. 관리자 감사 활동 로그 (Activity Logs)
# =====================================================
def log_admin_action(admin_id: str | None, username: str | None, name: str | None,
                     action: str, target: str = None, details: str = None,
                     result: str = "성공", ip_address: str = None):
    """관리자 활동 로그 기록"""
    try:
        if not ip_address:
            try:
                ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            except Exception:
                ip_address = "127.0.0.1"

        log_id = str(uuid.uuid4())
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        conn = get_sqlite_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin_logs (id, admin_id, admin_username, admin_name, action, target, details, result, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, admin_id, username or "알수없음", name or "알수없음", action, target or "-", details or "-", result, ip_address, now_str))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"관리자 활동 로그 기록 실패: {e}")


def list_admin_logs(limit: int = 150, action_filter: str = None, search: str = None) -> list[dict]:
    """관리자 활동 로그 목록 조회"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()

    query = "SELECT * FROM admin_logs"
    conditions = []
    params = []

    if action_filter:
        conditions.append("action LIKE ?")
        params.append(f"%{action_filter}%")
    if search:
        conditions.append("(admin_username LIKE ? OR admin_name LIKE ? OR target LIKE ? OR details LIKE ?)")
        search_param = f"%{search}%"
        params.extend([search_param, search_param, search_param, search_param])

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =====================================================
# 5. 시스템 설정 관리
# =====================================================
def get_system_settings() -> dict[str, str]:
    """시스템 설정 키-값 딕셔너리 반환"""
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM admin_settings")
    rows = cursor.fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def update_system_setting(key: str, value: str, operator_info: dict = None) -> bool:
    """개별 시스템 설정 갱신"""
    now_str = datetime.now(timezone.utc).isoformat()
    conn = get_sqlite_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO admin_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
    """, (key, value, now_str))
    conn.commit()
    conn.close()

    if operator_info:
        log_admin_action(
            admin_id=operator_info.get("id"),
            username=operator_info.get("username"),
            name=operator_info.get("name"),
            action="시스템 설정 변경",
            target=key,
            details=f"설정값 변경: {value}",
            result="성공"
        )
    return True


# =====================================================
# 6. 관리자 인증 및 권한 확인 데코레이터
# =====================================================
# 관리자 세션 최대 유효 시간 (비활동 시 30분 만료)
ADMIN_SESSION_LIFETIME_SECONDS = 30 * 60


def admin_login_required(view_func):
    """
    관리자 로그인 여부 및 세션 유효성/비활동 만료 확인 데코레이터
    - 비인증자 접근 시 관리자 데이터를 일체 노출하지 않고 관리자 로그인 화면으로 이동
    - 일정 시간 비활동 시 세션 자동 만료
    """
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        admin_id = session.get("admin_id")
        if not admin_id:
            # 원래 요청하려던 경로를 next로 전달
            next_url = request.full_path if request.query_string else request.path
            return redirect(url_for("auth.login", next=next_url))

        # 세션 비활동 만료 검사
        now_ts = datetime.now(timezone.utc).timestamp()
        last_activity = session.get("admin_last_activity")
        if last_activity and (now_ts - last_activity > ADMIN_SESSION_LIFETIME_SECONDS):
            # 세션 만료 처리
            session.pop("admin_id", None)
            session.pop("admin_username", None)
            session.pop("admin_role", None)
            session.pop("admin_name", None)
            session.pop("admin_last_activity", None)
            return redirect(url_for("auth.login", error="session_expired"))

        # 최신 활동 시간 갱신
        session["admin_last_activity"] = now_ts

        # 데이터베이스 상의 계정 존재 여부 및 활성 상태 재확증
        admin = get_admin_by_id(admin_id)
        if not admin or admin.get("status") != "active":
            session.pop("admin_id", None)
            session.pop("admin_username", None)
            session.pop("admin_role", None)
            session.pop("admin_name", None)
            session.pop("admin_last_activity", None)
            return redirect(url_for("auth.login", error="invalid_credentials"))

        # 최신 권한 정보를 session에 최신화
        session["admin_role"] = admin["role"]
        session["admin_name"] = admin["name"]
        return view_func(*args, **kwargs)
    return wrapper


def admin_permission_required(permission_code: str):
    """세부 RBAC 권한 검사 데코레이터 (페이지 접근 차단 시 403 Forbidden 반환)"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            admin_id = session.get("admin_id")
            if not admin_id:
                return redirect(url_for("auth.login", next=request.path))

            role = session.get("admin_role", "")
            if not has_admin_permission(role, permission_code):
                # 권한 없음 처리: 403 에러 템플릿 렌더링
                return render_template("admin/403.html",
                                       permission_code=permission_code,
                                       role=role,
                                       role_title=ROLES.get(role, role)), 403
            return view_func(*args, **kwargs)
        return wrapper
    return decorator


def admin_role_required(allowed_roles: list[str]):
    """허용된 역할 리스트 기준 데코레이터"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            admin_id = session.get("admin_id")
            if not admin_id:
                return redirect(url_for("auth.login", next=request.path))

            role = session.get("admin_role", "")
            if role not in allowed_roles:
                return render_template("admin/403.html",
                                       required_roles=allowed_roles,
                                       role=role,
                                       role_title=ROLES.get(role, role)), 403
            return view_func(*args, **kwargs)
        return wrapper
    return decorator
