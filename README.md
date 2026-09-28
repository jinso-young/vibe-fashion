# 🛍️ VIBE-FASHION (바이브 패션) 온라인 쇼핑몰

Flask 기반의 트렌디한 패션 이커머스 웹 애플리케이션입니다.

---

## 📌 주요 특징 및 기술 스택

1. **Python 3.13 & Flask 3.x**: 최신 파이썬 환경과 경량 웹 프레임워크
2. **앱 팩토리 패턴 (Application Factory Pattern)**:
   - `app.py`의 `create_app()` 함수를 통한 깔끔한 모듈 분리
   - `routes/`, `templates/`, `static/` 독립적인 폴더 구조
3. **Bootstrap 5.3 CDN**:
   - 반응형 레이아웃 및 모던한 다크 앤 라이트 테마 조화
   - 히어로 섹션, 혜택 바, 4개의 추천 상품 카드, 룩북 및 뉴스레터 섹션
4. **picsum.photos 더미 이미지**: 고품질 패션 더미 이미지 활용
5. **초보자 친화적 한국어 주석**: 모든 파이썬 및 템플릿, 스크립트 코드에 상세한 설명 수록

---

## 📂 프로젝트 폴더 구조

```text
Day0/
├── routes/                 # 라우트(블루프린트) 관리 폴더
│   ├── __init__.py
│   └── main.py            # 메인 홈 및 상품 상세 라우트, 상품 더미 데이터
├── templates/              # HTML 템플릿 (Jinja2)
│   ├── base.html          # 공통 레이아웃 (GNB, 푸터, 모달, 토스트, Bootstrap CDN)
│   ├── index.html         # 메인 페이지 (히어로 섹션, 4개 상품 카드, 룩북)
│   ├── product_detail.html# 상품 상세 페이지
│   └── 404.html           # 404 에러 안내 페이지
├── static/                 # 정적 리소스 파일
│   ├── css/
│   │   └── style.css      # 커스텀 패션 테마 스타일
│   └── js/
│       └── main.js        # 장바구니/찜/검색/필터링 인터랙션
├── app.py                  # Flask 앱 팩토리 함수 (create_app)
├── run.py                  # 애플리케이션 로컬 실행 엔트리포인트
├── requirements.txt        # 의존성 패키지 (flask, python-dotenv, supabase, gunicorn)
├── .env.example            # 환경 변수 설정 템플릿
├── .gitignore              # Git 버전 관리 제외 목록
└── README.md               # 프로젝트 가이드
```

---

## 🚀 실행 방법

### 1. 가상환경 생성 및 활성화
```bash
# 가상환경 생성
python -m venv venv

# 가상환경 활성화 (Windows PowerShell 기준)
.\venv\Scripts\Activate.ps1

# (선택) Mac / Linux의 경우
# source venv/bin/activate
```

### 2. 의존성 패키지 설치
```bash
pip install -r requirements.txt
```

### 3. 환경 변수 파일 생성
```bash
# Windows PowerShell
Copy-Item .env.example .env

# Mac / Linux
# cp .env.example .env
```

### 4. 서버 실행
```bash
python run.py
```

웹 브라우저에서 `http://127.0.0.1:5000` 주소로 접속하면 쇼핑몰 메인 페이지를 확인할 수 있습니다.
