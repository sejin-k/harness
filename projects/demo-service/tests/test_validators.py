"""WI-0002 수용 기준 검증: 이메일 형식 유효성 판별."""

import unittest

# AC: app 패키지에서 이메일 검증 함수를 import 하여 호출할 수 있다.
from app import is_valid_email


class IsValidEmailTest(unittest.TestCase):
    def test_importable_and_callable(self):
        # import 가능하고 호출 가능해야 한다.
        self.assertTrue(callable(is_valid_email))

    def test_valid_email_returns_true(self):
        # 유효한 이메일은 True 를 반환한다.
        self.assertTrue(is_valid_email("user@example.com"))

    def test_no_at_returns_false(self):
        # '@' 가 하나도 없으면 False.
        self.assertFalse(is_valid_email("userexample.com"))

    def test_multiple_at_returns_false(self):
        # '@' 가 2개 이상이면 False.
        self.assertFalse(is_valid_email("user@@example.com"))
        self.assertFalse(is_valid_email("a@b@example.com"))

    def test_empty_local_returns_false(self):
        # local 이 비어있으면 False.
        self.assertFalse(is_valid_email("@example.com"))

    def test_empty_domain_returns_false(self):
        # domain 이 비어있으면 False.
        self.assertFalse(is_valid_email("user@"))

    def test_domain_without_dot_returns_false(self):
        # domain 에 '.' 이 없으면 False.
        self.assertFalse(is_valid_email("user@example"))

    def test_domain_starts_with_dot_returns_false(self):
        # domain 이 '.' 으로 시작하면 False.
        self.assertFalse(is_valid_email("user@.example.com"))

    def test_domain_ends_with_dot_returns_false(self):
        # domain 이 '.' 으로 끝나면 False.
        self.assertFalse(is_valid_email("user@example.com."))

    def test_empty_string_returns_false(self):
        # 빈 문자열은 False.
        self.assertFalse(is_valid_email(""))

    def test_non_string_raises_type_error(self):
        # 문자열이 아닌 입력은 TypeError.
        for value in (123, None, ["user@example.com"]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    is_valid_email(value)


if __name__ == "__main__":
    unittest.main()
