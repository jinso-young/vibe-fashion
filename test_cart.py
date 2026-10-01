from app import create_app
import json

app = create_app()

# Test 1: 미로그인 상태에서 요청
with app.test_client() as c:
    print('✓ Test 1: 미로그인 상태')
    r = c.post('/cart/add', 
        json={'product_option_id': 'test-id', 'quantity': 1},
        follow_redirects=False)
    print(f'  Status: {r.status_code}')
    if r.status_code in [301, 302, 303, 307]:
        print(f'  Location: {r.location}')
    print()

# Test 2: 로그인 상태에서 유효하지 않은 option_id
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 'test-user-id-12345'
    
    print('✓ Test 2: 존재하지 않는 product_option_id')
    r = c.post('/cart/add', 
        json={'product_option_id': 'invalid-id', 'quantity': 1})
    data = r.get_json()
    print(f'  Status: {r.status_code}')
    print(f'  Response: {data.get("message", "")}')
    print()

# Test 3: 올바른 product_option_id로 요청 (처음 요청)
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 'test-user-id-12345'
    
    # Beige/S 옵션의 ID
    option_id = 'be82c131-0ef9-47a9-90fb-673c2e93a91a'
    
    print('✓ Test 3: 올바른 product_option_id로 첫 요청')
    r = c.post('/cart/add',
        json={'product_option_id': option_id, 'quantity': 2})
    data = r.get_json()
    print(f'  Status: {r.status_code}')
    print(f'  Success: {data.get("success", False)}')
    print(f'  Message: {data.get("message", "")}')
    print()

# Test 4: 같은 option 다시 요청 (수량 누적)
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 'test-user-id-12345'
    
    option_id = 'be82c131-0ef9-47a9-90fb-673c2e93a91a'
    
    print('✓ Test 4: 같은 option으로 재요청 (수량 누적)')
    r = c.post('/cart/add',
        json={'product_option_id': option_id, 'quantity': 3})
    data = r.get_json()
    print(f'  Status: {r.status_code}')
    print(f'  Success: {data.get("success", False)}')
    print(f'  Message: {data.get("message", "")}')
    print()

# Test 5: 재고 초과 요청
with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 'test-user-id-99999'
    
    option_id = 'be82c131-0ef9-47a9-90fb-673c2e93a91a'
    
    print('✓ Test 5: 재고(10개) 초과 요청')
    r = c.post('/cart/add',
        json={'product_option_id': option_id, 'quantity': 20})
    data = r.get_json()
    print(f'  Status: {r.status_code}')
    print(f'  Success: {data.get("success", False)}')
    print(f'  Message: {data.get("message", "")}')
