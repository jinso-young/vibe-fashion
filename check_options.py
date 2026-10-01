from app import create_app
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_ANON_KEY')
supabase = create_client(supabase_url, supabase_key)

opts = supabase.table('product_options').select('*').limit(3).execute()
if opts.data:
    for opt in opts.data:
        print(f'ID: {opt.get("id")}')
        print(f'  product_id: {opt.get("product_id")}')
        print(f'  option_name: {opt.get("option_name")}')
        print(f'  option_value: {opt.get("option_value")}')
        print(f'  stock: {opt.get("stock")}')
        print()
