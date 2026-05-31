"""WI-0001 수용 기준 검증: 장바구니 총액 계산."""

import unittest

# AC: app 패키지에서 함수를 import 하여 호출할 수 있다.
from app import calculate_cart_total


class CalculateCartTotalTest(unittest.TestCase):
    def test_importable_and_callable(self):
        # import 가능하고 호출 가능해야 한다.
        self.assertTrue(callable(calculate_cart_total))

    def test_empty_list_returns_zero(self):
        # 빈 리스트는 0을 반환한다.
        self.assertEqual(calculate_cart_total([]), 0)

    def test_below_threshold_no_discount(self):
        # 합계가 100000 미만이면 할인 없이 그대로 반환한다.
        items = [{"price": 1000, "qty": 2}, {"price": 500, "qty": 3}]
        self.assertEqual(calculate_cart_total(items), 3500)

    def test_exactly_threshold_applies_discount(self):
        # 합계가 정확히 100000일 때 5% 할인 -> 95000 (경계값, 이상 포함).
        items = [{"price": 100000, "qty": 1}]
        self.assertEqual(calculate_cart_total(items), 95000)

    def test_above_threshold_applies_discount(self):
        # 합계 200000 초과 시 5% 할인 -> 190000.
        items = [{"price": 100000, "qty": 2}]
        self.assertEqual(calculate_cart_total(items), 190000)

    def test_negative_price_raises_value_error(self):
        # price가 음수이면 ValueError.
        with self.assertRaises(ValueError):
            calculate_cart_total([{"price": -1, "qty": 1}])

    def test_negative_qty_raises_value_error(self):
        # qty가 음수이면 ValueError.
        with self.assertRaises(ValueError):
            calculate_cart_total([{"price": 1000, "qty": -1}])

    def test_zero_price_or_qty_contributes_zero(self):
        # price 또는 qty가 0이면 정상 처리되고 해당 항목은 0을 기여한다.
        items = [
            {"price": 0, "qty": 5},
            {"price": 1000, "qty": 0},
            {"price": 1000, "qty": 2},
        ]
        self.assertEqual(calculate_cart_total(items), 2000)


if __name__ == "__main__":
    unittest.main()
