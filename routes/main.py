"""
=====================================================
메인 라우트 모듈 (routes/main.py)
=====================================================
쇼핑몰의 메인 페이지와 상품 관련 요청을 처리하는 Blueprint 모듈입니다.
Supabase DB와 연동하여 상품 정보를 조회하고 템플릿에 전달합니다.
"""

import os
import sys
import logging
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
    if request.args.get("error") == "sold_out_included":
        error_msg = "품절된 상품이 포함되어 있어 주문할 수 없습니다. 품절 상품을 삭제해 주세요."

    cart_items = []
    total_price = 0

    try:
        supabase = get_supabase_admin_client() or get_supabase_client()
        if supabase:
            # carts + products + product_options JOIN 조회
            cart_resp = supabase.table("carts")\
                .select("id, product_id, option_id, quantity, products(id, name, price, sale_price, status, product_images(image_url, is_thumbnail, display_order)), product_options(id, option_name, option_value, stock)")\
                .eq("user_id", user_id)\
                .execute()

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
    except Exception as e:
        print(f"[장바구니 조회 오류]: {e}", file=sys.stderr)

    has_sold_out_items = any(item.get("is_sold_out") for item in cart_items)

    # 전체 합계 + 배송비 (50,000원 미만이면 3,000원, 이상이면 무료)
    if not cart_items or total_price == 0:
        shipping_fee = 0
    elif total_price < 50000:
        shipping_fee = 3000
    else:
        shipping_fee = 0

    final_total = total_price + shipping_fee

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


@main_bp.route("/order/checkout")
def order_checkout():
    """
    주문/결제 진행 라우트 (GET /order/checkout)
    - 로그인 필수
    - 단, 품절 아이템이 하나라도 있으면 주문 불가 -> /cart?error=sold_out_included 리다이렉트
    - 정상 시 장바구니 결제 모달 오픈 파라미터와 함께 이동
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
    if supabase:
        try:
            cart_resp = supabase.table("carts")\
                .select("id, quantity, product_options(stock), products(status)")\
                .eq("user_id", user_id)\
                .execute()
            items = cart_resp.data or []
            if not items:
                return redirect(url_for("main.view_cart"))

            for cart in items:
                opt = cart.get("product_options") or {}
                prod = cart.get("products") or {}
                stock = int(opt.get("stock") or 0)
                if stock <= 0 or prod.get("status") == "sold_out":
                    return redirect(url_for("main.view_cart", error="sold_out_included"))
        except Exception as e:
            logger.warning(f"체크아웃 전 카트 확인 오류: {e}")

    return redirect(url_for("main.view_cart", checkout="1"))


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
