/**
 * ==========================================================================
 * VIBE-FASHION 프론트엔드 인터랙션 스크립트 (static/js/main.js)
 * ==========================================================================
 * 쇼핑몰의 장바구니, 위시리스트, 카테고리 필터링, 검색 기능을 담당합니다.
 */

// 1. 장바구니 및 위시리스트 상태 관리 (인메모리 배열)
const cartState = [];
const wishlistState = [];
let wishlistCount = 0;

/**
 * 가격 문자열 또는 숫자를 안전하게 정수형 숫자로 변환하는 헬퍼 함수
 * @param {string|number} val
 * @returns {number}
 */
function parsePrice(val) {
    if (typeof val === 'number') {
        return isNaN(val) ? 0 : Math.round(val);
    }
    if (!val) return 0;
    // 쉼표, '원', 공백 등을 모두 제거하고 숫자만 추출
    const cleaned = String(val).replace(/[^0-9.-]/g, '');
    const num = parseFloat(cleaned);
    return isNaN(num) ? 0 : Math.round(num);
}

/**
 * 장바구니에 상품을 추가하는 함수
 * @param {string} name 상품명
 * @param {number|string} price 가격 (숫자 또는 문자열)
 * @param {string} imageUrl 상품 이미지 URL
 */
function addToCart(name, price, imageUrl) {
    const numericPrice = parsePrice(price);

    // 상품 객체 추가 (숫자형 가격으로 저장)
    cartState.push({
        id: Date.now() + Math.random(),
        name: name,
        price: numericPrice,
        imageUrl: imageUrl
    });

    // 장바구니 뱃지 숫자 갱신
    updateCartUI();

    // 토스트 팝업 알림 표시
    showToast(`"${name}" 상품이 장바구니에 담겼습니다!`);
}

/**
 * 장바구니에서 특정 아이템을 제거하는 함수
 * @param {number} index 제거할 아이템의 배열 인덱스
 */
function removeFromCart(index) {
    if (index >= 0 && index < cartState.length) {
        cartState.splice(index, 1);
        updateCartUI();
    }
}

/**
 * 장바구니 UI(오프캔버스 내용 및 뱃지 숫자)를 갱신하는 함수
 */
function updateCartUI() {
    const badge = document.getElementById('cart-badge');
    const emptyMsg = document.getElementById('cart-empty-msg');
    const list = document.getElementById('cart-list');
    const totalPriceEl = document.getElementById('cart-total-price');

    // 뱃지 숫자 업데이트
    if (badge) {
        badge.textContent = cartState.length;
    }

    // 장바구니 오프캔버스 목록 업데이트
    if (!list || !emptyMsg || !totalPriceEl) return;

    if (cartState.length === 0) {
        emptyMsg.style.display = 'block';
        list.innerHTML = '';
        totalPriceEl.textContent = '0원';
        return;
    }

    emptyMsg.style.display = 'none';
    let total = 0;
    let html = '';

    cartState.forEach((item, idx) => {
        const itemPrice = parsePrice(item.price);
        total += itemPrice;
        html += `
            <li class="list-group-item d-flex align-items-center justify-content-between px-0 py-3">
                <div class="d-flex align-items-center gap-3">
                    <img src="${item.imageUrl}" alt="${item.name}" class="rounded" style="width: 50px; height: 50px; object-fit: cover;">
                    <div>
                        <div class="fw-bold small text-truncate" style="max-width: 170px;">${item.name}</div>
                        <div class="text-muted small">${itemPrice.toLocaleString()}원</div>
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger border-0" onclick="removeFromCart(${idx})" title="삭제">
                    <i class="bi bi-trash"></i>
                </button>
            </li>
        `;
    });

    list.innerHTML = html;
    // 총합친 가격에 '원'을 딱 하나만 붙임
    totalPriceEl.textContent = total.toLocaleString() + '원';
}

/**
 * 토스트 알림을 띄우는 함수
 * @param {string} message 알림 문구
 */
function showToast(message) {
    const toastEl = document.getElementById('cartToast');
    const msgEl = document.getElementById('toast-message');
    if (!toastEl) return;

    if (msgEl) msgEl.textContent = message;
    const toast = new bootstrap.Toast(toastEl, { delay: 2500 });
    toast.show();
}

/**
 * 위시리스트(찜) 토글 함수
 * @param {HTMLElement} btn 버튼 요소
 * @param {string} productName 상품명
 * @param {number|string} price 상품 가격
 * @param {string} imageUrl 상품 이미지 URL
 * @param {string} detailUrl 상세페이지 링크
 */
function toggleWishlist(btn, productName, price, imageUrl, detailUrl) {
    const icon = btn.querySelector('i');
    const existingIndex = wishlistState.findIndex(item => item.name === productName);

    if (existingIndex === -1) {
        // 위시리스트에 추가
        wishlistState.push({
            name: productName,
            price: parsePrice(price),
            imageUrl: imageUrl || '',
            detailUrl: detailUrl || '#'
        });

        if (icon) {
            icon.classList.remove('bi-heart', 'text-secondary');
            icon.classList.add('bi-heart-fill', 'text-danger');
        }
        showToast(`"${productName}" 상품을 위시리스트에 담았습니다 ❤️`);
    } else {
        // 위시리스트에서 제거
        wishlistState.splice(existingIndex, 1);

        if (icon) {
            icon.classList.remove('bi-heart-fill', 'text-danger');
            icon.classList.add('bi-heart', 'text-secondary');
        }
        showToast(`"${productName}" 상품을 위시리스트에서 제외했습니다.`);
    }

    updateWishlistUI();
}

/**
 * 위시리스트에서 특정 아이템을 제거하는 함수
 * @param {number} index
 */
function removeFromWishlist(index) {
    if (index >= 0 && index < wishlistState.length) {
        const removed = wishlistState.splice(index, 1)[0];
        
        // 카드 내의 하트 버튼 아이콘 동기화
        const cards = document.querySelectorAll('.product-card-col');
        cards.forEach(card => {
            const cardName = card.getAttribute('data-name');
            if (cardName === removed.name) {
                const btn = card.querySelector('.btn-wishlist i');
                if (btn) {
                    btn.classList.remove('bi-heart-fill', 'text-danger');
                    btn.classList.add('bi-heart', 'text-secondary');
                }
            }
        });

        updateWishlistUI();
    }
}

/**
 * 위시리스트 UI(오프캔버스 내용 및 뱃지 숫자) 갱신
 */
function updateWishlistUI() {
    const badge = document.getElementById('wishlist-badge');
    const emptyMsg = document.getElementById('wishlist-empty-msg');
    const list = document.getElementById('wishlist-list');

    // 뱃지 숫자 업데이트
    if (badge) {
        badge.textContent = wishlistState.length;
        badge.style.display = wishlistState.length > 0 ? 'inline-block' : 'none';
    }

    if (!list || !emptyMsg) return;

    if (wishlistState.length === 0) {
        emptyMsg.style.display = 'block';
        list.innerHTML = '';
        return;
    }

    emptyMsg.style.display = 'none';
    let html = '';

    wishlistState.forEach((item, idx) => {
        const itemPrice = parsePrice(item.price);
        html += `
            <li class="list-group-item d-flex align-items-center justify-content-between px-0 py-3 border-bottom">
                <div class="d-flex align-items-center gap-3">
                    <img src="${item.imageUrl}" alt="${item.name}" class="rounded" style="width: 50px; height: 50px; object-fit: cover;">
                    <div>
                        <a href="${item.detailUrl}" class="fw-bold small text-dark text-decoration-none text-truncate d-block" style="max-width: 150px;">${item.name}</a>
                        <div class="text-muted small">${itemPrice.toLocaleString()}원</div>
                    </div>
                </div>
                <div class="d-flex align-items-center gap-1">
                    <button type="button" class="btn btn-sm btn-outline-dark" onclick="addToCart('${item.name}', ${itemPrice}, '${item.imageUrl}')" title="장바구니 담기">
                        <i class="bi bi-bag-plus"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-outline-danger border-0" onclick="removeFromWishlist(${idx})" title="삭제">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
            </li>
        `;
    });

    list.innerHTML = html;
}

/**
 * 카테고리별 상품 필터링 함수
 * @param {string} category 필터링할 카테고리 ('all', 'OUTER', 'TOP', etc.)
 * @param {HTMLElement} btnClicked 클릭된 버튼
 */
function filterProducts(category, btnClicked) {
    // 버튼 active 상태 변경
    if (btnClicked) {
        const group = btnClicked.parentElement;
        group.querySelectorAll('.btn').forEach(btn => {
            btn.classList.remove('btn-dark', 'active');
            btn.classList.add('btn-outline-dark');
        });
        btnClicked.classList.remove('btn-outline-dark');
        btnClicked.classList.add('btn-dark', 'active');
    }

    // 카드 표시/숨김 처리
    const cards = document.querySelectorAll('.product-card-col');
    cards.forEach(card => {
        const itemCategory = (card.getAttribute('data-category') || '').toUpperCase();
        let isMatch = false;

        if (category === 'all') {
            isMatch = true;
        } else if (category === 'ETC') {
            // 기타: 신발(SHOES), 가방(BAG), 액세서리(ACC) 등 포함
            isMatch = ['SHOES', 'BAG', 'ACC', 'ETC'].includes(itemCategory);
        } else {
            isMatch = itemCategory === category;
        }

        if (isMatch) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

/**
 * 헤더 검색 모달에서 입력된 키워드로 상품 필터 검색
 */
function performSearch() {
    const input = document.getElementById('searchInput');
    if (!input) return;

    const keyword = input.value.trim().toLowerCase();
    if (!keyword) {
        alert('검색어를 입력해주세요.');
        return;
    }

    // 모달 닫기
    const searchModalEl = document.getElementById('searchModal');
    if (searchModalEl) {
        const modal = bootstrap.Modal.getInstance(searchModalEl);
        if (modal) modal.hide();
    }

    // 상품 필터링
    const cards = document.querySelectorAll('.product-card-col');
    let matchedCount = 0;

    cards.forEach(card => {
        const name = (card.getAttribute('data-name') || '').toLowerCase();
        const category = (card.getAttribute('data-category') || '').toLowerCase();

        if (name.includes(keyword) || category.includes(keyword)) {
            card.style.display = 'block';
            matchedCount++;
        } else {
            card.style.display = 'none';
        }
    });

    // 상품 섹션으로 스크롤 이동
    const section = document.getElementById('products-section');
    if (section) {
        section.scrollIntoView({ behavior: 'smooth' });
    }

    showToast(`"${keyword}" 검색 결과: ${matchedCount}건`);
}

/**
 * 추천 태그 클릭 시 즉시 검색 실행
 * @param {string} tag 태그 단어
 */
function quickSearch(tag) {
    const input = document.getElementById('searchInput');
    if (input) {
        input.value = tag;
        performSearch();
    }
}
