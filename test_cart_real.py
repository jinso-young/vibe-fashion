from app import create_app
from supabase import create_client
import os
from dotenv import load_dotenv
import uuid

load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(supabase_url, supabase_key)

# 테스트용 UUID 생성 (실제 profiles에 등록되지 않아도 cartstate까지 진행)
test_user_id = str(uuid.uuid4())
app = create_app()

print("=== Cart Add API Test ===\n")

# Test 1: 미로그인 상태
print("Test 1: 미로그인 상태 - /auth/login으로 리다이렉트 예상")
with app.test_client() as c:
    r = c.post('/cart/add', 
        json={'product_option_id': 'test-id', 'quantity': 1},
        follow_redirects=False)
    print(f"Status: {r.status_code}")
    if r.status_code == 302:
        print(f"✓ Redirect location: {r.location}")
    print()

# Test 2: 유효한 UUID로 로그인 상태 시뮬레이션
print("Test 2: 유효한 product_option_id로 첫 요청")
option_id = 'be82c131-0ef9-47a9-90fb-673c2e93a91a'  # Beige/S

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = test_user_id
    
    r = c.post('/cart/add',
        json={'product_option_id': option_id, 'quantity': 2})
    data = r.get_json()
    print(f"Status: {r.status_code}")
    print(f"Response: {data}")
    print()

# Test 3: 같은 option으로 재요청 (수량 누적 테스트)
print("Test 3: 같은 option으로 재요청 - 수량 누적")
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = test_user_id
    
    r = c.post('/cart/add',
        json={'product_option_id': option_id, 'quantity': 3})
    data = r.get_json()
    print(f"Status: {r.status_code}")
    print(f"Response: {data}")
    
    # DB에서 실제로 쌓여있는지 확인
    cart_result = supabase.table('carts').select('quantity').eq('user_id', test_user_id).eq('option_id', option_id).execute()
    if cart_result.data:
        print(f"Cart qty in DB: {cart_result.data[0]['quantity']} (예상: 5 = 2+3)")
    print()

# Test 4: 재고 초과 테스트
print("Test 4: 재고 초과 요청")
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = str(uuid.uuid4())  # 다른 사용자로
    
    r = c.post('/cart/add',
        json={'product_option_id': option_id, 'quantity': 15})  # stock은 10
    data = r.get_json()
    print(f"Status: {r.status_code}")
    print(f"Response: {data}")
    print()

print("=== Test Complete ===")
