"""섭씨→화씨 변환 함수의 수용 기준 검증 테스트."""

import unittest

# 수용 기준: app 패키지에서 변환 함수를 import 할 수 있다.
from app import celsius_to_fahrenheit


class CelsiusToFahrenheitTest(unittest.TestCase):
    def test_freezing_point(self):
        # 0(섭씨) -> 32.0
        self.assertEqual(celsius_to_fahrenheit(0), 32.0)

    def test_boiling_point(self):
        # 100(섭씨) -> 212.0
        self.assertEqual(celsius_to_fahrenheit(100), 212.0)

    def test_minus_forty(self):
        # -40(섭씨) -> -40.0
        self.assertEqual(celsius_to_fahrenheit(-40), -40.0)

    def test_float_input(self):
        # 37.5(float) -> 99.5
        self.assertEqual(celsius_to_fahrenheit(37.5), 99.5)

    def test_int_input_returns_float(self):
        # int 입력이어도 반환 타입은 항상 float
        result = celsius_to_fahrenheit(0)
        self.assertIsInstance(result, float)

    def test_float_input_returns_float(self):
        # float 입력이어도 반환 타입은 항상 float
        result = celsius_to_fahrenheit(37.5)
        self.assertIsInstance(result, float)

    def test_string_input_raises_type_error(self):
        # 문자열 입력 시 TypeError
        with self.assertRaises(TypeError):
            celsius_to_fahrenheit("10")

    def test_none_input_raises_type_error(self):
        # None 입력 시 TypeError
        with self.assertRaises(TypeError):
            celsius_to_fahrenheit(None)

    def test_bool_true_raises_type_error(self):
        # True를 숫자로 취급하지 않고 TypeError
        with self.assertRaises(TypeError):
            celsius_to_fahrenheit(True)

    def test_bool_false_raises_type_error(self):
        # False를 숫자로 취급하지 않고 TypeError
        with self.assertRaises(TypeError):
            celsius_to_fahrenheit(False)


if __name__ == "__main__":
    unittest.main()
