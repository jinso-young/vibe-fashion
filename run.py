"""
=====================================================
VIBE-FASHION 애플리케이션 실행 엔트리포인트 (run.py)
=====================================================
개발 환경에서 애플리케이션을 구동할 때 이 스크립트를 직접 실행합니다.
명령어: python run.py
"""

import os
from app import create_app

# 앱 팩토리 함수를 호출하여 Flask 앱 객체를 생성합니다.
app = create_app()

if __name__ == "__main__":
    # 환경 변수에서 포트와 디버그 모드 설정을 가져옵니다 (기본값: 포트 5000, 디버그 활성화)
    port = int(os.getenv("PORT", 5000))
    debug_mode = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1", "t")

    print("=" * 55)
    print(" [VIBE-FASHION] 패션 쇼핑몰 서버가 시작되었습니다!")
    print(f" 접속 주소: http://127.0.0.1:{port}")
    print(f" 디버그 모드: {'활성화 (코드 변경 시 자동 재시작)' if debug_mode else '비활성화'}")
    print("=" * 55)

    # 로컬 개발용 서버 실행
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
