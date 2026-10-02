"""
=====================================================
메인 라우트 모듈 (routes/main.py)
=====================================================
쇼핑몰의 메인 페이지와 상품 관련 요청을 처리하는 Blueprint 모듈입니다.
Supabase DB와 연동하여 상품 정보를 조회하고 템플릿에 전달합니다.
"""

import os
import re
import sys
import time
import random
import secrets
import logging
from datetime import datetime, timezone
from functools import wraps
from flask import Blueprint, render_template, abort, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from supabase import create_client, Client

# routes.auth에서 admin client 함수 import
from routes.auth import get_supabase_admin_client

# 로깅 설정
logger = logging.getLogger(__name__)

# .env 환경 변수 로드
load_dotenv()

# Blueprint 인스턴스 생성
main_bp = Blueprint("main", __name__)

# Supabase 클라이언트 초기화 함수
def get_supabase_client() -> Client | None:
    """
    환경 변수에서 SUPABASE_URL과 SUPABASE_ANON_KEY를 읽어
    Supabase 클라이언트를 초기화하여 반환합니다.
    """
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        print("[Supabase 경고] SUPABASE_URL 또는 SUPABASE_ANON_KEY가 설정되지 않았습니다.", file=sys.stderr)
        return None

    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        print(f"[Supabase 연결 오류] 클라이언트 초기화 실패: {e}", file=sys.stderr)
        return None


def format_product(item):
    """
    Supabase 상품 레코드를 프론트엔드 표시에 적합한 규격으로 정제합니다.
    - sale_price(할인가)가 있는 경우 실제 판매가(price)를 할인가로 설정하고,
      원래 가격(original_price) 및 할인율(discount_rate)을 함께 산출합니다.
    - 문자열 포맷팅(formatted_price, formatted_original_price) 시 '원'을 정확히 1회만 붙입니다.
    - price 필드는 순수 정수형(int)으로 제공하여 자바스크립트 수치 계산 및 장바구니 합산에 오류가 없도록 합니다.
    """
    price_val = int(item.get("price") or 0)
    sale_price_raw = item.get("sale_price")
    sale_price_val = int(sale_price_raw) if sale_price_raw is not None else None

    # 할인 적용 판단 (sale_price가 존재하고 정상가보다 저렴한 경우)
    if sale_price_val and 0 < sale_price_val < price_val:
        current_price = sale_price_val
        original_price = price_val
        discount_rate = round(((original_price - current_price) / original_price) * 100)
    elif sale_price_val and sale_price_val > price_val:
        # 혹시 sale_price가 정상가, price가 할인가로 입력된 경우
        current_price = price_val
        original_price = sale_price_val
        discount_rate = round(((original_price - current_price) / original_price) * 100)
    else:
        current_price = price_val
        original_price = None
        discount_rate = None

    images = item.get("product_images") or []
    thumbnail_url = None
    for img in images:
        if img.get("is_thumbnail"):
            thumbnail_url = img.get("image_url")
            break
    if not thumbnail_url and images:
        thumbnail_url = images[0].get("image_url")
    if not thumbnail_url:
        thumbnail_url = f"https://picsum.photos/seed/{item.get('id', 'item')}/600/800"

    cat_data = item.get("categories") or {}
    category_slug = (cat_data.get("slug") or "top").upper()
    category_name = cat_data.get("name") or "패션"
    product_colors = {
        "basic-crop-tshirt": ["베이지"],
        "wide-denim-pants": ["청색"],
        "overfit-cotton-jacket": ["검은색", "갈색"],
        "modern-daily-hanbok": ["흰색", "분홍"],
        "classic-stripe-shirt": ["하늘색", "흰색"],
    }.get(item.get("slug"), [])

    return {
        "id": item.get("id"),
        "name": item.get("name"),
        "description": item.get("description", ""),
        "category": category_slug,
        "category_name": category_name,
        "price": current_price,                       # 숫자형: 장바구니 및 수치 계산용 (예: 19900)
        "original_price": original_price,             # 숫자형 (예: 29900)
        "discount_rate": discount_rate,               # 할인율 (%)
        "formatted_price": f"{current_price:,}원",    # '원'이 1개만 붙은 포맷팅 문자열
        "formatted_original_price": f"{original_price:,}원" if original_price else None,
        "thumbnail_url": thumbnail_url,
        "image_url": thumbnail_url,                   # 템플릿 호환용
        "images": [img.get("image_url") for img in images] if images else [thumbnail_url],
        "options": item.get("product_options") or [],
        "colors": product_colors,
        "stock": item.get("stock", 0),
        "status": item.get("status", "active"),
        "rating": 4.9,
        "review_count": 128
    }


def parse_product_option(option):
    option_name = str(option.get("option_name") or "").casefold()
    option_value = str(option.get("option_value") or "").strip()
    color = str(option.get("color") or "").strip()
    size = str(option.get("size") or "").strip()

    if "/" in option_value and ("size" in option_name or "사이즈" in option_name):
        value_color, value_size = (part.strip() for part in option_value.split("/", 1))
        color = color or value_color
        size = size or value_size
    elif not color and not size:
        if "size" in option_name or "사이즈" in option_name:
            size = option_value
        else:
            color = option_value

    return color, size


@main_bp.route("/")
def index():
    """
    메인 쇼핑몰 홈 페이지 라우트

    - Supabase products 테이블에서 추천 상품(is_featured=True, status='active') 최대 4개 조회
    - 가격 포맷팅 ({:,}원) 및 썸네일 이미지 연결
    - index.html 템플릿에 products 변수로 전달
    - 에러 발생 시 빈 리스트로 안전하게 대체
    """
    products = []

    try:
        supabase = get_supabase_client()
        if supabase:
            # 1. products 테이블에서 상품 정보 및 연관된 이미지, 카테고리 조회
            query = supabase.table("products").select("*, product_images(*), categories(*)")
            query = query.eq("is_featured", True).order("created_at", desc=False).limit(8)
            response = query.execute()

            raw_products = response.data or []

            # 2. 템플릿 표시용 데이터 가공
            for item in raw_products:
                item_status = item.get("status")
                is_active = item.get("is_active", True)
                if item_status is not None and item_status != "active":
                    continue
                if not is_active:
                    continue

                products.append(format_product(item))

    except Exception as e:
        # 터미널에 에러 로그 출력 및 앱이 죽지 않도록 빈 리스트로 처리
        print(f"[Supabase 조회 오류] 상품 목록을 불러오는 중 예외가 발생했습니다: {e}", file=sys.stderr)
        products = []

    return render_template(
        "index.html",
        products=products,
        brand_name="VIBE-FASHION",
        brand_slogan="당신의 일상에 특별한 무드를 더하다"
    )


@main_bp.route("/products/<product_id>")
@main_bp.route("/product/<product_id>")
def product_detail(product_id):
    """
    상품 상세 페이지 라우트 (GET /products/<product_id> 및 GET /product/<product_id>)

    :param product_id: URL에서 전달된 상품 ID (UUID 또는 식별자)
    """
    product = None
    related_products = []
    available_colors = []

    try:
        supabase = get_supabase_client()
        if supabase:
            # 1. 해당 상품 상세 조회
            resp = supabase.table("products").select("*, product_images(*), product_options(*), categories(*)").eq("id", product_id).execute()
            if resp.data:
                product = format_product(resp.data[0])

            # 2. 옵션 컬럼과 기존 option_value 형식 모두에서 색상 목록 구성
            try:
                opt_resp = supabase.table("product_options")\
                    .select("color, option_name, option_value")\
                    .eq("product_id", product_id)\
                    .execute()
            except Exception:
                opt_resp = supabase.table("product_options")\
                    .select("option_name, option_value")\
                    .eq("product_id", product_id)\
                    .execute()
            options = opt_resp.data or []
            explicit_colors = [str(row.get("color")).strip() for row in options if row.get("color")]
            if explicit_colors:
                available_colors = sorted(set(explicit_colors), key=str.casefold)
            else:
                parsed_colors = [parse_product_option(row)[0] for row in options]
                available_colors = sorted(set(filter(None, parsed_colors)), key=str.casefold)

            # 3. 연관 추천 상품 (현재 상품 제외 최대 3개)
            rel_resp = supabase.table("products").select("*, product_images(*), categories(*)").neq("id", product_id).limit(3).execute()
            if rel_resp.data:
                for rel in rel_resp.data:
                    related_products.append(format_product(rel))
    except Exception as e:
        print(f"[Supabase 상세 조회 오류]: {e}", file=sys.stderr)

    # 존재하지 않는 상품일 경우 404 에러 반환
    if product is None:
        abort(404)

    return render_template(
        "product_detail.html",
        product=product,
        available_colors=available_colors,
        related_products=related_products,
        brand_name="VIBE-FASHION"
    )


@main_bp.route("/api/products/<product_id>/sizes")
@main_bp.route("/products/<product_id>/options")
@main_bp.route("/api/products/<product_id>/options")
def get_product_sizes(product_id):
    """
    상품 색상별 사이즈 및 재고 목록 조회 API (GET /api/products/<product_id>/sizes?color=<선택한 색상>)
    - product_options 테이블에서 product_id와 color로 필터링
    - id(product_option_id), size, stock을 JSON 배열로 반환
      예: [{"id": "uuid-xxx", "size": "S", "stock": 3}, ...]
    """
    color = request.args.get("color", "").strip()
    if not color:
        return jsonify([])

    result = []
    try:
        supabase = get_supabase_client()
        if supabase:
            # 실제 DB의 option_value와 color/size 컬럼을 함께 지원
            try:
                resp = supabase.table("product_options")\
                    .select("id, option_name, option_value, color, size, stock")\
                    .eq("product_id", product_id)\
                    .execute()
            except Exception:
                resp = supabase.table("product_options")\
                    .select("id, option_name, option_value, stock")\
                    .eq("product_id", product_id)\
                    .execute()

            raw_list = []
            for item in resp.data or []:
                option_color, option_size = parse_product_option(item)
                if option_color.casefold() == color.casefold() and option_size:
                    raw_list.append({
                        "id": item.get("id"),
                        "size": option_size,
                        "stock": item.get("stock")
                    })
            # 사이즈 순서 정렬 (XS -> S -> M -> L -> XL -> XXL -> FREE)
            size_order = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "XXL": 6, "FREE": 7}
            raw_list.sort(key=lambda x: size_order.get((x.get("size") or "").upper(), 99))

            # id, size, stock 형태의 깔끔한 딕셔너리 리스트로 정제
            result = [
                {
                    "id": item.get("id"),
                    "size": item.get("size"),
                    "stock": int(item.get("stock") or 0)
                }
                for item in raw_list
            ]
    except Exception as e:
        print(f"[사이즈 목록 API 조회 오류]: {e}", file=sys.stderr)
        return jsonify([]), 500

    return jsonify(result)


@main_bp.route("/cart/add", methods=["POST"])
def add_to_cart():
    """
    장바구니 담기 API (POST /cart/add)
    
    Request JSON:
    - product_option_id: 상품 옵션 ID (UUID)
    - quantity: 수량 (정수, > 0)
    
    Response:
    - 성공 (200): {"success": true, "message": "장바구니에 담겼습니다"}
    - 재고 부족 (400): {"success": false, "message": "재고가 부족합니다(현재 N개)"}
    - 기타 에러 (400/500): {"success": false, "message": "에러 메시지"}
    """
    # 1. 로그인 체크
    user_id = session.get("user_id")
    print(f"[Cart] Session user_id: {user_id}", file=sys.stderr)
    
    if not user_id:
        # session['user'] 딕셔너리에 id가 있는 경우 동기화
        user_obj = session.get("user")
        print(f"[Cart] Session user obj: {user_obj}", file=sys.stderr)
        
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
            session["user_id"] = user_id
            print(f"[Cart] Sync'd user_id: {user_id}", file=sys.stderr)
        else:
            print(f"[Cart] No user_id found, login required", file=sys.stderr)
            return jsonify({
                "success": False,
                "message": "로그인이 필요합니다. 다시 로그인해주세요."
            }), 401
    
    # 2. 요청 body에서 product_option_id, quantity 추출
    try:
        data = request.get_json() or {}
        product_option_id = data.get("product_option_id", "").strip()
        quantity = data.get("quantity")
        
        if not product_option_id:
            return jsonify({
                "success": False,
                "message": "product_option_id가 필요합니다."
            }), 400
        
        # quantity를 정수로 변환
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "message": "quantity는 정수여야 합니다."
            }), 400
        
        if quantity <= 0:
            return jsonify({
                "success": False,
                "message": "quantity는 1 이상이어야 합니다."
            }), 400
    
    except Exception as e:
        print(f"[장바구니 요청 파싱 오류]: {e}", file=sys.stderr)
        return jsonify({
            "success": False,
            "message": "잘못된 요청입니다."
        }), 400
    
    # 3. Supabase 클라이언트 초기화 (admin client 우선 사용)
    supabase = get_supabase_admin_client()
    if not supabase:
        supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({
            "success": False,
            "message": "데이터베이스 연결 실패"
        }), 500
    
    try:
        # 4. product_options 테이블에서 option 조회
        opt_resp = supabase.table("product_options")\
            .select("id, product_id, stock")\
            .eq("id", product_option_id)\
            .execute()
        
        if not opt_resp.data:
            return jsonify({
                "success": False,
                "message": "존재하지 않는 상품 옵션입니다."
            }), 404
        
        option = opt_resp.data[0]
        product_id = option.get("product_id")
        current_stock = int(option.get("stock") or 0)
        
        # 5. 요청 수량 vs 현재 재고 체크
        if current_stock < quantity:
            return jsonify({
                "success": False,
                "message": f"재고가 부족합니다(현재 {current_stock}개)"
            }), 400
        
        # 6. carts 테이블에서 동일 옵션이 이미 있는지 확인
        cart_resp = supabase.table("carts")\
            .select("id, quantity")\
            .eq("user_id", user_id)\
            .eq("option_id", product_option_id)\
            .execute()
        
        # 7. UPSERT 처리: 있으면 UPDATE, 없으면 INSERT
        if cart_resp.data:
            # 이미 있는 경우: quantity 누적
            existing_cart = cart_resp.data[0]
            cart_id = existing_cart.get("id")
            existing_qty = int(existing_cart.get("quantity") or 0)
            new_qty = existing_qty + quantity
            
            # 누적 수량이 재고를 초과하는지 확인
            if new_qty > current_stock:
                return jsonify({
                    "success": False,
                    "message": f"재고가 부족합니다(현재 {current_stock}개)"
                }), 400
            
            # UPDATE
            update_resp = supabase.table("carts")\
                .update({"quantity": new_qty})\
                .eq("id", cart_id)\
                .execute()
            
            if not update_resp.data:
                raise Exception("UPDATE 실패")
        
        else:
            # 없는 경우: INSERT
            insert_resp = supabase.table("carts")\
                .insert({
                    "user_id": user_id,
                    "product_id": product_id,
                    "option_id": product_option_id,
                    "quantity": quantity
                })\
                .execute()
            
            if not insert_resp.data:
                raise Exception("INSERT 실패")
        
        # 8. 성공 응답
        return jsonify({
            "success": True,
            "message": "장바구니에 담겼습니다"
        }), 200
    
    except Exception as e:
        print(f"[장바구니 담기 오류]: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"장바구니 추가 중 오류가 발생했습니다. ({str(e)[:100]})"
        }), 500


@main_bp.route("/api/cart", methods=["GET"])
def get_cart_items():
    """현재 로그인 사용자의 DB 장바구니를 JSON으로 반환합니다."""
    user_id = session.get("user_id")
    if not user_id:
        user = session.get("user")
        user_id = user.get("id") if isinstance(user, dict) else None
    if not user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    supabase = get_supabase_admin_client() or get_supabase_client()
    if not supabase:
        return jsonify({"success": False, "message": "데이터베이스 연결에 실패했습니다."}), 500

    try:
        response = supabase.table("carts")\
            .select("id, quantity, products(id, name, price, sale_price, status, product_images(image_url, is_thumbnail, display_order)), product_options(id, option_name, option_value, stock)")\
            .eq("user_id", user_id)\
            .execute()

        items = []
        for cart in response.data or []:
            product = cart.get("products") or {}
            option = cart.get("product_options") or {}
            formatted_product = format_product(product)
            color, size = parse_product_option(option)
            quantity = int(cart.get("quantity") or 1)
            price = int(formatted_product.get("price") or 0)
            stock = int(option.get("stock") or 0) if option else 0
            is_sold_out = (stock <= 0) or (product.get("status") == "sold_out")
            items.append({
                "cart_id": cart.get("id"),
                "name": formatted_product.get("name") or "상품",
                "price": price,
                "quantity": quantity,
                "stock": stock,
                "is_sold_out": is_sold_out,
                "subtotal": price * quantity,
                "image_url": formatted_product.get("thumbnail_url") or "",
                "color": color,
                "size": size
            })
        return jsonify({"success": True, "items": items})
    except Exception as e:
        logger.exception("장바구니 API 조회 실패")
        return jsonify({"success": False, "message": "장바구니를 불러오지 못했습니다."}), 500


def _fetch_cart_details(supabase, user_id):
    """
    사용자의 장바구니 항목들과 금액 정보, 품절 여부를 조회하여 가공합니다.
    (carts + products + product_options JOIN)
    """
    cart_resp = supabase.table("carts")\
        .select("id, product_id, option_id, quantity, products(id, name, price, sale_price, status, product_images(image_url, is_thumbnail, display_order)), product_options(id, option_name, option_value, stock)")\
        .eq("user_id", user_id)\
        .execute()

    cart_items = []
    total_price = 0
    has_sold_out_items = False

    if cart_resp.data:
        for cart in cart_resp.data:
            product = cart.get("products") or {}
            option = cart.get("product_options") or {}
            formatted_product = format_product(product)
            color, size = parse_product_option(option)
            quantity = int(cart.get("quantity") or 1)
            product_price = int(formatted_product.get("price") or 0)
            item_total = product_price * quantity
            total_price += item_total

            stock = int(option.get("stock") or 0) if option else 0
            is_sold_out = (stock <= 0) or (product.get("status") == "sold_out")
            if is_sold_out:
                has_sold_out_items = True

            cart_items.append({
                "cart_id": cart.get("id"),
                "product_id": product.get("id"),
                "option_id": option.get("id") if option else None,
                "product_name": formatted_product.get("name"),
                "color": color,
                "size": size,
                "price": product_price,
                "quantity": quantity,
                "stock": stock,
                "is_sold_out": is_sold_out,
                "item_total": item_total,
                "formatted_price": f"{product_price:,}원",
                "formatted_item_total": f"{item_total:,}원",
                "thumbnail_url": formatted_product.get("thumbnail_url") or f"https://picsum.photos/seed/{product.get('id', 'item')}/200/200"
            })

    if not cart_items or total_price == 0:
        shipping_fee = 0
    elif total_price < 50000:
        shipping_fee = 3000
    else:
        shipping_fee = 0

    final_total = total_price + shipping_fee

    return cart_items, total_price, shipping_fee, final_total, has_sold_out_items


@main_bp.route("/cart")
def view_cart():
    """
    장바구니 조회 페이지 (GET /cart)
    - carts + product_options + products JOIN 조회
    - 각 아이템: 상품명, 색상, 사이즈, 수량, 단가, 소계
    - 품절(stock=0) 아이템은 "품절됨" 배지 + 수량 변경 비활성화
    - 전체 합계 + 배송비 (50,000원 미만 3,000원, 이상 무료)
    - "주문하기" 버튼 -> /order/checkout (품절 상품 포함 시 비활성화 + 안내 문구)
    """
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
            session["user_id"] = user_id
        else:
            return redirect(url_for("auth.login", error="login_required"))

    error_msg = None
    err = request.args.get("error")
    if err in ("sold_out", "sold_out_included"):
        error_msg = "품절된 상품이 있어 주문할 수 없습니다"

    cart_items = []
    total_price = 0
    shipping_fee = 0
    final_total = 0
    has_sold_out_items = False

    try:
        supabase = get_supabase_admin_client() or get_supabase_client()
        if supabase:
            cart_items, total_price, shipping_fee, final_total, has_sold_out_items = _fetch_cart_details(supabase, user_id)
    except Exception as e:
        print(f"[장바구니 조회 오류]: {e}", file=sys.stderr)

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total_price=total_price,
        shipping_fee=shipping_fee,
        final_total=final_total,
        formatted_total=f"{total_price:,}원",
        formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
        formatted_final_total=f"{final_total:,}원",
        has_sold_out_items=has_sold_out_items,
        error_message=error_msg,
        brand_name="VIBE-FASHION"
    )


@main_bp.route("/api/user/default-address")
def get_default_address():
    """
    마이페이지에 저장된 기본 배송지 정보 조회 API (GET /api/user/default-address)
    - profiles 테이블 조회 및 session/metadata 보강
    """
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
            session["user_id"] = user_id
        else:
            return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    supabase = get_supabase_admin_client() or get_supabase_client()
    if not supabase:
        return jsonify({"success": False, "message": "데이터베이스 연결에 실패했습니다."}), 500

    name = ""
    phone = ""
    address = ""
    address_detail = ""

    try:
        prof_resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if prof_resp.data:
            prof = prof_resp.data[0]
            name = prof.get("full_name") or ""
            phone = prof.get("phone") or ""
            if "address" in prof and prof.get("address"):
                address = prof.get("address") or ""

        # 세션 및 auth 메타데이터에서 추가 정보 보강
        session_user = session.get("user") or {}
        if not name:
            name = session_user.get("name") or ""
        if not phone:
            phone = session_user.get("phone") or ""
        if not address:
            address = session_user.get("address") or ""
        if not address_detail:
            address_detail = session_user.get("address_detail") or ""

        return jsonify({
            "success": True,
            "recipient_name": name,
            "recipient_phone": phone,
            "shipping_address": address,
            "shipping_address_detail": address_detail
        })
    except Exception as e:
        logger.error(f"기본 배송지 조회 중 예외 발생: {e}")
        return jsonify({"success": False, "message": "기본 배송지를 불러오지 못했습니다."}), 500


@main_bp.route("/order/checkout", methods=["GET"])
def order_checkout():
    """
    주문서 페이지 라우트 (GET /order/checkout)
    - 로그인 필수, 미로그인 시 /login 리다이렉트
    - 장바구니 비어있으면 /cart 리다이렉트
    - 품절(stock=0) 아이템이 하나라도 있으면 /cart 리다이렉트 및 안내
    - GET: 주문서 페이지(checkout.html) 렌더링
    """
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
            session["user_id"] = user_id
        else:
            return redirect(url_for("auth.login", error="login_required"))

    supabase = get_supabase_admin_client() or get_supabase_client()
    if not supabase:
        abort(500)

    try:
        cart_items, total_price, shipping_fee, final_total, has_sold_out_items = _fetch_cart_details(supabase, user_id)
    except Exception as e:
        logger.error(f"주문서 장바구니 조회 실패: {e}")
        return redirect(url_for("main.view_cart"))

    # 장바구니가 비어있는 경우
    if not cart_items:
        return redirect(url_for("main.view_cart"))

    # 품절 아이템이 하나라도 있는 경우 -> /cart로 리다이렉트
    if has_sold_out_items:
        return redirect(url_for("main.view_cart", error="sold_out"))

    default_profile = {
        "name": "",
        "phone": "",
        "address": "",
        "address_detail": ""
    }
    try:
        prof_resp = supabase.table("profiles").select("*").eq("id", user_id).execute()
        if prof_resp.data:
            prof = prof_resp.data[0]
            default_profile["name"] = prof.get("full_name") or ""
            default_profile["phone"] = prof.get("phone") or ""
            if "address" in prof and prof.get("address"):
                default_profile["address"] = prof.get("address") or ""
    except Exception as pe:
        logger.warning(f"체크아웃 프로필 조회 경고: {pe}")

    session_user = session.get("user") or {}
    if not default_profile["name"]:
        default_profile["name"] = session_user.get("name") or ""
    if not default_profile["phone"]:
        default_profile["phone"] = session_user.get("phone") or ""
    if not default_profile["address"]:
        default_profile["address"] = session_user.get("address") or ""
    if not default_profile["address_detail"]:
        default_profile["address_detail"] = session_user.get("address_detail") or ""

    return render_template(
        "checkout.html",
        cart_items=cart_items,
        total_price=total_price,
        shipping_fee=shipping_fee,
        final_total=final_total,
        formatted_total=f"{total_price:,}원",
        formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
        formatted_final_total=f"{final_total:,}원",
        default_profile=default_profile,
        brand_name="VIBE-FASHION"
    )


@main_bp.route("/order/create", methods=["POST"])
def order_create():
    """
    주문 생성 API 및 폼 제출 라우트 (POST /order/create)
    처리 순서:
    1. 장바구니 조회 + 재고 확인 (재고 부족 시 에러, 처리 중단, 아무 것도 쓰지 않음)
    2. 배송지 입력값 서버 측 재검증 (수령인 2자 이상, 휴대폰 번호 010-0000-0000 패턴, 주소 최소 5자 이상)
    3. 주문번호 생성: 'VF-' + 오늘날짜(YYYYMMDD) + '-' + 4자리 랜덤숫자 + 밀리초 타임스탬프 뒷 3자리
    4. orders 테이블에 INSERT (status='paid', paid_at=now())
    5. order_items INSERT (상품명, 색상, 사이즈, 가격 스냅샷)
    6. product_options.stock 차감 (조건부 UPDATE: UPDATE ... SET stock = stock - 수량 WHERE id = 옵션ID AND stock >= 수량)
       - 영향받은 행이 0개면 "방금 재고가 소진되었습니다" 에러로 롤백 처리
    7. carts 아이템 DELETE
    8. /order/complete/<order_id> 리다이렉트
    기술: service_role 키로 재고 차감 (RLS 우회 필요)
    """
    # 0. 로그인 확인
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
            session["user_id"] = user_id
        else:
            if request.is_json:
                return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401
            return redirect(url_for("auth.login", error="login_required"))

    # service_role 관리자 클라이언트 획득 (RLS 우회 및 트랜잭션 작업용)
    admin_supabase = get_supabase_admin_client() or get_supabase_client()
    if not admin_supabase:
        if request.is_json:
            return jsonify({"success": False, "message": "데이터베이스 연결에 실패했습니다."}), 500
        abort(500)

    # 1. 장바구니 조회 + 재고 확인 (재고 부족 시 에러, 처리 중단, 아무 것도 쓰지 않음)
    try:
        cart_items, total_price, shipping_fee, final_total, has_sold_out_items = _fetch_cart_details(admin_supabase, user_id)
    except Exception as e:
        logger.error(f"주문 생성 전 장바구니 조회 실패: {e}")
        if request.is_json:
            return jsonify({"success": False, "message": "장바구니 조회 중 오류가 발생했습니다."}), 500
        return redirect(url_for("main.view_cart"))

    if not cart_items:
        if request.is_json:
            return jsonify({"success": False, "message": "장바구니가 비어 있습니다.", "redirect_url": url_for("main.view_cart")}), 400
        return redirect(url_for("main.view_cart"))

    # 장바구니 각 품목 재고 직접 확인 (요청 수량 > 현재 재고이거나 품절된 경우 즉시 중단)
    for item in cart_items:
        req_qty = int(item.get("quantity") or 1)
        cur_stock = int(item.get("stock") or 0)
        prod_name = item.get("product_name") or "상품"
        if item.get("is_sold_out") or cur_stock < req_qty:
            error_msg = f"'{prod_name}' 상품의 재고가 부족합니다 (현재 재고: {cur_stock}개)."
            if request.is_json:
                return jsonify({"success": False, "message": error_msg, "redirect_url": url_for("main.view_cart")}), 400
            return redirect(url_for("main.view_cart", error="sold_out"))

    # 2. 배송지 입력값 서버 측 재검증
    data = request.get_json(silent=True) if request.is_json else request.form
    if not data:
        data = request.form

    recipient_name = (data.get("recipient_name") or "").strip()
    recipient_phone = (data.get("recipient_phone") or "").strip()
    shipping_address = (data.get("shipping_address") or "").strip()
    shipping_address_detail = (data.get("shipping_address_detail") or "").strip()
    delivery_memo = (data.get("delivery_memo") or "").strip()

    if not recipient_name or len(recipient_name) < 2:
        error_msg = "수령인 이름을 2자 이상 입력해주세요."
        if request.is_json:
            return jsonify({"success": False, "message": error_msg}), 400
        return render_template(
            "checkout.html",
            cart_items=cart_items,
            total_price=total_price,
            shipping_fee=shipping_fee,
            final_total=final_total,
            formatted_total=f"{total_price:,}원",
            formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
            formatted_final_total=f"{final_total:,}원",
            default_profile=data,
            error_message=error_msg,
            brand_name="VIBE-FASHION"
        ), 400

    if not re.match(r"^010-\d{4}-\d{4}$", recipient_phone):
        error_msg = "휴대폰 번호는 010-0000-0000 형식으로 입력해주세요."
        if request.is_json:
            return jsonify({"success": False, "message": error_msg}), 400
        return render_template(
            "checkout.html",
            cart_items=cart_items,
            total_price=total_price,
            shipping_fee=shipping_fee,
            final_total=final_total,
            formatted_total=f"{total_price:,}원",
            formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
            formatted_final_total=f"{final_total:,}원",
            default_profile=data,
            error_message=error_msg,
            brand_name="VIBE-FASHION"
        ), 400

    if not shipping_address or len(shipping_address) < 5:
        error_msg = "배송 주소는 최소 5자 이상 입력해주세요."
        if request.is_json:
            return jsonify({"success": False, "message": error_msg}), 400
        return render_template(
            "checkout.html",
            cart_items=cart_items,
            total_price=total_price,
            shipping_fee=shipping_fee,
            final_total=final_total,
            formatted_total=f"{total_price:,}원",
            formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
            formatted_final_total=f"{final_total:,}원",
            default_profile=data,
            error_message=error_msg,
            brand_name="VIBE-FASHION"
        ), 400

    # 3. 주문번호 생성: 'VF-' + 오늘날짜(YYYYMMDD) + '-' + 4자리 랜덤숫자 + 밀리초 타임스탬프 뒷 3자리
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y%m%d")
    rand_4digit = f"{random.randint(0, 9999):04d}"
    millis_suffix = f"{int(time.time() * 1000) % 1000:03d}"
    order_number = f"VF-{today_str}-{rand_4digit}{millis_suffix}"

    created_order_id = None
    subtracted_options = []  # 롤백을 위한 차감 이력 [(opt_id, qty)]

    try:
        # 4. orders 테이블에 INSERT (status='paid', paid_at=now())
        order_payload = {
            "order_number": order_number,
            "user_id": user_id,
            "total_amount": total_price,
            "discount_amount": 0,
            "shipping_fee": shipping_fee,
            "final_amount": final_total,
            "status": "paid",
            "recipient_name": recipient_name,
            "recipient_phone": recipient_phone,
            "shipping_address": shipping_address,
            "shipping_address_detail": shipping_address_detail or None,
            "delivery_memo": delivery_memo or None,
            "payment_method": "더미 결제 (간편결제)",
            "paid_at": now_utc.isoformat()
        }

        order_res = admin_supabase.table("orders").insert(order_payload).execute()
        if not order_res.data:
            raise Exception("orders 테이블 주문 생성 실패")

        created_order_id = order_res.data[0]["id"]

        # 5. order_items INSERT (상품명, 색상, 사이즈, 가격 스냅샷)
        order_items_payload = []
        for item in cart_items:
            opt_parts = []
            if item.get("color"):
                opt_parts.append(f"색상: {item['color']}")
            if item.get("size"):
                opt_parts.append(f"사이즈: {item['size']}")
            opt_desc = " / ".join(opt_parts) if opt_parts else None

            order_items_payload.append({
                "order_id": created_order_id,
                "product_id": item.get("product_id"),
                "option_id": item.get("option_id"),
                "product_name": item.get("product_name"),
                "option_name": opt_desc,
                "unit_price": item.get("price", 0),
                "quantity": item.get("quantity", 1),
                "total_price": item.get("item_total", 0)
            })

        if order_items_payload:
            items_res = admin_supabase.table("order_items").insert(order_items_payload).execute()
            if not items_res.data:
                raise Exception("order_items 테이블 상세 생성 실패")

        # 6. product_options.stock 차감 — 반드시 조건부 UPDATE 사용:
        # UPDATE ... SET stock = stock - 수량 WHERE id = 옵션ID AND stock >= 수량
        # 영향받은 행이 0개면 "방금 재고가 소진되었습니다" 에러로 롤백 처리
        for item in cart_items:
            opt_id = item.get("option_id")
            qty = int(item.get("quantity") or 1)
            if not opt_id:
                continue

            # 현재 최신 stock을 가져와서 조건부 UPDATE 수행
            cur_opt_resp = admin_supabase.table("product_options").select("stock").eq("id", opt_id).execute()
            if not cur_opt_resp.data:
                raise Exception("방금 재고가 소진되었습니다")

            current_stock = int(cur_opt_resp.data[0].get("stock") or 0)
            new_stock = current_stock - qty

            # 조건부 UPDATE: WHERE id = opt_id AND stock >= qty
            update_res = admin_supabase.table("product_options")\
                .update({"stock": new_stock})\
                .eq("id", opt_id)\
                .gte("stock", qty)\
                .execute()

            # 영향받은 행이 0개인지 확인
            if not update_res.data or len(update_res.data) == 0:
                raise Exception("방금 재고가 소진되었습니다")

            subtracted_options.append((opt_id, qty))

        # 7. carts 아이템 DELETE
        admin_supabase.table("carts").delete().eq("user_id", user_id).execute()

        # 8. /order/complete/<order_id> 리다이렉트
        complete_url = url_for("main.order_complete", order_id_or_number=created_order_id)

        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "success": True,
                "order_id": created_order_id,
                "order_number": order_number,
                "redirect_url": complete_url,
                "message": "주문 및 결제가 성공적으로 완료되었습니다."
            })

        return redirect(complete_url)

    except Exception as e:
        logger.error(f"주문 생성 중 예외 발생: {e}")
        err_str = str(e)

        # 롤백 처리: 이미 차감된 옵션 재고 복구
        for opt_id, qty in subtracted_options:
            try:
                opt_info = admin_supabase.table("product_options").select("stock").eq("id", opt_id).execute()
                if opt_info.data:
                    c_stock = int(opt_info.data[0].get("stock") or 0)
                    admin_supabase.table("product_options").update({"stock": c_stock + qty}).eq("id", opt_id).execute()
            except Exception as re_stock_err:
                logger.error(f"재고 롤백 실패 (opt_id={opt_id}): {re_stock_err}")

        # 롤백 처리: 이미 생성된 주문(orders) 및 주문상품(order_items) 삭제
        if created_order_id:
            try:
                admin_supabase.table("orders").delete().eq("id", created_order_id).execute()
            except Exception as re_order_err:
                logger.error(f"주문 롤백 실패 (order_id={created_order_id}): {re_order_err}")

        # 사용자 노출 에러 메시지 결정
        if "방금 재고가 소진되었습니다" in err_str:
            user_msg = "방금 재고가 소진되었습니다"
        else:
            user_msg = "주문 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

        if request.is_json:
            return jsonify({"success": False, "message": user_msg}), 400

        return render_template(
            "checkout.html",
            cart_items=cart_items,
            total_price=total_price,
            shipping_fee=shipping_fee,
            final_total=final_total,
            formatted_total=f"{total_price:,}원",
            formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
            formatted_final_total=f"{final_total:,}원",
            default_profile=data,
            error_message=user_msg,
            brand_name="VIBE-FASHION"
        ), 400


@main_bp.route("/order/complete/<order_id_or_number>")
def order_complete(order_id_or_number):
    """
    주문 완료 결과 페이지 (GET /order/complete/<order_id_or_number>)
    - order_id (UUID) 또는 order_number 둘 다 지원
    - 주문 번호, 결제 금액, 배송지 정보, 주문 아이템 요약 표시
    """
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
            session["user_id"] = user_id
        else:
            return redirect(url_for("auth.login", error="login_required"))

    supabase = get_supabase_admin_client() or get_supabase_client()
    if not supabase:
        abort(500)

    try:
        # UUID 형식 여부에 따라 id 또는 order_number로 주문 조회
        query = supabase.table("orders").select("*").eq("user_id", user_id)
        if re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", order_id_or_number):
            order_resp = query.eq("id", order_id_or_number).execute()
        else:
            order_resp = query.eq("order_number", order_id_or_number).execute()

        if not order_resp.data:
            abort(404)

        order = order_resp.data[0]

        # 주문 상품 항목 조회
        items_resp = supabase.table("order_items")\
            .select("*, products(id, product_images(image_url, is_thumbnail))")\
            .eq("order_id", order["id"])\
            .execute()

        order_items = []
        for row in items_resp.data or []:
            prod = row.get("products") or {}
            images = prod.get("product_images") or []
            thumb = next((img.get("image_url") for img in images if img.get("is_thumbnail")), None)
            if not thumb and images:
                thumb = images[0].get("image_url")
            if not thumb:
                thumb = f"https://picsum.photos/seed/{row.get('product_id', 'item')}/200/200"

            order_items.append({
                "product_name": row.get("product_name"),
                "option_name": row.get("option_name") or "",
                "quantity": int(row.get("quantity") or 1),
                "unit_price": int(row.get("unit_price") or 0),
                "total_price": int(row.get("total_price") or 0),
                "formatted_unit_price": f"{int(row.get('unit_price') or 0):,}원",
                "formatted_total_price": f"{int(row.get('total_price') or 0):,}원",
                "thumbnail_url": thumb
            })

        total_amount = int(order.get("total_amount") or 0)
        shipping_fee = int(order.get("shipping_fee") or 0)
        final_amount = int(order.get("final_amount") or 0)

        formatted_created_at = order.get("created_at", "")
        try:
            dt = datetime.fromisoformat(formatted_created_at.replace("Z", "+00:00"))
            formatted_created_at = dt.strftime("%Y년 %m월 %d일 %H:%M")
        except Exception:
            pass

        return render_template(
            "order_complete.html",
            order=order,
            order_items=order_items,
            formatted_created_at=formatted_created_at,
            formatted_total_amount=f"{total_amount:,}원",
            formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
            formatted_final_amount=f"{final_amount:,}원",
            brand_name="VIBE-FASHION"
        )
    except Exception as e:
        logger.error(f"주문 완료 페이지 조회 실패: {e}")
        abort(500)

        formatted_created_at = order.get("created_at", "")
        try:
            dt = datetime.fromisoformat(formatted_created_at.replace("Z", "+00:00"))
            formatted_created_at = dt.strftime("%Y년 %m월 %d일 %H:%M")
        except Exception:
            pass

        return render_template(
            "order_complete.html",
            order=order,
            order_items=order_items,
            formatted_created_at=formatted_created_at,
            formatted_total_amount=f"{total_amount:,}원",
            formatted_shipping_fee="무료" if shipping_fee == 0 else f"{shipping_fee:,}원",
            formatted_final_amount=f"{final_amount:,}원",
            brand_name="VIBE-FASHION"
        )
    except Exception as e:
        logger.error(f"주문 완료 페이지 조회 실패: {e}")
        abort(500)


@main_bp.route("/cart/<cart_id>", methods=["PATCH"])
def update_cart_quantity(cart_id):
    """
    장바구니 수량 변경 API (PATCH /cart/<cart_id>)
    
    Request JSON:
    - quantity: 변경할 새 수량 (정수, >= 1)
    
    Response:
    - 성공 (200): {"success": true, "subtotal": 50000, "message": "수량이 변경되었습니다"}
    - 실패 (400/404): {"success": false, "message": "에러 메시지"}
    """
    # 1. 로그인 확인
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
        else:
            return jsonify({
                "success": False,
                "message": "로그인이 필요합니다"
            }), 401
    
    # 2. 요청 body에서 quantity 추출
    try:
        data = request.get_json() or {}
        quantity = data.get("quantity")
        
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return jsonify({
                "success": False,
                "message": "quantity는 정수여야 합니다"
            }), 400
        
        if quantity < 1:
            return jsonify({
                "success": False,
                "message": "수량은 1 이상이어야 합니다"
            }), 400
    
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "잘못된 요청입니다"
        }), 400
    
    # 3. Supabase 클라이언트 초기화
    supabase = get_supabase_admin_client()
    if not supabase:
        supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({
            "success": False,
            "message": "데이터베이스 연결 실패"
        }), 500
    
    try:
        # 4. cart 조회 (해당 cart_id가 현재 사용자 소유인지 확인)
        cart_resp = supabase.table("carts")\
            .select("id, user_id, option_id, quantity")\
            .eq("id", cart_id)\
            .execute()
        
        if not cart_resp.data:
            return jsonify({
                "success": False,
                "message": "존재하지 않는 장바구니 항목입니다"
            }), 404
        
        cart = cart_resp.data[0]
        
        # 5. 본인 소유 확인 (보안: 다른 사용자의 cart 접근 차단)
        if str(cart.get("user_id")) != str(user_id):
            return jsonify({
                "success": False,
                "message": "이 장바구니 항목에 접근할 권한이 없습니다"
            }), 403
        
        option_id = cart.get("option_id")
        
        # 6. product_options에서 stock 조회 및 product 정보 함께 조회
        opt_resp = supabase.table("product_options")\
            .select("id, product_id, stock")\
            .eq("id", option_id)\
            .execute()
        
        if not opt_resp.data:
            return jsonify({
                "success": False,
                "message": "상품 옵션을 찾을 수 없습니다"
            }), 404
        
        option = opt_resp.data[0]
        stock = int(option.get("stock") or 0)
        product_id = option.get("product_id")
        
        # 7. 변경하려는 수량이 재고를 초과하는지 확인
        if quantity > stock:
            return jsonify({
                "success": False,
                "message": f"재고가 부족합니다(현재 {stock}개)"
            }), 400
        
        # 8. carts 테이블 UPDATE
        update_resp = supabase.table("carts")\
            .update({"quantity": quantity})\
            .eq("id", cart_id)\
            .execute()
        
        if not update_resp.data:
            raise Exception("UPDATE 실패")
        
        # 9. 새 소계(subtotal) 계산 (할인가 반영)
        prod_resp = supabase.table("products")\
            .select("price, sale_price")\
            .eq("id", product_id)\
            .execute()
        
        product_price = 0
        if prod_resp.data:
            prod_data = prod_resp.data[0]
            base_price = int(prod_data.get("price") or 0)
            sale_price = int(prod_data.get("sale_price") or 0)
            product_price = sale_price if 0 < sale_price < base_price else base_price
        
        subtotal = product_price * quantity
        
        # 10. 성공 응답
        return jsonify({
            "success": True,
            "subtotal": subtotal,
            "message": "수량이 변경되었습니다"
        }), 200
    
    except Exception as e:
        print(f"[장바구니 수량 변경 오류]: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"수량 변경 중 오류가 발생했습니다. ({str(e)[:100]})"
        }), 500


@main_bp.route("/cart/<cart_id>", methods=["DELETE"])
def remove_from_cart(cart_id):
    """
    장바구니 항목 삭제 API (DELETE /cart/<cart_id>)
    
    Response:
    - 성공 (200): {"success": true, "message": "장바구니에서 제거되었습니다"}
    - 실패 (400/404): {"success": false, "message": "에러 메시지"}
    """
    # 1. 로그인 확인
    user_id = session.get("user_id")
    if not user_id:
        user_obj = session.get("user")
        if isinstance(user_obj, dict) and user_obj.get("id"):
            user_id = user_obj["id"]
        else:
            return jsonify({
                "success": False,
                "message": "로그인이 필요합니다"
            }), 401
    
    # 2. Supabase 클라이언트 초기화
    supabase = get_supabase_admin_client()
    if not supabase:
        supabase = get_supabase_client()
    
    if not supabase:
        return jsonify({
            "success": False,
            "message": "데이터베이스 연결 실패"
        }), 500
    
    try:
        # 3. cart 조회 (본인 소유 확인)
        cart_resp = supabase.table("carts")\
            .select("id, user_id")\
            .eq("id", cart_id)\
            .execute()
        
        if not cart_resp.data:
            return jsonify({
                "success": False,
                "message": "존재하지 않는 장바구니 항목입니다"
            }), 404
        
        cart = cart_resp.data[0]
        
        # 4. 본인 소유 확인 (보안: 다른 사용자의 cart_id 접근 차단)
        if str(cart.get("user_id")) != str(user_id):
            return jsonify({
                "success": False,
                "message": "이 장바구니 항목에 접근할 권한이 없습니다"
            }), 403
        
        # 5. carts 테이블에서 DELETE
        delete_resp = supabase.table("carts")\
            .delete()\
            .eq("id", cart_id)\
            .execute()
        
        # 6. 성공 응답
        return jsonify({
            "success": True,
            "message": "장바구니에서 제거되었습니다"
        }), 200
    
    except Exception as e:
        print(f"[장바구니 삭제 오류]: {e}", file=sys.stderr)
        return jsonify({
            "success": False,
            "message": "삭제 중 오류가 발생했습니다"
        }), 500
