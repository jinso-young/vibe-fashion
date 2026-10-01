/**
 * ==========================================================================
 * VIBE-FASHION 프론트엔드 인터랙션 스크립트 (static/js/main.js)
 * ==========================================================================
 * 쇼핑몰의 장바구니, 위시리스트, 카테고리 필터링, 검색 기능을 담당합니다.
 */

// 1. 장바구니 및 위시리스트 상태 관리 (localStorage와 연동)
const CART_STORAGE_KEY = 'vibe_fashion_cart';
const WISHLIST_STORAGE_KEY = 'vibe_fashion_wishlist';

function loadCartFromStorage() {
    try {
        const stored = localStorage.getItem(CART_STORAGE_KEY);
        return stored ? JSON.parse(stored) : [];
    } catch (e) {
        return [];
    }
}

function saveCartToStorage() {
    try {
        localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cartState));
    } catch (e) {
        console.error('장바구니 저장 실패:', e);
    }
}

function loadWishlistFromStorage() {
    try {
        const stored = localStorage.getItem(WISHLIST_STORAGE_KEY);
        return stored ? JSON.parse(stored) : [];
    } catch (e) {
        return [];
    }
}

function saveWishlistToStorage() {
    try {
        localStorage.setItem(WISHLIST_STORAGE_KEY, JSON.stringify(wishlistState));
    } catch (e) {
        console.error('위시리스트 저장 실패:', e);
    }
}

let cartState = loadCartFromStorage();
const wishlistState = loadWishlistFromStorage();
let wishlistCount = wishlistState.length;

async function loadCartFromServer() {
    if (!window.IS_LOGGED_IN) {
        updateCartUI();
        return;
    }

    try {
        const response = await fetch('/api/cart', { headers: { 'Accept': 'application/json' } });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || '장바구니를 불러오지 못했습니다.');
        }

        cartState = (data.items || []).map(item => ({
            cartId: item.cart_id,
            name: item.name,
            price: Number(item.price) || 0,
            quantity: Number(item.quantity) || 1,
            imageUrl: item.image_url,
            color: item.color,
            size: item.size
        }));
        updateCartUI();
        renderMypageCartSection();
    } catch (error) {
        console.error('서버 장바구니 조회 실패:', error);
        updateCartUI();
    }
}

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
    // 비로그인 상태일 경우 로그인 유도 모달 팝업 표시
    if (typeof window.IS_LOGGED_IN !== 'undefined' && !window.IS_LOGGED_IN) {
        const loginModalEl = document.getElementById('loginRequiredModal');
        if (loginModalEl && typeof bootstrap !== 'undefined') {
            const loginModal = bootstrap.Modal.getOrCreateInstance(loginModalEl);
            loginModal.show();
            return;
        } else if (confirm('로그인이 필요한 서비스입니다. 로그인 페이지로 이동하시겠습니까?')) {
            window.location.href = window.LOGIN_URL || '/auth/login';
            return;
        }
    }

    const numericPrice = parsePrice(price);

    // 상품 객체 추가 (숫자형 가격으로 저장)
    cartState.push({
        id: Date.now() + Math.random(),
        name: name,
        price: numericPrice,
        imageUrl: imageUrl
    });

    saveCartToStorage();

    // 장바구니 뱃지 숫자 갱신
    updateCartUI();

    // 토스트 팝업 알림 표시
    showToast(`"${name}" 상품이 장바구니에 담겼습니다!`);
}

/**
 * 장바구니에서 특정 아이템을 제거하는 함수
 * @param {number} index 제거할 아이템의 배열 인덱스
 */
async function removeFromCart(index) {
    const item = cartState[index];
    if (item && item.cartId) {
        try {
            const response = await fetch(`/cart/${encodeURIComponent(item.cartId)}`, { method: 'DELETE' });
            const data = await response.json();
            if (!response.ok || !data.success) {
                alert(data.message || '장바구니에서 삭제하지 못했습니다.');
                return;
            }
            await loadCartFromServer();
        } catch (error) {
            console.error('장바구니 삭제 실패:', error);
            alert('장바구니에서 삭제하지 못했습니다. 다시 시도해주세요.');
        }
        return;
    }

    if (index >= 0 && index < cartState.length) {
        cartState.splice(index, 1);
        saveCartToStorage();
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
        badge.textContent = cartState.reduce((count, item) => count + (Number(item.quantity) || 1), 0);
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
        const quantity = Number(item.quantity) || 1;
        const itemTotal = itemPrice * quantity;
        total += itemTotal;
        html += `
            <li class="list-group-item d-flex align-items-center justify-content-between px-0 py-3">
                <div class="d-flex align-items-center gap-3">
                    <img src="${item.imageUrl || ''}" alt="${item.name}" class="rounded" style="width: 50px; height: 50px; object-fit: cover;">
                    <div>
                        <div class="fw-bold small text-truncate" style="max-width: 170px;">${item.name}</div>
                        <div class="text-muted small">${item.color || ''}${item.size ? ` / ${item.size}` : ''}${quantity > 1 ? ` · ${quantity}개` : ''}</div>
                        <div class="text-muted small">${itemTotal.toLocaleString()}원</div>
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
 * 바로 구매하기 함수 (단일 상품 즉시 주문서 오픈)
 */
function buyNow(name, price, imageUrl) {
    if (typeof window.IS_LOGGED_IN !== 'undefined' && !window.IS_LOGGED_IN) {
        const loginModalEl = document.getElementById('loginRequiredModal');
        if (loginModalEl && typeof bootstrap !== 'undefined') {
            const loginModal = bootstrap.Modal.getOrCreateInstance(loginModalEl);
            loginModal.show();
            return;
        } else {
            alert('로그인이 필요한 서비스입니다.');
            window.location.href = window.LOGIN_URL || '/auth/login';
            return;
        }
    }

    const numericPrice = parsePrice(price);
    // 단일 상품 구매용 임시 아이템으로 결제창 오픈
    const singleItem = [{
        name: name,
        price: numericPrice,
        imageUrl: imageUrl
    }];
    openCheckoutModalWithItems(singleItem, true);
}

/**
 * 결제 모달(주문서 작성창) 열기 - 장바구니 전체
 */
function openCheckoutModal() {
    // 1. 로그인 여부 확인
    if (typeof window.IS_LOGGED_IN !== 'undefined' && !window.IS_LOGGED_IN) {
        const loginModalEl = document.getElementById('loginRequiredModal');
        if (loginModalEl && typeof bootstrap !== 'undefined') {
            const loginModal = bootstrap.Modal.getOrCreateInstance(loginModalEl);
            loginModal.show();
            return;
        } else {
            alert('로그인이 필요한 서비스입니다.');
            window.location.href = window.LOGIN_URL || '/auth/login';
            return;
        }
    }

    // 2. 장바구니 비어있는지 확인
    if (!cartState || cartState.length === 0) {
        alert('장바구니에 담긴 상품이 없습니다.');
        return;
    }

    openCheckoutModalWithItems(cartState, false);
}

let currentCheckoutItems = [];
let isDirectBuyNow = false;

/**
 * 특정 아이템 목록으로 주문서 모달 오픈
 */
function openCheckoutModalWithItems(items, isSingle) {
    currentCheckoutItems = items;
    isDirectBuyNow = isSingle;

    // 장바구니 오프캔버스 서랍이 열려있다면 닫기
    const offcanvasEl = document.getElementById('cartOffcanvas');
    if (offcanvasEl && typeof bootstrap !== 'undefined') {
        const offcanvas = bootstrap.Offcanvas.getInstance(offcanvasEl);
        if (offcanvas) offcanvas.hide();
    }

    // 모달 내용 렌더링
    const itemsListEl = document.getElementById('checkoutItemsList');
    const subtotalEl = document.getElementById('checkoutSubtotal');
    const totalEl = document.getElementById('checkoutTotal');
    const payBtnText = document.getElementById('checkoutPayBtnText');

    let total = 0;
    let html = '';

    items.forEach(item => {
        const quantity = Number(item.quantity) || 1;
        const p = parsePrice(item.price) * quantity;
        total += p;
        html += `
            <div class="d-flex align-items-center justify-content-between py-2 border-bottom">
                <div class="d-flex align-items-center gap-2">
                    <img src="${item.imageUrl}" alt="${item.name}" class="rounded" style="width: 40px; height: 40px; object-fit: cover;">
                    <span class="small fw-medium text-truncate" style="max-width: 140px;">${item.name}${quantity > 1 ? ` (${quantity}개)` : ''}</span>
                </div>
                <span class="small fw-bold">${p.toLocaleString()}원</span>
            </div>
        `;
    });

    if (itemsListEl) itemsListEl.innerHTML = html;
    if (subtotalEl) subtotalEl.textContent = total.toLocaleString() + '원';
    if (totalEl) totalEl.textContent = total.toLocaleString() + '원';
    if (payBtnText) payBtnText.textContent = `${total.toLocaleString()}원 결제하기`;

    // 모달 표시
    const checkoutModalEl = document.getElementById('checkoutModal');
    if (checkoutModalEl && typeof bootstrap !== 'undefined') {
        const modal = bootstrap.Modal.getOrCreateInstance(checkoutModalEl);
        modal.show();
    }
}

/**
 * 실제 결제 처리 함수 (결제 승인 및 주문 완료 처리)
 */
function processPayment() {
    const recipient = document.getElementById('checkoutRecipient')?.value.trim();
    const phone = document.getElementById('checkoutPhone')?.value.trim();
    const address = document.getElementById('checkoutAddress')?.value.trim();

    if (!recipient || !phone || !address) {
        alert('배송지 정보(수령인, 연락처, 주소)를 모두 입력해주세요.');
        return;
    }

    const selectedPayMethod = document.querySelector('input[name="paymentMethod"]:checked')?.value || 'kakaopay';
    const payNames = {
        'kakaopay': '카카오페이',
        'naverpay': '네이버페이',
        'credit_card': '신용카드'
    };
    const payName = payNames[selectedPayMethod] || '간편결제';

    let total = 0;
    currentCheckoutItems.forEach(item => {
        total += parsePrice(item.price) * (Number(item.quantity) || 1);
    });

    // 주문 번호 생성 (ORD-YYYYMMDD-랜덤)
    const now = new Date();
    const dateStr = now.getFullYear().toString() +
                    String(now.getMonth() + 1).padStart(2, '0') +
                    String(now.getDate()).padStart(2, '0');
    const randomStr = Math.floor(1000 + Math.random() * 9000);
    const orderNumber = `ORD-${dateStr}-${randomStr}`;

    // 주문서 모달 닫기
    const checkoutModalEl = document.getElementById('checkoutModal');
    if (checkoutModalEl && typeof bootstrap !== 'undefined') {
        const modal = bootstrap.Modal.getInstance(checkoutModalEl);
        if (modal) modal.hide();
    }

    // 장바구니 전체 결제였던 경우 장바구니 비우기
    if (!isDirectBuyNow) {
        cartState.length = 0;
        saveCartToStorage();
        updateCartUI();
        renderMypageCartSection();
    }

    // 주문 완료 축하 모달 세팅 및 표시
    const orderNumEl = document.getElementById('orderSuccessNumber');
    const orderAmtEl = document.getElementById('orderSuccessAmount');
    if (orderNumEl) orderNumEl.textContent = `${orderNumber} (${payName})`;
    if (orderAmtEl) orderAmtEl.textContent = total.toLocaleString() + '원';

    const orderModalEl = document.getElementById('orderSuccessModal');
    if (orderModalEl && typeof bootstrap !== 'undefined') {
        const orderModal = bootstrap.Modal.getOrCreateInstance(orderModalEl);
        orderModal.show();
    } else {
        alert(`주문 및 결제가 정상 완료되었습니다!\n주문번호: ${orderNumber}\n결제수단: ${payName}\n결제금액: ${total.toLocaleString()}원`);
    }
}

/**
 * 장바구니 주문하기 처리 함수 (오프캔버스 하단 버튼 호환)
 */
function handleCheckout() {
    openCheckoutModal();
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

    saveWishlistToStorage();
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

        saveWishlistToStorage();
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
                    <a href="${item.detailUrl}" class="btn btn-sm btn-outline-dark" title="옵션 선택">
                        <i class="bi bi-bag-plus"></i>
                    </a>
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

/**
 * 페이지 로드 시 장바구니 및 위시리스트 상태 초기화
 */
document.addEventListener('DOMContentLoaded', async () => {
    updateWishlistUI();
    await loadCartFromServer();
    renderMypageCartSection();
});

/**
 * 마이페이지의 장바구니 영역 렌더링 함수
 */
function renderMypageCartSection() {
    const container = document.getElementById('mypage-cart-list');
    const emptyEl = document.getElementById('mypage-cart-empty');
    const countBadge = document.getElementById('mypage-cart-count');
    const totalEl = document.getElementById('mypage-cart-total');

    if (!container) return;

    if (countBadge) {
        countBadge.textContent = cartState.reduce((count, item) => count + (Number(item.quantity) || 1), 0);
    }

    if (!cartState || cartState.length === 0) {
        if (emptyEl) emptyEl.style.display = 'block';
        container.innerHTML = '';
        if (totalEl) totalEl.textContent = '0원';
        return;
    }

    if (emptyEl) emptyEl.style.display = 'none';

    let total = 0;
    let html = '';

    cartState.forEach((item, idx) => {
        const itemPrice = parsePrice(item.price);
        const quantity = Number(item.quantity) || 1;
        const itemTotal = itemPrice * quantity;
        total += itemTotal;
        html += `
            <div class="d-flex align-items-center justify-content-between p-3 border rounded-3 mb-2 bg-white shadow-xs">
                <div class="d-flex align-items-center gap-3">
                    <img src="${item.imageUrl || ''}" alt="${item.name}" class="rounded-3" style="width: 55px; height: 55px; object-fit: cover;">
                    <div>
                        <div class="fw-bold small text-dark">${item.name}</div>
                        <div class="text-muted text-xs">${item.color || ''}${item.size ? ` / ${item.size}` : ''}${quantity > 1 ? ` (${quantity}개)` : ''}</div>
                        <div class="text-danger fw-bold small">${itemTotal.toLocaleString()}원</div>
                    </div>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <button type="button" class="btn btn-sm btn-outline-danger border-0" onclick="removeFromCart(${idx}); renderMypageCartSection();" title="삭제">
                        <i class="bi bi-trash fs-6"></i>
                    </button>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
    if (totalEl) totalEl.textContent = total.toLocaleString() + '원';
}
