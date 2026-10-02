"""
=====================================================
쇼핑몰 관리자 전용 라우트 모듈 (routes/admin.py)
=====================================================
일반 회원과 완전히 분리된 관리자 전용 시스템입니다.
- 관리자 인증 (로그인, 로그아웃, 세션 관리, 비밀번호 변경)
- RBAC 역할 기반 접근 제어 (SUPER_ADMIN, ADMIN, STAFF)
- 관리자 대시보드 (핵심 KPI, 최근 주문/회원, 재고 부족 알림, 매출 그래프)
- 회원 관리 (목록, 검색, 상세, 수정, 삭제)
- 상품 관리 (목록, 등록, 수정, 삭제, 판매상태 변경)
- 주문 관리 (목록, 필터, 상세, 주문/배송 상태 변경, 취소/재고원복, 환불)
- 재고 관리 (실시간 재고, 입고 처리, 재고 부족/품절 자동화)
- 판매 및 매출 통계 (기간별 매출/판매량, 인기 상품, Chart.js 연동)
- 관리자 계정 관리 (SUPER_ADMIN 전용: 생성, 수정, 권한변경, 활성/비활성, 비번 초기화, 삭제)
- 관리자 활동 감사 로그 (수행 작업, 대상, 일시, 결과, IP 기록 및 열람)
- 시스템 설정 (SUPER_ADMIN 전용)
"""

import os
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from flask import (
    Blueprint, render_template, request, redirect, url_for, session,
    flash, jsonify, abort, current_app, make_response
)
from routes.auth import get_supabase_admin_client
from services.admin_service import (
    ROLES, PERMISSIONS, has_admin_permission,
    get_admin_by_id, list_admins,
    create_admin, update_admin, toggle_admin_status,
    delete_admin, reset_admin_password, change_own_password,
    verify_admin_password, validate_password_complexity,
    log_admin_action, list_admin_logs,
    get_system_settings, update_system_setting,
    admin_login_required, admin_permission_required, admin_role_required
)

logger = logging.getLogger(__name__)

# =====================================================
# 관리자 URL 접두어 보안 암호화/난독화 (Security Token Path)
# 기본값: /manage-x7k9q2m (난독화된 보안 경로)
# .env의 ADMIN_URL_PREFIX 환경변수를 통해 변경 가능하며,
# /admin 같은 뻔한 관리자 URL 노출을 원천 방지합니다.
# =====================================================
DEFAULT_ADMIN_PREFIX = "/manage-x7k9q2m"
ADMIN_URL_PREFIX = os.getenv("ADMIN_URL_PREFIX", DEFAULT_ADMIN_PREFIX).strip()
if not ADMIN_URL_PREFIX.startswith("/"):
    ADMIN_URL_PREFIX = "/" + ADMIN_URL_PREFIX

# 관리자 전용 블루프린트 (동적 난독화 접두어 등록)
admin_bp = Blueprint("admin", __name__, url_prefix=ADMIN_URL_PREFIX)


# =====================================================
# 컨텍스트 프로세서: 모든 관리자 템플릿에 공통 변수 주입
# =====================================================
@admin_bp.context_processor
def inject_admin_context():
    """모든 관리자 템플릿에서 로그인 정보와 권한 확인 함수 사용 가능"""
    admin_id = session.get("admin_id")
    current_admin = None
    if admin_id:
        current_admin = get_admin_by_id(admin_id)

    role = session.get("admin_role", "")

    def check_perm(perm_code: str) -> bool:
        return has_admin_permission(role, perm_code)

    settings = get_system_settings()

    return {
        "current_admin": current_admin,
        "admin_role": role,
        "admin_role_title": ROLES.get(role, role),
        "has_perm": check_perm,
        "admin_settings": settings,
        "now": datetime.now(timezone.utc),
    }


# =====================================================
# 1. 관리자 전용 인증 (로그인, 로그아웃, 비밀번호 변경)
# =====================================================
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """기존 관리자 로그인 경로를 공통 쇼핑몰 로그인 화면으로 연결합니다."""
    return redirect(url_for("auth.login", **request.args))


@admin_bp.route("/logout")
def logout():
    """관리자 전용 로그아웃"""
    admin_id = session.get("admin_id")
    if admin_id:
        log_admin_action(
            admin_id=admin_id,
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="로그아웃",
            target="관리자 시스템",
            details="로그아웃 완료",
            result="성공"
        )
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    session.pop("admin_name", None)
    session.pop("admin_role", None)

    session.clear()
    return redirect(url_for("auth.login", success="logged_out"))


@admin_bp.route("/profile", methods=["GET", "POST"])
@admin_login_required
def profile():
    """관리자 본인 정보 조회 및 비밀번호 변경"""
    admin = get_admin_by_id(session["admin_id"])
    error_list = []
    error_msg = None
    success_msg = None

    if request.method == "POST":
        current_pw = request.form.get("current_password", "").strip()
        new_pw = request.form.get("new_password", "").strip()
        confirm_pw = request.form.get("confirm_password", "").strip()

        if not current_pw or not new_pw or not confirm_pw:
            error_msg = "모든 항목을 입력해주세요."
        elif new_pw != confirm_pw:
            error_msg = "새 비밀번호와 비밀번호 확인이 일치하지 않습니다."
        else:
            success, err_or_errors = change_own_password(session["admin_id"], current_pw, new_pw)
            if success:
                # 비밀번호 변경 완료: 기존 관리자 세션 종료 및 로그인 화면 이동
                session.pop("admin_id", None)
                session.pop("admin_username", None)
                session.pop("admin_name", None)
                session.pop("admin_role", None)
                session.pop("admin_last_activity", None)

                return redirect(url_for("auth.login", error="password_changed"))
            else:
                if isinstance(err_or_errors, list):
                    error_list = err_or_errors
                else:
                    error_msg = err_or_errors

    return render_template("admin/profile.html", admin=admin, error=error_msg, error_list=error_list, success=success_msg)


# =====================================================
# 2. 관리자 메인 대시보드
# =====================================================
@admin_bp.route("")
def admin_root():
    """
    관리자 기본 루트 접근 제어
    - 로그인 인증이 완료된 관리자만 대시보드로 이동
    - 미인증 상태에서 관리자 URL을 직접 입력 시 일반 회원 로그인 화면으로 이동
    """
    if session.get("admin_id") and session.get("admin_role"):
        return redirect(url_for("admin.dashboard"))
    # 공식 진입 경로인 일반 회원 로그인 화면으로 이동
    return redirect(url_for("auth.login"))


@admin_bp.route("/dashboard")
@admin_login_required
@admin_permission_required("dashboard_view")
def dashboard():
    """관리자 메인 대시보드 (통계 카드, 최근 주문/회원, 재고 부족/품절 알림, 차트 데이터)"""
    client = get_supabase_admin_client()
    settings = get_system_settings()
    low_stock_limit = int(settings.get("low_stock_threshold", 5))

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_start = f"{today_str}T00:00:00+00:00"

    # 1) 통계 집계 변수 초기화
    today_revenue = 0
    total_orders_count = 0
    total_sold_quantity = 0
    total_users_count = 0
    total_products_count = 0
    total_stock_count = 0

    recent_orders = []
    recent_users = []
    low_stock_products = []
    sold_out_products = []

    chart_dates = []
    chart_revenues = []
    chart_sales_counts = []

    if client:
        try:
            # 전체 주문 목록 조회 (통계 계산용)
            ord_res = client.table("orders").select("*").order("created_at", desc=True).execute()
            all_orders = ord_res.data or []
            total_orders_count = len(all_orders)

            # 오늘 매출 집계
            for o in all_orders:
                status = o.get("status", "")
                created = o.get("created_at", "")
                final_amt = int(o.get("final_amount") or 0)
                if status in ["paid", "shipping", "delivered", "completed"]:
                    if created >= today_start:
                        today_revenue += final_amt

            recent_orders = all_orders[:7]

            # 주문 품목(order_items) 조회 -> 총 판매 수량 계산
            items_res = client.table("order_items").select("quantity, total_price, product_id, product_name").execute()
            all_items = items_res.data or []
            total_sold_quantity = sum(int(item.get("quantity") or 0) for item in all_items)

            # 회원 수 조회
            users_res = client.table("profiles").select("*").order("created_at", desc=True).execute()
            all_users = users_res.data or []
            total_users_count = len(all_users)
            recent_users = all_users[:5]

            # 상품 및 재고 집계
            prod_res = client.table("products").select("*, categories(name, slug), product_images(image_url, is_thumbnail)").order("created_at", desc=True).execute()
            all_products = prod_res.data or []
            total_products_count = len(all_products)

            for p in all_products:
                stk = int(p.get("stock") or 0)
                total_stock_count += stk
                if stk == 0 or p.get("status") == "sold_out":
                    sold_out_products.append(p)
                elif stk <= low_stock_limit:
                    low_stock_products.append(p)

            # 최근 7일간 매출 및 판매량 그래프 데이터 집계
            for i in range(6, -1, -1):
                d = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
                d_start = f"{d}T00:00:00+00:00"
                d_end = f"{d}T23:59:59+00:00"

                day_rev = 0
                day_cnt = 0
                for o in all_orders:
                    c_at = o.get("created_at", "")
                    if d_start <= c_at <= d_end and o.get("status") in ["paid", "shipping", "delivered", "completed"]:
                        day_rev += int(o.get("final_amount") or 0)
                        day_cnt += 1

                chart_dates.append(d[5:])  # MM-DD
                chart_revenues.append(day_rev)
                chart_sales_counts.append(day_cnt)

        except Exception as e:
            logger.error(f"대시보드 통계 조회 오류: {e}")

    # 최근 활동 로그 5건
    recent_logs = list_admin_logs(limit=5)

    return render_template(
        "admin/dashboard.html",
        today_revenue=today_revenue,
        total_orders_count=total_orders_count,
        total_sold_quantity=total_sold_quantity,
        total_users_count=total_users_count,
        total_products_count=total_products_count,
        total_stock_count=total_stock_count,
        recent_orders=recent_orders,
        recent_users=recent_users,
        low_stock_products=low_stock_products,
        sold_out_products=sold_out_products,
        chart_dates=json.dumps(chart_dates),
        chart_revenues=json.dumps(chart_revenues),
        chart_sales_counts=json.dumps(chart_sales_counts),
        recent_logs=recent_logs,
        low_stock_limit=low_stock_limit
    )


# =====================================================
# 3. 회원 관리 (목록, 검색, 상세, 수정, 삭제)
# =====================================================
@admin_bp.route("/users")
@admin_login_required
@admin_permission_required("user_view")
def users_list():
    """회원 목록 페이지 (검색, 정렬, 페이징)"""
    client = get_supabase_admin_client()
    search = request.args.get("search", "").strip()
    sort_by = request.args.get("sort_by", "created_at_desc")

    users = []
    if client:
        try:
            # 프로필 목록 조회
            res = client.table("profiles").select("*").execute()
            all_users = res.data or []

            # 각 회원의 실시간 주문 통계(주문 횟수, 총 결제액) 집계
            orders_res = client.table("orders").select("user_id, final_amount, status").execute()
            user_orders_map = {}
            for o in orders_res.data or []:
                uid = o.get("user_id")
                if not uid:
                    continue
                if uid not in user_orders_map:
                    user_orders_map[uid] = {"count": 0, "total_spent": 0}
                if o.get("status") in ["paid", "shipping", "delivered", "completed"]:
                    user_orders_map[uid]["count"] += 1
                    user_orders_map[uid]["total_spent"] += int(o.get("final_amount") or 0)

            for u in all_users:
                uid = u.get("id")
                stats = user_orders_map.get(uid, {"count": 0, "total_spent": int(u.get("total_spent") or 0)})
                u["order_count"] = stats["count"]
                u["computed_spent"] = stats["total_spent"]
                users.append(u)

            # 검색 필터링 (이름, 이메일, 전화번호)
            if search:
                low_s = search.lower()
                users = [
                    u for u in users
                    if low_s in (u.get("full_name") or "").lower()
                    or low_s in (u.get("email") or "").lower()
                    or low_s in (u.get("phone") or "").lower()
                ]

            # 정렬 기준 반영
            if sort_by == "created_at_asc":
                users.sort(key=lambda x: x.get("created_at") or "")
            elif sort_by == "spent_desc":
                users.sort(key=lambda x: x.get("computed_spent", 0), reverse=True)
            elif sort_by == "spent_asc":
                users.sort(key=lambda x: x.get("computed_spent", 0))
            elif sort_by == "orders_desc":
                users.sort(key=lambda x: x.get("order_count", 0), reverse=True)
            else:  # 기본: 최신 가입일순
                users.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        except Exception as e:
            logger.error(f"회원 목록 조회 실패: {e}")

    return render_template("admin/users/list.html", users=users, search=search, sort_by=sort_by)


@admin_bp.route("/users/<user_id>")
@admin_login_required
@admin_permission_required("user_view")
def user_detail(user_id: str):
    """회원 상세 정보 페이지 (기본 정보, 주문 내역, 구매 통계)"""
    client = get_supabase_admin_client()
    if not client:
        abort(500, "데이터베이스 연결 오류")

    try:
        user_res = client.table("profiles").select("*").eq("id", user_id).execute()
        if not user_res.data:
            flash("존재하지 않는 회원입니다.", "warning")
            return redirect(url_for("admin.users_list"))
        user = user_res.data[0]

        # 해당 회원의 주문 내역
        orders_res = client.table("orders").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        orders = orders_res.data or []

        order_count = len([o for o in orders if o.get("status") in ["paid", "shipping", "delivered", "completed"]])
        total_spent = sum(int(o.get("final_amount") or 0) for o in orders if o.get("status") in ["paid", "shipping", "delivered", "completed"])
        latest_order_date = orders[0].get("created_at") if orders else None

        user["order_count"] = order_count
        user["total_spent"] = total_spent
        user["latest_order_date"] = latest_order_date

        return render_template("admin/users/detail.html", user=user, orders=orders)
    except Exception as e:
        logger.error(f"회원 상세 조회 오류: {e}")
        flash("회원 정보를 불러오는 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<user_id>/edit", methods=["POST"])
@admin_login_required
@admin_permission_required("user_edit")
def user_edit(user_id: str):
    """회원 정보 수정 (ADMIN, SUPER_ADMIN 가능, STAFF 불가)"""
    client = get_supabase_admin_client()
    if not client:
        return jsonify({"success": False, "message": "데이터베이스 연결 오류"}), 500

    full_name = request.form.get("full_name", "").strip()
    phone = request.form.get("phone", "").strip()
    grade = request.form.get("grade", "BRONZE").strip()

    try:
        old_user = client.table("profiles").select("full_name, phone, grade").eq("id", user_id).execute()
        old_info = old_user.data[0] if old_user.data else {}

        update_payload = {
            "full_name": full_name,
            "phone": phone,
            "grade": grade,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        client.table("profiles").update(update_payload).eq("id", user_id).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="회원 정보 수정",
            target=f"회원ID: {user_id}",
            details=f"이름: {old_info.get('full_name')} -> {full_name}, 연락처: {phone}, 등급: {grade}",
            result="성공"
        )
        flash("회원 정보가 성공적으로 수정되었습니다.", "success")
        return redirect(url_for("admin.user_detail", user_id=user_id))
    except Exception as e:
        logger.error(f"회원 수정 오류: {e}")
        flash("회원 정보 수정에 실패했습니다.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))


@admin_bp.route("/users/<user_id>/delete", methods=["POST"])
@admin_login_required
@admin_permission_required("user_delete")
def user_delete(user_id: str):
    """회원 삭제 (SUPER_ADMIN 전용, 확인창 필수)"""
    client = get_supabase_admin_client()
    if not client:
        flash("데이터베이스 연결 오류", "danger")
        return redirect(url_for("admin.users_list"))

    try:
        user_res = client.table("profiles").select("email, full_name").eq("id", user_id).execute()
        target_info = user_res.data[0] if user_res.data else {}

        # 회원 레코드 삭제
        client.table("profiles").delete().eq("id", user_id).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="회원 삭제",
            target=f"회원 {target_info.get('email')} ({target_info.get('full_name')})",
            details=f"회원 ID: {user_id}",
            result="성공"
        )
        flash(f"회원 ({target_info.get('email')}) 계정이 삭제되었습니다.", "success")
    except Exception as e:
        logger.error(f"회원 삭제 실패: {e}")
        flash(f"회원 삭제 중 오류가 발생했습니다: {e}", "danger")

    return redirect(url_for("admin.users_list"))


# =====================================================
# 4. 상품 관리 (목록, 등록, 수정, 삭제, 판매상태 변경)
# =====================================================
@admin_bp.route("/products")
@admin_login_required
@admin_permission_required("product_view")
def products_list():
    """상품 목록 페이지 (카테고리 필터, 판매상태 필터, 검색)"""
    client = get_supabase_admin_client()
    category_filter = request.args.get("category", "")
    status_filter = request.args.get("status", "")
    search = request.args.get("search", "").strip()

    products = []
    categories = []

    if client:
        try:
            cat_res = client.table("categories").select("*").order("display_order").execute()
            categories = cat_res.data or []

            query = client.table("products").select("*, categories(name, slug), product_images(image_url, is_thumbnail)").order("created_at", desc=True)
            prod_res = query.execute()
            all_prods = prod_res.data or []

            # 주문 상세에서 상품별 누적 판매량 집계
            items_res = client.table("order_items").select("product_id, quantity").execute()
            sales_map = {}
            for item in items_res.data or []:
                pid = item.get("product_id")
                if pid:
                    sales_map[pid] = sales_map.get(pid, 0) + int(item.get("quantity") or 0)

            for p in all_prods:
                p["sales_count"] = sales_map.get(p.get("id"), 0)

                # 썸네일 이미지 추출
                imgs = p.get("product_images") or []
                thumb = None
                for img in imgs:
                    if img.get("is_thumbnail"):
                        thumb = img.get("image_url")
                        break
                if not thumb and imgs:
                    thumb = imgs[0].get("image_url")
                p["thumbnail_url"] = thumb or "https://picsum.photos/seed/item/400/400"

                products.append(p)

            # 필터링
            if category_filter:
                products = [p for p in products if (p.get("categories") or {}).get("slug") == category_filter or p.get("category_id") == category_filter]
            if status_filter:
                products = [p for p in products if p.get("status") == status_filter]
            if search:
                low_s = search.lower()
                products = [p for p in products if low_s in (p.get("name") or "").lower() or low_s in (p.get("slug") or "").lower()]

        except Exception as e:
            logger.error(f"상품 목록 조회 오류: {e}")

    return render_template(
        "admin/products/list.html",
        products=products,
        categories=categories,
        category_filter=category_filter,
        status_filter=status_filter,
        search=search
    )


@admin_bp.route("/products/new", methods=["GET", "POST"])
@admin_login_required
@admin_permission_required("product_create")
def product_create():
    """신규 상품 등록"""
    client = get_supabase_admin_client()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id", "").strip() or None
        price = int(request.form.get("price") or 0)
        sale_price_raw = request.form.get("sale_price", "").strip()
        sale_price = int(sale_price_raw) if sale_price_raw else None
        stock = int(request.form.get("stock") or 0)
        status = request.form.get("status", "active")
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        slug = request.form.get("slug", "").strip() or str(uuid.uuid4())[:8]

        # 재고가 0이면 자동으로 품절 상태로 설정
        if stock == 0:
            status = "sold_out"

        try:
            new_prod_id = str(uuid.uuid4())
            now_iso = datetime.now(timezone.utc).isoformat()
            payload = {
                "id": new_prod_id,
                "name": name,
                "category_id": category_id,
                "price": price,
                "sale_price": sale_price,
                "stock": stock,
                "status": status,
                "description": description,
                "slug": slug,
                "created_at": now_iso,
                "updated_at": now_iso
            }
            client.table("products").insert(payload).execute()

            # 이미지 추가
            if image_url:
                client.table("product_images").insert({
                    "product_id": new_prod_id,
                    "image_url": image_url,
                    "alt_text": name,
                    "is_thumbnail": True,
                    "display_order": 0
                }).execute()

            log_admin_action(
                admin_id=session.get("admin_id"),
                username=session.get("admin_username"),
                name=session.get("admin_name"),
                action="상품 등록",
                target=f"{name}",
                details=f"가격: {price:,}원, 재고: {stock}개, 상태: {status}",
                result="성공"
            )
            flash(f"상품 '{name}'이(가) 등록되었습니다.", "success")
            return redirect(url_for("admin.products_list"))
        except Exception as e:
            logger.error(f"상품 등록 실패: {e}")
            flash(f"상품 등록 중 오류가 발생했습니다: {e}", "danger")

    categories = []
    if client:
        try:
            cat_res = client.table("categories").select("*").order("display_order").execute()
            categories = cat_res.data or []
        except Exception:
            pass

    return render_template("admin/products/form.html", product=None, categories=categories, mode="new")


@admin_bp.route("/products/<product_id>/edit", methods=["GET", "POST"])
@admin_login_required
@admin_permission_required("product_edit")
def product_edit(product_id: str):
    """상품 정보 수정"""
    client = get_supabase_admin_client()
    if not client:
        abort(500, "데이터베이스 연결 오류")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id", "").strip() or None
        price = int(request.form.get("price") or 0)
        sale_price_raw = request.form.get("sale_price", "").strip()
        sale_price = int(sale_price_raw) if sale_price_raw else None
        stock = int(request.form.get("stock") or 0)
        status = request.form.get("status", "active")
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()

        # 재고 수량에 따른 자동 상태 제어: 재고가 0이면 sold_out
        if stock == 0:
            status = "sold_out"
        elif stock > 0 and status == "sold_out":
            status = "active"

        try:
            old_prod = client.table("products").select("name, price, stock, status").eq("id", product_id).execute()
            old_data = old_prod.data[0] if old_prod.data else {}

            update_payload = {
                "name": name,
                "category_id": category_id,
                "price": price,
                "sale_price": sale_price,
                "stock": stock,
                "status": status,
                "description": description,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            client.table("products").update(update_payload).eq("id", product_id).execute()

            # 이미지 갱신
            if image_url:
                img_res = client.table("product_images").select("id").eq("product_id", product_id).eq("is_thumbnail", True).execute()
                if img_res.data:
                    client.table("product_images").update({"image_url": image_url}).eq("id", img_res.data[0]["id"]).execute()
                else:
                    client.table("product_images").insert({
                        "product_id": product_id,
                        "image_url": image_url,
                        "alt_text": name,
                        "is_thumbnail": True,
                        "display_order": 0
                    }).execute()

            log_admin_action(
                admin_id=session.get("admin_id"),
                username=session.get("admin_username"),
                name=session.get("admin_name"),
                action="상품 수정",
                target=f"상품번호: {product_id} ({name})",
                details=f"가격: {old_data.get('price'):,}원 -> {price:,}원 / 재고: {old_data.get('stock')} -> {stock} / 상태: {status}",
                result="성공"
            )
            flash(f"상품 '{name}' 정보가 수정되었습니다.", "success")
            return redirect(url_for("admin.products_list"))
        except Exception as e:
            logger.error(f"상품 수정 실패: {e}")
            flash(f"상품 수정 중 오류가 발생했습니다: {e}", "danger")

    prod_res = client.table("products").select("*, product_images(*)").eq("id", product_id).execute()
    if not prod_res.data:
        flash("상품을 찾을 수 없습니다.", "warning")
        return redirect(url_for("admin.products_list"))

    product = prod_res.data[0]
    imgs = product.get("product_images") or []
    product["thumbnail_url"] = imgs[0].get("image_url") if imgs else ""

    cat_res = client.table("categories").select("*").order("display_order").execute()
    categories = cat_res.data or []

    return render_template("admin/products/form.html", product=product, categories=categories, mode="edit")


@admin_bp.route("/products/<product_id>/delete", methods=["POST"])
@admin_login_required
@admin_permission_required("product_delete")
def product_delete(product_id: str):
    """상품 삭제 (SUPER_ADMIN 전용, ADMIN/STAFF 불가)"""
    client = get_supabase_admin_client()
    if not client:
        flash("데이터베이스 연결 오류", "danger")
        return redirect(url_for("admin.products_list"))

    try:
        prod_res = client.table("products").select("name").eq("id", product_id).execute()
        prod_name = prod_res.data[0].get("name") if prod_res.data else product_id

        client.table("products").delete().eq("id", product_id).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="상품 삭제",
            target=f"상품번호: {product_id} ({prod_name})",
            details="상품 및 관련 옵션/이미지 삭제 완료",
            result="성공"
        )
        flash(f"상품 '{prod_name}'이(가) 삭제되었습니다.", "success")
    except Exception as e:
        logger.error(f"상품 삭제 실패: {e}")
        flash(f"상품 삭제 중 오류 발생: {e}", "danger")

    return redirect(url_for("admin.products_list"))


@admin_bp.route("/products/<product_id>/status", methods=["POST"])
@admin_login_required
@admin_permission_required("product_edit")
def product_change_status(product_id: str):
    """상품 판매 상태 즉시 변경"""
    client = get_supabase_admin_client()
    new_status = request.form.get("status")

    if new_status not in ["active", "sold_out", "hidden"]:
        return jsonify({"success": False, "message": "유효하지 않은 상태값입니다."}), 400

    try:
        client.table("products").update({
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", product_id).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="상품 판매 상태 변경",
            target=f"상품번호: {product_id}",
            details=f"새 상태: {new_status}",
            result="성공"
        )
        flash("상품 상태가 변경되었습니다.", "success")
    except Exception as e:
        flash(f"상태 변경 실패: {e}", "danger")

    return redirect(request.referrer or url_for("admin.products_list"))


# =====================================================
# 5. 주문 관리 (목록, 검색, 상세, 상태변경, 취소, 환불)
# =====================================================
@admin_bp.route("/orders")
@admin_login_required
@admin_permission_required("order_view")
def orders_list():
    """주문 목록 페이지 (주문번호/주문자 검색, 상태 필터)"""
    client = get_supabase_admin_client()
    status_filter = request.args.get("status", "")
    search = request.args.get("search", "").strip()

    orders = []
    if client:
        try:
            ord_res = client.table("orders").select("*, order_items(*)").order("created_at", desc=True).execute()
            all_orders = ord_res.data or []

            for o in all_orders:
                items = o.get("order_items") or []
                total_qty = sum(int(it.get("quantity") or 0) for it in items)
                first_item_name = items[0].get("product_name") if items else "주문 상품"
                item_summary = f"{first_item_name} 외 {len(items)-1}건" if len(items) > 1 else first_item_name

                o["total_qty"] = total_qty
                o["item_summary"] = item_summary
                orders.append(o)

            # 필터링
            if status_filter:
                orders = [o for o in orders if o.get("status") == status_filter]
            if search:
                low_s = search.lower()
                orders = [
                    o for o in orders
                    if low_s in (o.get("order_number") or "").lower()
                    or low_s in (o.get("recipient_name") or "").lower()
                    or low_s in (o.get("recipient_phone") or "").lower()
                ]

        except Exception as e:
            logger.error(f"주문 목록 조회 오류: {e}")

    return render_template(
        "admin/orders/list.html",
        orders=orders,
        status_filter=status_filter,
        search=search
    )


@admin_bp.route("/orders/<order_id>")
@admin_login_required
@admin_permission_required("order_view")
def order_detail(order_id: str):
    """주문 상세 정보 페이지"""
    client = get_supabase_admin_client()
    if not client:
        abort(500, "데이터베이스 연결 오류")

    try:
        # UUID 또는 주문번호(order_number)로 조회 지원
        ord_res = client.table("orders").select("*").eq("id", order_id).execute()
        if not ord_res.data:
            ord_res = client.table("orders").select("*").eq("order_number", order_id).execute()
        if not ord_res.data:
            flash("주문 정보를 찾을 수 없습니다.", "warning")
            return redirect(url_for("admin.orders_list"))

        order = ord_res.data[0]

        # 주문 항목 조회
        items_res = client.table("order_items").select("*").eq("order_id", order["id"]).execute()
        items = items_res.data or []

        # 주문 고객 정보
        user_res = client.table("profiles").select("*").eq("id", order["user_id"]).execute()
        user = user_res.data[0] if user_res.data else None

        return render_template("admin/orders/detail.html", order=order, items=items, user=user)
    except Exception as e:
        logger.error(f"주문 상세 조회 오류: {e}")
        flash("주문 정보를 불러오는 중 오류가 발생했습니다.", "danger")
        return redirect(url_for("admin.orders_list"))


@admin_bp.route("/orders/<order_id>/status", methods=["POST"])
@admin_login_required
@admin_permission_required("order_status_change")
def order_change_status(order_id: str):
    """주문 및 배송 상태 변경 (결제대기, 결제완료, 상품준비중, 배송중, 배송완료, 완료)"""
    client = get_supabase_admin_client()
    new_status = request.form.get("status")

    valid_statuses = ["pending", "paid", "shipping", "delivered", "completed"]
    if new_status not in valid_statuses:
        flash("유효하지 않은 주문 상태입니다.", "warning")
        return redirect(request.referrer or url_for("admin.orders_list"))

    try:
        ord_res = client.table("orders").select("order_number, status").eq("id", order_id).execute()
        old_data = ord_res.data[0] if ord_res.data else {}

        update_payload = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if new_status == "paid" and not old_data.get("paid_at"):
            update_payload["paid_at"] = datetime.now(timezone.utc).isoformat()

        client.table("orders").update(update_payload).eq("id", order_id).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="주문 상태 변경",
            target=f"주문번호: {old_data.get('order_number')}",
            details=f"상태: {old_data.get('status')} -> {new_status}",
            result="성공"
        )
        flash(f"주문 상태가 '{new_status}'(으)로 변경되었습니다.", "success")
    except Exception as e:
        logger.error(f"주문 상태 변경 실패: {e}")
        flash(f"주문 상태 변경 중 오류: {e}", "danger")

    return redirect(request.referrer or url_for("admin.order_detail", order_id=order_id))


@admin_bp.route("/orders/<order_id>/cancel", methods=["POST"])
@admin_login_required
@admin_permission_required("order_cancel")
def order_cancel(order_id: str):
    """주문 취소 처리 (권한 확인, 재고 원복, 활동 로그 기록)"""
    client = get_supabase_admin_client()
    cancel_reason = request.form.get("reason", "관리자 주문 취소").strip()

    try:
        ord_res = client.table("orders").select("*, order_items(*)").eq("id", order_id).execute()
        if not ord_res.data:
            flash("주문을 찾을 수 없습니다.", "warning")
            return redirect(url_for("admin.orders_list"))

        order = ord_res.data[0]
        if order.get("status") == "cancelled":
            flash("이미 취소된 주문입니다.", "info")
            return redirect(url_for("admin.order_detail", order_id=order_id))

        # 1. 주문 상태를 cancelled로 변경
        client.table("orders").update({
            "status": "cancelled",
            "delivery_memo": f"취소 사유: {cancel_reason}",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", order_id).execute()

        # 2. 재고 원복: 주문 품목들의 수량만큼 상품 재고 및 옵션 재고 복구
        items = order.get("order_items") or []
        for it in items:
            pid = it.get("product_id")
            opt_id = it.get("option_id")
            qty = int(it.get("quantity") or 0)

            if pid and qty > 0:
                # 상품 메인 재고 복구
                p_res = client.table("products").select("stock, status").eq("id", pid).execute()
                if p_res.data:
                    cur_stock = int(p_res.data[0].get("stock") or 0)
                    new_stock = cur_stock + qty
                    # 품절이었던 경우 재고 증가 시 active로 자동 복귀
                    new_stat = "active" if p_res.data[0].get("status") == "sold_out" and new_stock > 0 else p_res.data[0].get("status")
                    client.table("products").update({
                        "stock": new_stock,
                        "status": new_stat,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", pid).execute()

            if opt_id and qty > 0:
                # 옵션 재고 복구
                opt_res = client.table("product_options").select("stock").eq("id", opt_id).execute()
                if opt_res.data:
                    c_opt_stock = int(opt_res.data[0].get("stock") or 0)
                    client.table("product_options").update({"stock": c_opt_stock + qty}).eq("id", opt_id).execute()

        # 3. 활동 로그 기록
        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="주문 취소",
            target=f"주문번호: {order.get('order_number')}",
            details=f"사유: {cancel_reason} / 재고 원복 완료",
            result="성공"
        )
        flash(f"주문({order.get('order_number')})이 취소 처리되었으며 상품 재고가 원복되었습니다.", "success")
    except Exception as e:
        logger.error(f"주문 취소 실패: {e}")
        flash(f"주문 취소 처리 중 오류: {e}", "danger")

    return redirect(url_for("admin.order_detail", order_id=order_id))


@admin_bp.route("/orders/<order_id>/refund", methods=["POST"])
@admin_login_required
@admin_permission_required("order_refund")
def order_refund(order_id: str):
    """환불 처리 (SUPER_ADMIN, ADMIN 허용, STAFF 금지, 재고 원복 및 환불 기록)"""
    client = get_supabase_admin_client()
    refund_amount_raw = request.form.get("refund_amount")
    refund_reason = request.form.get("reason", "관리자 환불 승인").strip()

    try:
        ord_res = client.table("orders").select("*, order_items(*)").eq("id", order_id).execute()
        if not ord_res.data:
            flash("주문을 찾을 수 없습니다.", "warning")
            return redirect(url_for("admin.orders_list"))

        order = ord_res.data[0]
        final_amt = int(order.get("final_amount") or 0)
        refund_amt = int(refund_amount_raw) if refund_amount_raw else final_amt

        # 1. 환불 레코드 생성
        client.table("refunds").insert({
            "order_id": order_id,
            "user_id": order["user_id"],
            "reason": refund_reason,
            "refund_amount": refund_amt,
            "status": "completed",
            "processed_at": datetime.now(timezone.utc).isoformat()
        }).execute()

        # 2. 주문 상태를 cancelled 또는 refund 처리
        client.table("orders").update({
            "status": "cancelled",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", order_id).execute()

        # 3. 재고 원복
        items = order.get("order_items") or []
        for it in items:
            pid = it.get("product_id")
            qty = int(it.get("quantity") or 0)
            if pid and qty > 0:
                p_res = client.table("products").select("stock, status").eq("id", pid).execute()
                if p_res.data:
                    c_stk = int(p_res.data[0].get("stock") or 0)
                    client.table("products").update({
                        "stock": c_stk + qty,
                        "status": "active" if c_stk == 0 else p_res.data[0].get("status"),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).eq("id", pid).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="환불 처리",
            target=f"주문번호: {order.get('order_number')}",
            details=f"환불금액: {refund_amt:,}원 / 사유: {refund_reason} / 재고 복구 완료",
            result="성공"
        )
        flash(f"주문({order.get('order_number')})에 대해 {refund_amt:,}원의 환불 처리가 완료되었습니다.", "success")
    except Exception as e:
        logger.error(f"환불 처리 실패: {e}")
        flash(f"환불 처리 중 오류: {e}", "danger")

    return redirect(url_for("admin.order_detail", order_id=order_id))


# =====================================================
# 6. 재고 관리 (실시간 재고, 입고 처리, 재고 부족/품절 자동화)
# =====================================================
@admin_bp.route("/inventory")
@admin_login_required
@admin_permission_required("inventory_view")
def inventory_list():
    """재고 관리 페이지 (재고 상태: 충분, 재고 부족, 품절)"""
    client = get_supabase_admin_client()
    settings = get_system_settings()
    threshold = int(settings.get("low_stock_threshold", 5))

    status_filter = request.args.get("status", "")
    search = request.args.get("search", "").strip()

    items = []
    low_stock_count = 0
    sold_out_count = 0
    normal_count = 0

    if client:
        try:
            prod_res = client.table("products").select("*, categories(name)").order("stock", desc=False).execute()
            all_prods = prod_res.data or []

            # 주문 품목에서 누적 판매량 산출
            order_items_res = client.table("order_items").select("product_id, quantity").execute()
            sales_map = {}
            for oi in order_items_res.data or []:
                pid = oi.get("product_id")
                if pid:
                    sales_map[pid] = sales_map.get(pid, 0) + int(oi.get("quantity") or 0)

            for p in all_prods:
                stock = int(p.get("stock") or 0)
                sales_qty = sales_map.get(p.get("id"), 0)

                # 재고 상태 판별
                if stock == 0:
                    inv_status = "품절"
                    sold_out_count += 1
                elif stock <= threshold:
                    inv_status = "재고 부족"
                    low_stock_count += 1
                else:
                    inv_status = "충분"
                    normal_count += 1

                p["stock_status"] = inv_status
                p["sales_qty"] = sales_qty
                items.append(p)

            # 필터링
            if status_filter:
                items = [it for it in items if it.get("stock_status") == status_filter]
            if search:
                low_s = search.lower()
                items = [it for it in items if low_s in (it.get("name") or "").lower()]

        except Exception as e:
            logger.error(f"재고 목록 조회 오류: {e}")

    return render_template(
        "admin/inventory/list.html",
        items=items,
        threshold=threshold,
        status_filter=status_filter,
        search=search,
        low_stock_count=low_stock_count,
        sold_out_count=sold_out_count,
        normal_count=normal_count
    )


@admin_bp.route("/inventory/<product_id>/update", methods=["POST"])
@admin_login_required
@admin_permission_required("inventory_edit")
def inventory_update(product_id: str):
    """재고 수량 수정 (직접 변경 또는 입고 수량 추가)"""
    client = get_supabase_admin_client()
    if not client:
        flash("데이터베이스 연결 오류", "danger")
        return redirect(url_for("admin.inventory_list"))

    action_type = request.form.get("action_type", "set")  # "set" (직접입력) or "add" (입고추가)
    quantity = int(request.form.get("quantity") or 0)

    try:
        p_res = client.table("products").select("name, stock, status").eq("id", product_id).execute()
        if not p_res.data:
            flash("상품을 찾을 수 없습니다.", "warning")
            return redirect(url_for("admin.inventory_list"))

        old_stock = int(p_res.data[0].get("stock") or 0)
        prod_name = p_res.data[0].get("name")

        if action_type == "add":
            new_stock = old_stock + quantity
            details = f"입고 수량: +{quantity}개 ({old_stock}개 -> {new_stock}개)"
        else:
            new_stock = max(0, quantity)
            details = f"재고 직접 변경: {old_stock}개 -> {new_stock}개"

        # 재고 수량에 따른 자동 상태 변경: 0개면 sold_out, 0보다 크면 기존 품절 시 active 복구
        new_status = p_res.data[0].get("status")
        if new_stock == 0:
            new_status = "sold_out"
        elif new_stock > 0 and new_status == "sold_out":
            new_status = "active"

        client.table("products").update({
            "stock": new_stock,
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", product_id).execute()

        log_admin_action(
            admin_id=session.get("admin_id"),
            username=session.get("admin_username"),
            name=session.get("admin_name"),
            action="재고 수정",
            target=f"상품: {prod_name}",
            details=details,
            result="성공"
        )
        flash(f"'{prod_name}' 재고가 {new_stock}개로 갱신되었습니다.", "success")
    except Exception as e:
        logger.error(f"재고 수정 오류: {e}")
        flash(f"재고 수정 실패: {e}", "danger")

    return redirect(url_for("admin.inventory_list"))


# =====================================================
# 7. 판매 및 매출 통계 (STAFF 접근 제한)
# =====================================================
@admin_bp.route("/statistics")
@admin_login_required
@admin_permission_required("stats_view")
def statistics():
    """판매 및 매출 통계 페이지 (일별/월별 매출 및 판매량, 인기 상품 TOP 5, 시각화 차트)"""
    client = get_supabase_admin_client()
    period = request.args.get("period", "7days")  # today, 7days, this_month, last_month, custom
    custom_start = request.args.get("start_date")
    custom_end = request.args.get("end_date")

    now = datetime.now(timezone.utc)

    if period == "today":
        start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == "this_month":
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    elif period == "last_month":
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day_of_last_month = first_of_this_month - timedelta(seconds=1)
        start_dt = last_day_of_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = last_day_of_last_month
    elif period == "custom" and custom_start and custom_end:
        try:
            start_dt = datetime.strptime(custom_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(custom_end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except Exception:
            start_dt = now - timedelta(days=7)
            end_dt = now
    else:  # 기본: 최근 7일
        period = "7days"
        start_dt = now - timedelta(days=6)
        start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()

    total_revenue = 0
    total_orders = 0
    total_sales_qty = 0

    daily_labels = []
    daily_revenue = []
    daily_sales = []

    top_products = []

    if client:
        try:
            # 기간 내 주문 조회
            ord_res = client.table("orders").select("*, order_items(*)").gte("created_at", start_iso).lte("created_at", end_iso).execute()
            orders = ord_res.data or []

            paid_orders = [o for o in orders if o.get("status") in ["paid", "shipping", "delivered", "completed"]]
            total_orders = len(paid_orders)
            total_revenue = sum(int(o.get("final_amount") or 0) for o in paid_orders)

            # 일자별 데이터 매핑을 위한 일자 목록 생성
            num_days = (end_dt.date() - start_dt.date()).days + 1
            day_map = {}
            for i in range(min(num_days, 60)):  # 최대 60일
                curr_date = (start_dt.date() + timedelta(days=i)).strftime("%Y-%m-%d")
                day_map[curr_date] = {"revenue": 0, "count": 0, "qty": 0}

            # 주문 데이터 일별 누적
            prod_sales_counter = {}

            for o in paid_orders:
                c_date = (o.get("created_at") or "")[:10]
                if c_date in day_map:
                    day_map[c_date]["revenue"] += int(o.get("final_amount") or 0)
                    day_map[c_date]["count"] += 1

                for item in o.get("order_items") or []:
                    qty = int(item.get("quantity") or 0)
                    total_sales_qty += qty
                    if c_date in day_map:
                        day_map[c_date]["qty"] += qty

                    p_name = item.get("product_name") or "상품"
                    if p_name not in prod_sales_counter:
                        prod_sales_counter[p_name] = {"qty": 0, "revenue": 0}
                    prod_sales_counter[p_name]["qty"] += qty
                    prod_sales_counter[p_name]["revenue"] += int(item.get("total_price") or 0)

            for d_str, val in sorted(day_map.items()):
                daily_labels.append(d_str[5:])  # MM-DD
                daily_revenue.append(val["revenue"])
                daily_sales.append(val["qty"])

            # 인기 상품 TOP 5 정렬
            sorted_prods = sorted(prod_sales_counter.items(), key=lambda x: x[1]["qty"], reverse=True)
            for name, stats in sorted_prods[:5]:
                top_products.append({
                    "name": name,
                    "qty": stats["qty"],
                    "revenue": stats["revenue"]
                })

        except Exception as e:
            logger.error(f"통계 산출 오류: {e}")

    return render_template(
        "admin/statistics/index.html",
        period=period,
        start_date=start_dt.strftime("%Y-%m-%d"),
        end_date=end_dt.strftime("%Y-%m-%d"),
        total_revenue=total_revenue,
        total_orders=total_orders,
        total_sales_qty=total_sales_qty,
        daily_labels=json.dumps(daily_labels),
        daily_revenue=json.dumps(daily_revenue),
        daily_sales=json.dumps(daily_sales),
        top_products=top_products
    )


# =====================================================
# 8. 관리자 계정 관리 (SUPER_ADMIN 전용)
# =====================================================
@admin_bp.route("/admins")
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def admins_list():
    """관리자 계정 목록 (SUPER_ADMIN 전용)"""
    admins = list_admins()
    return render_template("admin/admins/list.html", admins=admins, roles=ROLES)


@admin_bp.route("/admins/new", methods=["POST"])
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def admin_create():
    """관리자 계정 생성 (SUPER_ADMIN 전용, 본인 비밀번호 재확인 필수)"""
    auth_password = request.form.get("auth_password", "").strip()
    if not auth_password or not verify_admin_password(session["admin_id"], auth_password):
        flash("현재 관리자 비밀번호 확인에 실패했습니다. 올바른 비밀번호를 입력해주세요.", "danger")
        return redirect(url_for("admin.admins_list"))

    username = request.form.get("username", "").strip()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()
    role = request.form.get("role", "STAFF").strip()
    status = request.form.get("status", "active").strip()
    must_change = bool(request.form.get("must_change_password"))

    creator_info = {
        "id": session.get("admin_id"),
        "username": session.get("admin_username"),
        "name": session.get("admin_name")
    }

    admin, err = create_admin(
        username=username,
        name=name,
        email=email,
        password=password,
        role=role,
        status=status,
        must_change_password=must_change,
        creator_info=creator_info
    )

    if err:
        if isinstance(err, list):
            flash("신규 관리자 비밀번호가 보안 규칙을 만족하지 않습니다: " + ", ".join(err), "danger")
        else:
            flash(err, "danger")
    else:
        flash(f"관리자 '{username}' ({name}) 계정이 성공적으로 생성되었습니다.", "success")

    return redirect(url_for("admin.admins_list"))


@admin_bp.route("/admins/<admin_id>/edit", methods=["POST"])
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def admin_modify(admin_id: str):
    """관리자 정보 및 권한 수정 (SUPER_ADMIN 전용, 본인 비밀번호 재확인 필수)"""
    auth_password = request.form.get("auth_password", "").strip()
    if not auth_password or not verify_admin_password(session["admin_id"], auth_password):
        flash("현재 관리자 비밀번호 확인에 실패했습니다. 올바른 비밀번호를 입력해주세요.", "danger")
        return redirect(url_for("admin.admins_list"))

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    role = request.form.get("role", "STAFF").strip()
    status = request.form.get("status", "active").strip()

    updater_info = {
        "id": session.get("admin_id"),
        "username": session.get("admin_username"),
        "name": session.get("admin_name")
    }

    success, err = update_admin(
        admin_id=admin_id,
        name=name,
        email=email,
        role=role,
        status=status,
        updater_info=updater_info
    )

    if success:
        flash("관리자 정보 및 권한이 수정되었습니다.", "success")
    else:
        flash(err or "수정에 실패했습니다.", "danger")

    return redirect(url_for("admin.admins_list"))


@admin_bp.route("/admins/<admin_id>/toggle-status", methods=["POST"])
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def admin_toggle_status(admin_id: str):
    """관리자 활성화 / 비활성화 (SUPER_ADMIN 전용, 본인 계정 불가)"""
    new_status = request.form.get("status", "inactive")
    updater_info = {
        "id": session.get("admin_id"),
        "username": session.get("admin_username"),
        "name": session.get("admin_name")
    }

    success, err = toggle_admin_status(admin_id, new_status, updater_info)
    if success:
        stat_name = "활성화" if new_status == "active" else "비활성화"
        flash(f"계정이 {stat_name} 처리되었습니다.", "success")
    else:
        flash(err or "상태 변경 실패", "danger")

    return redirect(url_for("admin.admins_list"))


@admin_bp.route("/admins/<admin_id>/reset-password", methods=["POST"])
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def admin_reset_pw(admin_id: str):
    """관리자 비밀번호 초기화 (SUPER_ADMIN 전용, 본인 비밀번호 재확인 필수)"""
    auth_password = request.form.get("auth_password", "").strip()
    if not auth_password or not verify_admin_password(session["admin_id"], auth_password):
        flash("현재 관리자 비밀번호 확인에 실패했습니다. 올바른 비밀번호를 입력해주세요.", "danger")
        return redirect(url_for("admin.admins_list"))

    new_password = request.form.get("new_password", "").strip()
    must_change = bool(request.form.get("must_change", True))

    operator_info = {
        "id": session.get("admin_id"),
        "username": session.get("admin_username"),
        "name": session.get("admin_name")
    }

    success, err = reset_admin_password(admin_id, new_password, must_change, operator_info)
    if success:
        flash("임시 비밀번호로 초기화되었습니다.", "success")
    else:
        if isinstance(err, list):
            flash("임시 비밀번호가 보안 규칙을 만족하지 않습니다: " + ", ".join(err), "danger")
        else:
            flash(err or "비밀번호 초기화 실패", "danger")

    return redirect(url_for("admin.admins_list"))


@admin_bp.route("/admins/<admin_id>/delete", methods=["POST"])
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def admin_remove(admin_id: str):
    """관리자 계정 삭제 (SUPER_ADMIN 전용, 본인 계정 불가, 본인 비밀번호 재확인 필수)"""
    auth_password = request.form.get("auth_password", "").strip()
    if not auth_password or not verify_admin_password(session["admin_id"], auth_password):
        flash("현재 관리자 비밀번호 확인에 실패했습니다. 올바른 비밀번호를 입력해주세요.", "danger")
        return redirect(url_for("admin.admins_list"))

    operator_info = {
        "id": session.get("admin_id"),
        "username": session.get("admin_username"),
        "name": session.get("admin_name")
    }

    success, err = delete_admin(admin_id, operator_info)
    if success:
        flash("관리자 계정이 삭제되었습니다.", "success")
    else:
        flash(err or "계정 삭제 실패", "danger")

    return redirect(url_for("admin.admins_list"))


# =====================================================
# 9. 관리자 활동 감사 로그 (SUPER_ADMIN, ADMIN 가능)
# =====================================================
@admin_bp.route("/logs")
@admin_login_required
@admin_permission_required("logs_view")
def logs_list():
    """관리자 감사 활동 로그 조회"""
    action_filter = request.args.get("action", "")
    search = request.args.get("search", "").strip()

    logs = list_admin_logs(limit=200, action_filter=action_filter or None, search=search or None)
    return render_template("admin/logs/list.html", logs=logs, action_filter=action_filter, search=search)


# =====================================================
# 10. 시스템 설정 (SUPER_ADMIN 전용)
# =====================================================
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_login_required
@admin_role_required(["SUPER_ADMIN"])
def settings_page():
    """쇼핑몰 시스템 설정 (상호명, 고객센터, 배송비, 재고 부족 기준 등, 본인 비밀번호 재확인 필수)"""
    operator_info = {
        "id": session.get("admin_id"),
        "username": session.get("admin_username"),
        "name": session.get("admin_name")
    }

    if request.method == "POST":
        auth_password = request.form.get("auth_password", "").strip()
        if not auth_password or not verify_admin_password(session["admin_id"], auth_password):
            flash("시스템 설정을 변경하려면 현재 관리자 비밀번호 확인이 필요합니다.", "danger")
            return redirect(url_for("admin.settings_page"))

        settings_keys = [
            "shop_name", "company_name", "cs_phone", "cs_email",
            "low_stock_threshold", "free_shipping_min", "default_shipping_fee"
        ]
        for k in settings_keys:
            if k in request.form:
                val = request.form.get(k, "").strip()
                update_system_setting(k, val, operator_info)

        flash("시스템 설정이 성공적으로 저장되었습니다.", "success")
        return redirect(url_for("admin.settings_page"))

    settings = get_system_settings()
    return render_template("admin/settings.html", settings=settings)
