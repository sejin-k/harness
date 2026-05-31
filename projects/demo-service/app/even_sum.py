"""정수 리스트에서 짝수 원소들의 합을 구하는 유틸리티."""


def sum_even(numbers):
    """정수 리스트에서 짝수 원소들의 합을 반환한다.

    Args:
        numbers: 정수들의 리스트. 빈 리스트 허용.

    Returns:
        짝수(음의 짝수와 0 포함) 원소들의 합. 짝수가 없거나 빈 리스트면 0.

    Raises:
        TypeError: 원소 중 int가 아닌 값(또는 bool)이 하나라도 있을 때.
    """
    # 1) 검증: 모든 원소가 int이고 bool이 아니어야 함 (합산 전에 전부 확인)
    for x in numbers:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError(
                f"sum_even() expects a list of int, got {type(x).__name__}: {x!r}"
            )
    # 2) 합산: 짝수만 (음수·0도 % 연산으로 일관 처리)
    return sum(x for x in numbers if x % 2 == 0)
