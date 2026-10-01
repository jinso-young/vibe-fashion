from app import create_app
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_ANON_KEY")
supabase = create_client(supabase_url, supabase_key)

# 전체 carts 데이터 조회
try:
    result = supabase.table('carts').select('*').limit(10).execute()
    print("Carts in DB:")
    if result.data:
        for cart in result.data:
            print(f"  user_id: {cart.get('user_id')}")
            print(f"  product_id: {cart.get('product_id')}")
            print(f"  option_id: {cart.get('option_id')}")
            print(f"  quantity: {cart.get('quantity')}")
            print()
    else:
        print("  (empty - no carts)")
except Exception as e:
    print(f"Error: {e}")
