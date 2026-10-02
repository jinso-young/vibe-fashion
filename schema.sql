-- ==============================================================================
-- VIBE-FASHION 쇼핑몰 데이터베이스 스키마 (Supabase PostgreSQL)
-- ==============================================================================

-- 0. 기존 테이블/함수 초기화가 필요한 경우를 대비한 구문 (선택적)
-- DROP SCHEMA public CASCADE; CREATE SCHEMA public;

-- 1. 확장 기능 활성화
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 2. 공통 함수: updated_at 자동 갱신 트리거 함수
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = timezone('utc'::text, now());
  RETURN NEW;
END;
$$;

-- ==============================================================================
-- 3. 테이블 정의
-- ==============================================================================

-- 3-1. 회원 프로필 테이블 (auth.users 연동)
CREATE TABLE IF NOT EXISTS public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email TEXT NOT NULL,
  full_name TEXT,
  avatar_url TEXT,
  phone TEXT,
  role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'admin')),
  grade TEXT NOT NULL DEFAULT 'BRONZE' CHECK (grade IN ('BRONZE', 'SILVER', 'GOLD', 'VIP')),
  total_spent NUMERIC(12, 0) NOT NULL DEFAULT 0 CHECK (total_spent >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-2. 상품 카테고리 테이블
CREATE TABLE IF NOT EXISTS public.categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  description TEXT,
  parent_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
  display_order INT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-3. 상품 테이블
CREATE TABLE IF NOT EXISTS public.products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID REFERENCES public.categories(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  slug TEXT UNIQUE,
  description TEXT,
  price NUMERIC(12, 0) NOT NULL CHECK (price >= 0),
  sale_price NUMERIC(12, 0) CHECK (sale_price >= 0),
  stock INT NOT NULL DEFAULT 0 CHECK (stock >= 0),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'sold_out', 'hidden')),
  is_featured BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-4. 상품 옵션 테이블 (사이즈, 색상 등)
CREATE TABLE IF NOT EXISTS public.product_options (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
  option_name TEXT NOT NULL,       -- 예: '사이즈', '컬러'
  option_value TEXT NOT NULL,      -- 예: 'FREE', '블랙'
  additional_price NUMERIC(12, 0) NOT NULL DEFAULT 0,
  stock INT NOT NULL DEFAULT 0 CHECK (stock >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-5. 상품 이미지 테이블
CREATE TABLE IF NOT EXISTS public.product_images (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
  image_url TEXT NOT NULL,
  alt_text TEXT,
  display_order INT NOT NULL DEFAULT 0,
  is_thumbnail BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-6. 장바구니 테이블
CREATE TABLE IF NOT EXISTS public.carts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
  option_id UUID REFERENCES public.product_options(id) ON DELETE SET NULL,
  quantity INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  CONSTRAINT unique_user_product_option UNIQUE NULLS NOT DISTINCT (user_id, product_id, option_id)
);

-- 3-7. 주문 테이블
CREATE TABLE IF NOT EXISTS public.orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_number TEXT NOT NULL UNIQUE,
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  total_amount NUMERIC(12, 0) NOT NULL CHECK (total_amount >= 0),
  discount_amount NUMERIC(12, 0) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
  shipping_fee NUMERIC(12, 0) NOT NULL DEFAULT 0 CHECK (shipping_fee >= 0),
  final_amount NUMERIC(12, 0) NOT NULL CHECK (final_amount >= 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'shipping', 'delivered', 'completed', 'cancelled')),
  recipient_name TEXT NOT NULL,
  recipient_phone TEXT NOT NULL,
  shipping_address TEXT NOT NULL,
  shipping_address_detail TEXT,
  postal_code TEXT,
  delivery_memo TEXT,
  payment_method TEXT,
  payment_key TEXT,
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-8. 주문 상세 항목 테이블
CREATE TABLE IF NOT EXISTS public.order_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
  product_id UUID REFERENCES public.products(id) ON DELETE SET NULL,
  option_id UUID REFERENCES public.product_options(id) ON DELETE SET NULL,
  product_name TEXT NOT NULL,
  option_name TEXT,
  unit_price NUMERIC(12, 0) NOT NULL CHECK (unit_price >= 0),
  quantity INT NOT NULL CHECK (quantity > 0),
  total_price NUMERIC(12, 0) NOT NULL CHECK (total_price >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-9. 환불/반품 테이블
CREATE TABLE IF NOT EXISTS public.refunds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
  order_item_id UUID REFERENCES public.order_items(id) ON DELETE SET NULL,
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  refund_amount NUMERIC(12, 0) NOT NULL CHECK (refund_amount >= 0),
  status TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'approved', 'rejected', 'completed')),
  rejection_reason TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  processed_at TIMESTAMPTZ
);

-- 3-10. 알림 테이블
CREATE TABLE IF NOT EXISTS public.notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'notice' CHECK (type IN ('order', 'delivery', 'refund', 'notice', 'event')),
  link_url TEXT,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 3-11. 리뷰 테이블
CREATE TABLE IF NOT EXISTS public.reviews (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES public.products(id) ON DELETE CASCADE,
  order_item_id UUID REFERENCES public.order_items(id) ON DELETE SET NULL,
  rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
  content TEXT NOT NULL,
  image_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- ==============================================================================
-- 4. 인덱스 생성 (성능 최적화)
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_products_category_id ON public.products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_status ON public.products(status);
CREATE INDEX IF NOT EXISTS idx_product_options_product_id ON public.product_options(product_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product_id ON public.product_images(product_id);
CREATE INDEX IF NOT EXISTS idx_carts_user_id ON public.carts(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON public.orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON public.orders(status);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON public.order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON public.refunds(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_user_id ON public.refunds(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON public.notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON public.notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_reviews_product_id ON public.reviews(product_id);
CREATE INDEX IF NOT EXISTS idx_reviews_user_id ON public.reviews(user_id);

-- ==============================================================================
-- 5. 트리거 설정 (updated_at 자동 갱신)
-- ==============================================================================
DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_products_updated_at ON public.products;
CREATE TRIGGER trg_products_updated_at
  BEFORE UPDATE ON public.products
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_carts_updated_at ON public.carts;
CREATE TRIGGER trg_carts_updated_at
  BEFORE UPDATE ON public.carts
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_orders_updated_at ON public.orders;
CREATE TRIGGER trg_orders_updated_at
  BEFORE UPDATE ON public.orders
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

DROP TRIGGER IF EXISTS trg_reviews_updated_at ON public.reviews;
CREATE TRIGGER trg_reviews_updated_at
  BEFORE UPDATE ON public.reviews
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- ==============================================================================
-- 6. 소셜 로그인 및 일반 가입 시 프로필 자동 생성 트리거 (handle_new_user)
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_full_name TEXT;
  v_avatar_url TEXT;
  v_phone TEXT;
BEGIN
  -- 소셜 로그인(Google, Kakao 등) 및 일반 이메일 가입 메타데이터 파싱
  v_full_name := COALESCE(
    NEW.raw_user_meta_data ->> 'full_name',
    NEW.raw_user_meta_data ->> 'name',
    NEW.raw_user_meta_data ->> 'user_name',
    NEW.raw_user_meta_data ->> 'preferred_username',
    split_part(NEW.email, '@', 1)
  );

  v_avatar_url := COALESCE(
    NEW.raw_user_meta_data ->> 'avatar_url',
    NEW.raw_user_meta_data ->> 'picture',
    NEW.raw_user_meta_data ->> 'profile_image',
    NULL
  );

  v_phone := COALESCE(
    NEW.raw_user_meta_data ->> 'phone',
    NEW.raw_user_meta_data ->> 'phone_number',
    NEW.phone,
    NULL
  );

  INSERT INTO public.profiles (
    id,
    email,
    full_name,
    avatar_url,
    phone,
    role,
    grade,
    total_spent
  )
  VALUES (
    NEW.id,
    COALESCE(NEW.email, ''),
    v_full_name,
    v_avatar_url,
    v_phone,
    'customer',
    'BRONZE',
    0
  )
  ON CONFLICT (id) DO UPDATE
  SET
    email = EXCLUDED.email,
    full_name = COALESCE(public.profiles.full_name, EXCLUDED.full_name),
    avatar_url = COALESCE(public.profiles.avatar_url, EXCLUDED.avatar_url),
    phone = COALESCE(public.profiles.phone, EXCLUDED.phone),
    updated_at = timezone('utc'::text, now());

  RETURN NEW;
END;
$$;

-- auth.users 테이블에 가입 트리거 연결
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ==============================================================================
-- 7. 고객 등급 자동 업데이트 함수 (update_customer_grade)
--    - 결제 완료 / 배송 / 구매 확정된 총 누적 결제금액(final_amount - refund_amount) 산정
--    - 등급 기준:
--      * BRONZE : 20만 원 미만
--      * SILVER : 20만 원 이상 ~ 50만 원 미만
--      * GOLD   : 50만 원 이상 ~ 100만 원 미만
--      * VIP    : 100만 원 이상
-- ==============================================================================
CREATE OR REPLACE FUNCTION public.update_customer_grade(p_user_id UUID)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_total_spent NUMERIC(12, 0) := 0;
  v_new_grade TEXT := 'BRONZE';
BEGIN
  -- 결제 완료(paid), 배송중(shipping), 배송완료(delivered), 구매확정(completed) 주문의 결제금액 합산
  SELECT COALESCE(SUM(final_amount), 0)
  INTO v_total_spent
  FROM public.orders
  WHERE user_id = p_user_id
    AND status IN ('paid', 'shipping', 'delivered', 'completed');

  -- 완료된 환불 금액이 있다면 차감
  v_total_spent := v_total_spent - COALESCE((
    SELECT SUM(r.refund_amount)
    FROM public.refunds r
    JOIN public.orders o ON r.order_id = o.id
    WHERE o.user_id = p_user_id
      AND r.status = 'completed'
  ), 0);

  -- 음수 방지
  IF v_total_spent < 0 THEN
    v_total_spent := 0;
  END IF;

  -- 등급 산정
  IF v_total_spent >= 1000000 THEN
    v_new_grade := 'VIP';
  ELSIF v_total_spent >= 500000 THEN
    v_new_grade := 'GOLD';
  ELSIF v_total_spent >= 200000 THEN
    v_new_grade := 'SILVER';
  ELSE
    v_new_grade := 'BRONZE';
  END IF;

  -- 프로필에 총 구매액 및 등급 반영
  UPDATE public.profiles
  SET
    total_spent = v_total_spent,
    grade = v_new_grade,
    updated_at = timezone('utc'::text, now())
  WHERE id = p_user_id;
END;
$$;

-- 주문 변경 시 고객 등급 자동 갱신 트리거 함수
CREATE OR REPLACE FUNCTION public.trigger_order_customer_grade_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    PERFORM public.update_customer_grade(OLD.user_id);
    RETURN OLD;
  ELSE
    PERFORM public.update_customer_grade(NEW.user_id);
    RETURN NEW;
  END IF;
END;
$$;

-- 주문 상태 변경/추가 시 고객 등급 자동 반영 트리거 연결
DROP TRIGGER IF EXISTS trg_order_update_customer_grade ON public.orders;
CREATE TRIGGER trg_order_update_customer_grade
  AFTER INSERT OR UPDATE OF status, final_amount OR DELETE ON public.orders
  FOR EACH ROW EXECUTE FUNCTION public.trigger_order_customer_grade_update();

-- 환불 완료 처리 시 고객 등급 자동 재산정 트리거 연결
DROP TRIGGER IF EXISTS trg_refund_update_customer_grade ON public.refunds;
CREATE TRIGGER trg_refund_update_customer_grade
  AFTER INSERT OR UPDATE OF status, refund_amount OR DELETE ON public.refunds
  FOR EACH ROW EXECUTE FUNCTION public.trigger_order_customer_grade_update();

-- ==============================================================================
-- 8. Row Level Security (RLS) 활성화 및 기본 정책
-- ==============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_options ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.carts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.refunds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;

-- 8-1. profiles 정책 (재귀 조회 방지를 위해 auth.uid() 직접 비교)
CREATE POLICY "프로필 조회: 본인 전용"
  ON public.profiles FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "프로필 수정: 본인 전용"
  ON public.profiles FOR UPDATE
  USING (auth.uid() = id);

-- 8-2. categories 정책 (모두 조회 가능)
CREATE POLICY "카테고리 조회: 누구나"
  ON public.categories FOR SELECT
  USING (is_active = TRUE);

-- 8-3. products 정책 (공개 상품 누구나 조회)
CREATE POLICY "상품 조회: 누구나 활성 상품 조회"
  ON public.products FOR SELECT
  USING (status != 'hidden');

-- 8-4. product_options & product_images 정책
CREATE POLICY "상품 옵션 조회: 누구나"
  ON public.product_options FOR SELECT USING (TRUE);

CREATE POLICY "상품 이미지 조회: 누구나"
  ON public.product_images FOR SELECT USING (TRUE);

-- 8-5. carts 정책 (본인 장바구니만 접근)
CREATE POLICY "장바구니 조회/관리: 본인 전용"
  ON public.carts FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- 8-6. orders & order_items 정책
CREATE POLICY "주문 조회: 본인 또는 관리자"
  ON public.orders FOR SELECT
  USING (auth.uid() = user_id OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin');

CREATE POLICY "주문 생성: 본인 전용"
  ON public.orders FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "주문 수정: 관리자 또는 본인(취소 등)"
  ON public.orders FOR UPDATE
  USING (auth.uid() = user_id OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin');

CREATE POLICY "주문 상세 조회: 본인 또는 관리자"
  ON public.order_items FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.orders o
      WHERE o.id = order_items.order_id
        AND (o.user_id = auth.uid() OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin')
    )
  );

CREATE POLICY "주문 상세 생성: 주문 소유자"
  ON public.order_items FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.orders o
      WHERE o.id = order_items.order_id AND o.user_id = auth.uid()
    )
  );

-- 8-7. refunds 정책
CREATE POLICY "환불 내역 조회: 본인 또는 관리자"
  ON public.refunds FOR SELECT
  USING (auth.uid() = user_id OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin');

CREATE POLICY "환불 신청: 본인 전용"
  ON public.refunds FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "환불 처리: 관리자 전용"
  ON public.refunds FOR UPDATE
  USING ((SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin');

-- 8-8. notifications 정책
CREATE POLICY "알림 조회 및 읽음 처리: 본인 전용"
  ON public.notifications FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

-- 8-9. reviews 정책
CREATE POLICY "리뷰 조회: 누구나"
  ON public.reviews FOR SELECT USING (TRUE);

CREATE POLICY "리뷰 작성: 로그인 사용자"
  ON public.reviews FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "리뷰 수정 및 삭제: 본인 또는 관리자"
  ON public.reviews FOR UPDATE
  USING (auth.uid() = user_id OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin');

CREATE POLICY "리뷰 삭제: 본인 또는 관리자"
  ON public.reviews FOR DELETE
  USING (auth.uid() = user_id OR (SELECT role FROM public.profiles WHERE id = auth.uid()) = 'admin');

-- ==============================================================================
-- 9. 관리자 전용 테이블 및 RBAC 권한 관리
-- ==============================================================================

-- 9-1. 관리자 계정 테이블
CREATE TABLE IF NOT EXISTS public.admin_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('SUPER_ADMIN', 'ADMIN', 'STAFF')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'locked')),
  must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 9-2. 관리자 활동 로그 테이블
CREATE TABLE IF NOT EXISTS public.admin_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id UUID,
  admin_username TEXT NOT NULL,
  admin_name TEXT NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  details TEXT,
  result TEXT NOT NULL DEFAULT '성공',
  ip_address TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- 9-3. 관리자 시스템 설정 테이블
CREATE TABLE IF NOT EXISTS public.admin_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  description TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_admin_users_role ON public.admin_users(role);
CREATE INDEX IF NOT EXISTS idx_admin_users_status ON public.admin_users(status);
CREATE INDEX IF NOT EXISTS idx_admin_logs_admin_id ON public.admin_logs(admin_id);
CREATE INDEX IF NOT EXISTS idx_admin_logs_created_at ON public.admin_logs(created_at DESC);

