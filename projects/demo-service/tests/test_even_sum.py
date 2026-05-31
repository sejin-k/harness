"""WI-0005 수용 기준 검증 테스트."""

import unittest

from app.even_sum import sum_even


class SumEvenTest(unittest.TestCase):
    def test_importable(self):
        # `from app.even_sum import sum_even` 이 가능하고 호출 가능해야 한다.
        self.assertTrue(callable(sum_even))

    def test_basic_even_sum(self):
        self.assertEqual(sum_even([1, 2, 3, 4, 5, 6]), 12)

    def test_no_even_returns_zero(self):
        self.assertEqual(sum_even([1, 3, 5]), 0)

    def test_empty_list_returns_zero(self):
        self.assertEqual(sum_even([]), 0)

    def test_zero_and_negative_even(self):
        # 0 과 음의 짝수도 짝수로 취급: -2 + 0 = -2
        self.assertEqual(sum_even([-2, -1, 0, 1]), -2)

    def test_non_int_raises_typeerror(self):
        for bad in [[2, "a"], [2, 2.5], [2, None]]:
            with self.subTest(value=bad):
                with self.assertRaises(TypeError):
                    sum_even(bad)

    def test_bool_raises_typeerror(self):
        with self.assertRaises(TypeError):
            sum_even([2, True])
        with self.assertRaises(TypeError):
            sum_even([2, False])

    def test_input_not_mutated(self):
        original = [1, 2, 3, 4, 5, 6]
        snapshot = list(original)
        sum_even(original)
        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main()
