# WI-0005 기술 설계 — 짝수 합산 함수 (`sum_even`)

## 접근 방식

명세는 "정수 리스트에서 짝수 원소만 골라 합을 반환"하는 순수 함수 하나를 요구한다. 외부 인터페이스·성능 최적화·정수 외 타입 합산은 모두 범위 밖이므로, 단일 모듈에 단순한 순수 함수로 구현한다.

핵심 결정과 이유:

1. **단일 순수 함수로 구현.** 상태나 부수효과가 없고, 입력 리스트를 변경하지 않는다(수용 기준 8). 따라서 클래스나 설정 없이 `app/even_sum.py`에 함수 하나만 둔다. 레포 관례(비즈니스 로직은 `app/` 아래, 표준 라이브러리만 사용)와 일치한다.

2. **타입 검증을 합산 전에 명시적으로 수행.** 명세는 정수가 아닌 원소가 *하나라도* 있으면 `TypeError`를 요구한다(수용 기준 6·7). "검증 후 합산" 순서로 분리하면, 부분 합산 같은 중간 상태 없이 깔끔하게 예외를 던질 수 있다. 단순 구현이므로 두 번 순회(검증 1회 + 합산 1회)해도 무방하며, 명세상 성능 최적화는 범위 밖이다.

3. **`bool` 배제를 위해 `type(x) is int` 대신 `isinstance` + `bool` 제외 전략 사용.** 파이썬에서 `bool`은 `int`의 하위 타입이라 `isinstance(True, int)`는 `True`다. 명세(수용 기준 7)는 `bool`을 정수가 아닌 입력으로 취급하라고 한다. 따라서 판정식은 `isinstance(x, int) and not isinstance(x, bool)`로 한다. (`type(x) is int`로도 가능하나, 향후 `int` 하위 클래스 허용 여지를 남기고 의도를 명확히 드러내기 위해 `isinstance` 기반으로 한다.)

4. **짝수 판정은 `x % 2 == 0`.** 음수·0에 대해서도 파이썬 `%`가 일관되게 동작하여 `-2 % 2 == 0`, `0 % 2 == 0`이므로 별도 분기 없이 수용 기준 5를 만족한다.

5. **입력은 변경하지 않음.** 리스트를 인덱스로 수정하거나 정렬하지 않고 읽기만 하므로 수용 기준 8을 자연히 만족한다(추가 방어 코드 불필요).

6. **테스트는 구현 단계에서 `unittest`로 작성.** `harness.yaml`의 test 커맨드가 `python3 -m unittest discover -p "test_*.py"`이므로 `tests/test_even_sum.py`는 `unittest.TestCase` 기반으로 작성한다(설계 단계에서는 파일을 만들지 않음).

## 변경/추가 파일

- **`app/even_sum.py`** (신규) — `sum_even` 함수 구현. 모듈 docstring으로 목적을 기술하고, 표준 라이브러리만 사용한다.
- **`app/__init__.py`** (기존, 현재 비어 있음) — 명세상 "필요 시 export 추가". 수용 기준은 `from app.even_sum import sum_even` 경로만 요구하므로 **변경하지 않아도 충족**된다. 다만 패키지 레벨 노출이 바람직하면 `from app.even_sum import sum_even`과 `__all__`을 추가할 수 있다(선택 사항, 구현 단계 판단).
- **`tests/test_even_sum.py`** (신규, 구현 단계에서 작성) — 아래 8개 수용 기준을 각각 검증하는 `unittest` 테스트 케이스.

## 인터페이스/시그니처

```python
def sum_even(numbers: list[int]) -> int:
    """정수 리스트에서 짝수 원소들의 합을 반환한다.

    Args:
        numbers: 정수들의 리스트. 빈 리스트 허용.

    Returns:
        짝수(음의 짝수와 0 포함) 원소들의 합. 짝수가 없거나 빈 리스트면 0.

    Raises:
        TypeError: 원소 중 int가 아닌 값(또는 bool)이 하나라도 있을 때.
    """
```

- **이름**: `sum_even`
- **인자**: `numbers` — 정수 리스트 (`list[int]`)
- **반환**: `int` — 짝수 원소들의 합 (없으면 `0`)
- **예외**: `TypeError` — 원소 중 `int`가 아니거나 `bool`인 값이 존재할 때
- **import 경로**: `from app.even_sum import sum_even` (수용 기준 1)

구현 로직(의사 코드):

```
def sum_even(numbers):
    # 1) 검증: 모든 원소가 int이고 bool이 아니어야 함
    for x in numbers:
        if not isinstance(x, int) or isinstance(x, bool):
            raise TypeError(...)   # 어떤 값이 문제인지 메시지에 포함
    # 2) 합산: 짝수만
    return sum(x for x in numbers if x % 2 == 0)
```

## 엣지케이스 처리

| 입력 | 처리 | 결과 | 근거(수용 기준) |
|---|---|---|---|
| `[1, 2, 3, 4, 5, 6]` | 짝수 2,4,6 합산 | `12` | AC 2 |
| `[1, 3, 5]` | 짝수 없음 → `sum()` 빈 generator | `0` | AC 3 |
| `[]` (빈 리스트) | 순회 0회, 합 없음 | `0` | AC 4 |
| `[-2, -1, 0, 1]` | `-2 % 2 == 0`, `0 % 2 == 0` → -2+0 | `-2` | AC 5 |
| `[2, "a"]` / `[2, 2.5]` / `[2, None]` | 검증 단계에서 `isinstance(x, int)` 실패 | `TypeError` | AC 6 |
| `[2, True]` | `isinstance(True, int)`는 True지만 `isinstance(True, bool)`도 True → 배제 | `TypeError` | AC 7 |
| 호출 후 원본 리스트 | 읽기 전용 순회, 수정 없음 | 입력 불변 | AC 8 |

추가 고려:
- **검증과 합산의 순서**: 검증을 먼저 전부 끝낸 뒤 합산하므로, `[2, "a"]`처럼 유효 원소와 무효 원소가 섞여 있어도 부분 합 없이 `TypeError`만 발생한다.
- **`float`로 표현된 정수값**(예: `2.0`): `isinstance(2.0, int)`는 `False`이므로 `TypeError`. 명세 "다루지 않을 것"(부동소수점 포함 동작)과 일치한다.
- **`numbers` 자체가 리스트가 아닌 경우**(예: `None`, 정수 하나): 명세 범위 밖(입력은 "정수 리스트" 전제)이라 별도 방어 코드는 두지 않는다. iterable이 아니면 순회 시점에서 자연히 `TypeError`가 발생한다. 구현 단계에서 필요하면 보강 가능.
