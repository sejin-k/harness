"""장바구니 총액 계산 로직."""

# 할인이 적용되기 시작하는 합계 기준(이상)
DISCOUNT_THRESHOLD = 100000
# 적용 할인율(5%)
DISCOUNT_RATE = 0.05


def calculate_cart_total(items: list[dict]) -> float:
    """장바구니 항목 목록의 최종 결제 금액을 계산한다.

    각 항목은 ``{"price": <number>, "qty": <number>}`` 형태이며,
    항목별 ``price * qty`` 의 합계를 구한다. 합계가
    ``DISCOUNT_THRESHOLD`` 이상이면 ``DISCOUNT_RATE`` 만큼 할인한
    금액을 반환한다.

    Args:
        items: 장바구니 항목 리스트.

    Returns:
        할인 규칙이 적용된 최종 금액.

    Raises:
        ValueError: 어떤 항목의 ``price`` 또는 ``qty`` 가 음수일 때.
    """
    subtotal = 0
    for item in items:
        price = item["price"]
        qty = item["qty"]
        if price < 0:
            raise ValueError(f"price must not be negative: {price}")
        if qty < 0:
            raise ValueError(f"qty must not be negative: {qty}")
        subtotal += price * qty

    if subtotal >= DISCOUNT_THRESHOLD:
        return subtotal * (1 - DISCOUNT_RATE)
    return subtotal
