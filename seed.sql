-- ==============================================================================
-- VIBE-FASHION 쇼핑몰 초기 데이터(Seed) SQL
-- ==============================================================================

DO $$
DECLARE
  -- 카테고리 ID 변수
  v_cat_top UUID;
  v_cat_bottom UUID;
  v_cat_outer UUID;
  v_cat_dress UUID;
  v_cat_acc UUID;
  v_cat_bag UUID;
  v_cat_shoes UUID;

  -- 상품 ID 변수
  v_prod_1 UUID;
  v_prod_2 UUID;
  v_prod_3 UUID;
  v_prod_4 UUID;
  v_prod_5 UUID;
  v_prod_6 UUID;
  v_prod_7 UUID;
  v_prod_8 UUID;
BEGIN

  -- ----------------------------------------------------------------------------
  -- 1. 카테고리 7개 등록 (기존 slug 충돌 시 재사용)
  -- ----------------------------------------------------------------------------
  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('상의', 'top', '티셔츠, 셔츠, 맨투맨, 니트 등', 1, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_top;

  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('하의', 'bottom', '데님, 슬랙스, 스커트, 팬츠 등', 2, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_bottom;

  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('아우터', 'outer', '자켓, 코트, 패딩, 가디건 등', 3, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_outer;

  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('원피스/세트', 'dress', '미니/미디/롱 원피스, 투피스 셋업', 4, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_dress;

  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('액세서리', 'acc', '모자, 주얼리, 머플러, 벨트 등', 5, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_acc;

  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('가방', 'bag', '숄더백, 토트백, 백팩, 에코백 등', 6, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_bag;

  INSERT INTO public.categories (name, slug, description, display_order, is_active)
  VALUES ('신발', 'shoes', '스니커즈, 로퍼, 부츠, 샌들 등', 7, TRUE)
  ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
  RETURNING id INTO v_cat_shoes;

  -- ----------------------------------------------------------------------------
  -- 2. 샘플 상품 4개 등록
  -- ※ 참고: 일반적인 쇼핑몰 기준 정상가(29,900원) -> 할인가(19,900원) 적용
  -- ----------------------------------------------------------------------------
  -- 상품 1: 베이직 크롭 티셔츠 (상의)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_top,
    '베이직 크롭 티셔츠',
    'basic-crop-tshirt',
    '데일리하게 착용하기 좋은 코튼 100% 베이직 슬림 크롭 티셔츠입니다.',
    29900,
    19900,
    150,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_1;

  -- 상품 2: 와이드 데님 팬츠 (하의)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_bottom,
    '와이드 데님 팬츠',
    'wide-denim-pants',
    '자연스러운 워싱과 트렌디한 와이드 실루엣으로 편안한 착용감을 선사하는 데님 팬츠입니다.',
    39900,
    NULL,
    80,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_2;

  -- 상품 3: 오버핏 코튼 자켓 (아우터)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_outer,
    '오버핏 코튼 자켓',
    'overfit-cotton-jacket',
    '간절기 시즌 가볍게 걸치기 좋은 탄탄한 코튼 소재의 미니멀 오버핏 자켓입니다.',
    59900,
    NULL,
    50,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_3;

  -- 상품 4: 플로럴 미디 원피스 (원피스/세트)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_dress,
    '플로럴 미디 원피스',
    'floral-midi-dress',
    '로맨틱한 플라워 패턴과 허리 스트링 디테일로 페미닌한 무드를 연출해주는 미디 원피스입니다.',
    45900,
    NULL,
    60,
    'active',
    FALSE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_4;

  -- 상품 5: 미니멀 레더 코트 스니커즈 (신발 - 크롭 티셔츠, 와이드 데님, 코튼 자켓과 어울리는 슈즈)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_shoes,
    '미니멀 레더 코트 스니커즈',
    'minimal-leather-sneakers',
    '크롭 티셔츠, 와이드 데님 팬츠, 오버핏 코튼 자켓 등 캐주얼과 미니멀 룩 어디에나 완벽하게 매치되는 천연 소가죽 클래식 스니커즈입니다.',
    69000,
    49000,
    70,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_5;

  -- 상품 6: 모던 데일리 생활한복 원피스 셋업 (신상품 / 원피스)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_dress,
    '모던 데일리 생활한복 원피스 셋업',
    'modern-daily-hanbok',
    '한국 전통의 우아한 선과 현대적인 모던 감성을 결합한 감각적인 데일리 생활한복입니다. 가벼운 코튼 린넨 블렌드로 일상 속에서 편안하고 특별하게 착용할 수 있습니다.',
    89000,
    69000,
    40,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_6;

  -- 상품 7: 캔버스 스트랩 버킷백 (가방/기타)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_bag,
    '캔버스 스트랩 버킷백',
    'canvas-strap-bucket-bag',
    '탄탄한 코튼 캔버스 원단과 고급스러운 블랙 레더 스트랩 배색이 돋보이는 모던 캐주얼 버킷백입니다. 넉넉한 수납공간과 가벼운 무게감으로 일상 데일리백으로 제격입니다.',
    58000,
    39000,
    50,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_7;

  -- 상품 8: 클래식 스트라이프 셔츠 (상의)
  INSERT INTO public.products (category_id, name, slug, description, price, sale_price, stock, status, is_featured)
  VALUES (
    v_cat_top,
    '클래식 스트라이프 셔츠',
    'classic-stripe-shirt',
    '감각적인 핀스트라이프 패턴과 깔끔한 카라 라인이 돋보이는 모던 와이셔츠입니다. 단독 착용은 물론 슬랙스나 데님 팬츠와 매치하여 포멀하면서도 세련된 데일리룩을 완성합니다.',
    39000,
    NULL,
    80,
    'active',
    TRUE
  )
  ON CONFLICT (slug) DO UPDATE SET
    price = EXCLUDED.price,
    sale_price = EXCLUDED.sale_price,
    stock = EXCLUDED.stock
  RETURNING id INTO v_prod_8;

  -- ----------------------------------------------------------------------------
  -- 3. 첫 번째 상품 옵션 9개 (블랙/화이트/베이지 × S/M/L)
  -- ----------------------------------------------------------------------------
  -- 기존 옵션 초기화 후 재등록 (중복 방지)
  DELETE FROM public.product_options WHERE product_id IN (v_prod_1, v_prod_6, v_prod_7, v_prod_8);

  INSERT INTO public.product_options (product_id, option_name, option_value, additional_price, stock)
  VALUES
    -- 블랙 계열 (S, M, L)
    (v_prod_1, '컬러/사이즈', '블랙 / S', 0, 20),
    (v_prod_1, '컬러/사이즈', '블랙 / M', 0, 25),
    (v_prod_1, '컬러/사이즈', '블랙 / L', 0, 15),
    -- 화이트 계열 (S, M, L)
    (v_prod_1, '컬러/사이즈', '화이트 / S', 0, 20),
    (v_prod_1, '컬러/사이즈', '화이트 / M', 0, 25),
    (v_prod_1, '컬러/사이즈', '화이트 / L', 0, 15),
    -- 베이지 계열 (S, M, L)
    (v_prod_1, '컬러/사이즈', '베이지 / S', 0, 10),
    (v_prod_1, '컬러/사이즈', '베이지 / M', 0, 10),
    (v_prod_1, '컬러/사이즈', '베이지 / L', 0, 10),

    -- 생활한복 옵션
    (v_prod_6, '사이즈', 'S (44~55)', 0, 15),
    (v_prod_6, '사이즈', 'M (55~66)', 0, 20),
    (v_prod_6, '사이즈', 'L (66~77)', 0, 5),

    -- 가방 옵션
    (v_prod_7, '색상', '아이보리/블랙', 0, 50),

    -- 와이셔츠 옵션 (프리사이즈, 하늘색 / 흰색)
    (v_prod_8, '색상/사이즈', '하늘색 / FREE', 0, 40),
    (v_prod_8, '색상/사이즈', '흰색 / FREE', 0, 40);

  -- ----------------------------------------------------------------------------
  -- 4. 상품 썸네일 및 추가 이미지 등록
  -- ----------------------------------------------------------------------------
  -- 기존 이미지 초기화 후 재등록
  DELETE FROM public.product_images WHERE product_id IN (v_prod_1, v_prod_2, v_prod_3, v_prod_4, v_prod_5, v_prod_6, v_prod_7, v_prod_8);

  INSERT INTO public.product_images (product_id, image_url, alt_text, display_order, is_thumbnail)
  VALUES
    -- 1번 상품 이미지 (베이직 크롭 티셔츠)
    (v_prod_1, '/static/images/products/basic-crop-tshirt.png', '베이직 크롭 티셔츠 메인 썸네일', 0, TRUE),

    -- 2번 상품 이미지 (와이드 데님 팬츠)
    (v_prod_2, '/static/images/products/wide-denim-pants.png', '와이드 데님 팬츠 메인 썸네일', 0, TRUE),

    -- 3번 상품 이미지 (오버핏 코튼 자켓)
    (v_prod_3, 'https://picsum.photos/id/1059/600/800', '오버핏 코튼 자켓 메인 썸네일', 0, TRUE),
    (v_prod_3, 'https://picsum.photos/id/1060/600/800', '오버핏 코튼 자켓 디테일 컷', 1, FALSE),

    -- 4번 상품 이미지 (플로럴 미디 원피스)
    (v_prod_4, 'https://picsum.photos/id/1012/600/800', '플로럴 미디 원피스 메인 썸네일', 0, TRUE),
    (v_prod_4, 'https://picsum.photos/id/1027/600/800', '플로럴 미디 원피스 디테일 컷', 1, FALSE),

    -- 5번 상품 이미지 (미니멀 레더 코트 스니커즈)
    (v_prod_5, 'https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=600&q=80', '미니멀 레더 코트 스니커즈 메인 썸네일', 0, TRUE),
    (v_prod_5, 'https://images.unsplash.com/photo-1560769629-975ec94e6a86?auto=format&fit=crop&w=600&q=80', '미니멀 레더 코트 스니커즈 디테일 컷', 1, FALSE),

    -- 6번 상품 이미지 (모던 데일리 생활한복)
    (v_prod_6, '/static/images/products/modern-hanbok.png', '모던 데일리 생활한복 메인 썸네일', 0, TRUE),

    -- 7번 상품 이미지 (캔버스 스트랩 버킷백)
    (v_prod_7, '/static/images/products/canvas-bucket-bag.png', '캔버스 스트랩 버킷백 메인 썸네일', 0, TRUE),

    -- 8번 상품 이미지 (클래식 스트라이프 셔츠)
    (v_prod_8, '/static/images/products/stripe-shirt.png', '클래식 스트라이프 셔츠 메인 썸네일', 0, TRUE);

  -- ----------------------------------------------------------------------------
  -- 5. 관리자 계정 초기 데이터 (비밀번호: admin1234!)
  -- ----------------------------------------------------------------------------
  -- pbkdf2:sha256 해시: scrypt:32768:8:1$... 또는 werkzeug pbkdf2:sha256
  INSERT INTO public.admin_users (username, name, email, password_hash, role, status)
  VALUES
    ('superadmin', '최고 관리자', 'superadmin@vibe.com', 'scrypt:32768:8:1$u7xV9a4T7273FGBj$87293fe2bc3dbdbebaea88126b864a7c8137397bdf7592cf99aebca59ceaafe152fe150f16fbc8235a8bc3bdf906e5da2d3d3ef423db359fe2d48074d2275e53', 'SUPER_ADMIN', 'active'),
    ('admin', '운영 관리자', 'admin@vibe.com', 'scrypt:32768:8:1$u7xV9a4T7273FGBj$87293fe2bc3dbdbebaea88126b864a7c8137397bdf7592cf99aebca59ceaafe152fe150f16fbc8235a8bc3bdf906e5da2d3d3ef423db359fe2d48074d2275e53', 'ADMIN', 'active'),
    ('staff', '상품/주문 담당자', 'staff@vibe.com', 'scrypt:32768:8:1$u7xV9a4T7273FGBj$87293fe2bc3dbdbebaea88126b864a7c8137397bdf7592cf99aebca59ceaafe152fe150f16fbc8235a8bc3bdf906e5da2d3d3ef423db359fe2d48074d2275e53', 'STAFF', 'active')
  ON CONFLICT (username) DO NOTHING;

END $$;
