"""텍스트 통계 로직."""


def count_words(value: str) -> int:
    """문자열의 단어 수를 센다.

    정규식이나 외부 라이브러리 없이 인자 없는 ``str.split()`` 의 표준 동작을
    활용한다. 인자 없는 ``split()`` 은 모든 공백 문자(스페이스, 탭, 개행 등)를
    구분자로 사용하고, 앞뒤 공백을 무시하며, 연속된 공백을 하나의 구분자로
    취급하여 빈 토큰을 만들지 않는다.

    Args:
        value: 단어 수를 셀 대상 문자열.

    Returns:
        공백으로 분리된 단어의 개수(0 이상의 정수). 빈 문자열이나 공백만으로
        이루어진 문자열은 ``0``.

    Raises:
        TypeError: ``value`` 가 ``str`` 이 아닐 때.
    """
    if not isinstance(value, str):
        raise TypeError(f"value must be str, got {type(value).__name__}")

    return len(value.split())
