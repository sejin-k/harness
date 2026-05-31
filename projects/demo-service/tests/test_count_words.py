"""WI-0003 수용 기준 검증: 공백 기준 단어 수 계산."""

import unittest

# AC: app 패키지에서 단어 수 계산 함수를 import 하여 호출할 수 있다.
from app import count_words


class CountWordsTest(unittest.TestCase):
    def test_importable_and_callable(self):
        # import 가능하고 호출 가능해야 한다.
        self.assertTrue(callable(count_words))

    def test_two_words(self):
        # "hello world" -> 2
        self.assertEqual(count_words("hello world"), 2)

    def test_single_word(self):
        # "hello" -> 1
        self.assertEqual(count_words("hello"), 1)

    def test_leading_trailing_spaces_ignored(self):
        # 앞뒤 공백은 무시한다. "  hello world  " -> 2
        self.assertEqual(count_words("  hello world  "), 2)

    def test_consecutive_spaces_collapsed(self):
        # 단어 사이 연속 공백은 하나의 구분자로 취급한다. "hello    world" -> 2
        self.assertEqual(count_words("hello    world"), 2)

    def test_tab_and_newline_separators(self):
        # 탭과 개행도 구분자로 취급한다. "hello\tworld\nfoo" -> 3
        self.assertEqual(count_words("hello\tworld\nfoo"), 3)

    def test_empty_string_returns_zero(self):
        # 빈 문자열은 0.
        self.assertEqual(count_words(""), 0)

    def test_whitespace_only_returns_zero(self):
        # 공백만 있는 문자열은 0.
        self.assertEqual(count_words("   "), 0)
        self.assertEqual(count_words("\t\n "), 0)

    def test_non_string_raises_type_error(self):
        # 문자열이 아닌 입력은 TypeError.
        for value in (123, None, ["hello"]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    count_words(value)


if __name__ == "__main__":
    unittest.main()
