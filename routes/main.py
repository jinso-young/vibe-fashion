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
from flask import Blueprint, render_template, abort, request, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client

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

            # 2. product_options 테이블에서 색상(color) 목록 DISTINCT 조회
            opt_resp = supabase.table("product_options").select("color").eq("product_id", product_id).not_.is_("color", "null").execute()
            if opt_resp.data:
                raw_colors = [row.get("color") for row in opt_resp.data if row.get("color")]
                # 중복 제거 및 정렬
                available_colors = sorted(list(dict.fromkeys(raw_colors)))

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
    - size, stock을 JSON 배열로 반환 (예: [{"size": "S", "stock": 3}, {"size": "M", "stock": 0}])
    """
    color = request.args.get("color", "").strip()
    if not color:
        return jsonify([])

    result = []
    try:
        supabase = get_supabase_client()
        if supabase:
            # product_options에서 product_id + color로 필터링
            resp = supabase.table("product_options")\
                .select("size, stock")\
                .eq("product_id", product_id)\
                .eq("color", color)\
                .not_.is_("size", "null")\
                .execute()

            raw_list = resp.data or []
            # 사이즈 순서 정렬 (XS -> S -> M -> L -> XL -> XXL -> FREE)
            size_order = {"XS": 1, "S": 2, "M": 3, "L": 4, "XL": 5, "XXL": 6, "FREE": 7}
            raw_list.sort(key=lambda x: size_order.get((x.get("size") or "").upper(), 99))

            # size, stock 형태의 깔끔한 딕셔너리 리스트로 정제
            result = [
                {
                    "size": item.get("size"),
                    "stock": int(item.get("stock") or 0)
                }
                for item in raw_list
            ]
    except Exception as e:
        print(f"[사이즈 목록 API 조회 오류]: {e}", file=sys.stderr)
        return jsonify([]), 500

    return jsonify(result)
