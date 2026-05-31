"""온도 변환 도메인 모듈."""


def celsius_to_fahrenheit(celsius: float) -> float:
    """섭씨 온도를 화씨로 변환한다.

    인자:
        celsius: 변환할 섭씨 온도. int 또는 float.
    반환:
        화씨 온도 (항상 float).
    예외:
        TypeError: celsius가 int/float가 아니거나 bool인 경우.
    """
    # bool은 int의 서브클래스이므로 일반 숫자 검사보다 먼저 거른다.
    if isinstance(celsius, bool):
        raise TypeError("celsius must be int or float, not bool")
    if not isinstance(celsius, (int, float)):
        raise TypeError(
            f"celsius must be int or float, not {type(celsius).__name__}"
        )
    return float(celsius) * 9 / 5 + 32
