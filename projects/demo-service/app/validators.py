"""입력값 검증 로직."""


def is_valid_email(value: str) -> bool:
    """문자열이 이메일 형식으로 유효한지 판별한다.

    정규식이나 외부 라이브러리 없이 다음 규칙을 순차적으로 검사한다.

    1. ``'@'`` 문자가 정확히 1개 존재한다.
    2. ``'@'`` 를 기준으로 local(앞)과 domain(뒤)으로 분리한다.
    3. local 이 비어있지 않다.
    4. domain 이 비어있지 않다.
    5. domain 에 ``'.'`` 이 최소 1개 존재한다.
    6. domain 이 ``'.'`` 으로 시작하지 않는다.
    7. domain 이 ``'.'`` 으로 끝나지 않는다.

    Args:
        value: 검증 대상 문자열.

    Returns:
        모든 규칙을 만족하면 ``True``, 하나라도 위반하면 ``False``.

    Raises:
        TypeError: ``value`` 가 ``str`` 이 아닐 때.
    """
    if not isinstance(value, str):
        raise TypeError(f"value must be str, got {type(value).__name__}")

    if value.count("@") != 1:
        return False

    local, domain = value.split("@")
    if len(local) < 1:
        return False
    if len(domain) < 1:
        return False
    if "." not in domain:
        return False
    if domain.startswith("."):
        return False
    if domain.endswith("."):
        return False

    return True
