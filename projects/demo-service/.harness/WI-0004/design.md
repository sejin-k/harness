# WI-0004 설계: 섭씨→화씨 변환 함수

## 접근 방식

`app` 패키지에 섭씨를 화씨로 변환하는 단일 순수 함수 `celsius_to_fahrenheit`를
구현한다. 변환 공식은 `F = C * 9/5 + 32`.

핵심 결정과 이유:

- **모듈 분리 (`app/temperature.py`)**: 레포 관례상 비즈니스 로직은 `app/` 아래
  모듈에 둔다. 온도 변환이라는 도메인을 별도 모듈로 분리해 향후 역방향 변환 등이
  추가되어도 한곳에 모이도록 한다. (이번 범위에는 정방향 1개만 구현.)
- **패키지 레벨 export (`app/__init__.py`)**: 수용 기준 "`app` 패키지에서 변환
  함수를 import 할 수 있다"를 충족하기 위해 `from app import celsius_to_fahrenheit`
  형태로 바로 쓸 수 있게 `__init__.py`에서 재노출한다. `from app.temperature import ...`
  경로도 함께 유효하다.
- **타입 검증을 함수 진입부에서 명시적으로 수행**: 숫자가 아닌 입력은 변환 연산을
  시도하기 전에 `TypeError`로 막는다. Python에서 `bool`은 `int`의 서브클래스라
  `isinstance(x, int)`로는 `True`/`False`가 통과해버리므로, **`bool`을 먼저
  명시적으로 거부**한 뒤 `int`/`float` 여부를 검사한다. (수용 기준의 bool 거부 항목
  대응.)
- **반환 타입 항상 `float`**: 결과를 `float(...)`로 감싸 `int` 입력이어도 항상
  `float`를 반환하도록 보장한다. (`* 9 / 5`가 이미 float를 만들지만, 의도를 코드로
  명시하고 향후 공식 변경에도 안전하도록 명시적 캐스팅 유지.)
- **표준 라이브러리만 사용**: 레포 정책(README)에 따라 외부 의존성 없이 구현하고,
  테스트는 `unittest`로 작성한다.

## 변경/추가 파일

- `app/temperature.py` *(신규)* — `celsius_to_fahrenheit` 함수 정의. 타입 검증 +
  변환 공식 + float 반환을 담당하는 도메인 모듈.
- `app/__init__.py` *(수정)* — `from app.temperature import celsius_to_fahrenheit`
  재노출 및 `__all__`에 등록하여 패키지 레벨 import 진입점 제공.
- `tests/test_temperature.py` *(신규)* — 수용 기준을 1:1로 검증하는 `unittest`
  테스트. 정상 변환값, 반환 타입, 예외 케이스를 모두 포함.

## 인터페이스/시그니처

```python
# app/temperature.py
def celsius_to_fahrenheit(celsius: float) -> float:
    """섭씨 온도를 화씨로 변환한다.

    인자:
        celsius: 변환할 섭씨 온도. int 또는 float.
    반환:
        화씨 온도 (항상 float).
    예외:
        TypeError: celsius가 int/float가 아니거나 bool인 경우.
    """
```

- **이름**: `celsius_to_fahrenheit`
- **인자**: `celsius` — `int` 또는 `float` (bool 제외)
- **반환**: `float` — 입력 타입과 무관하게 항상 `float`
- **예외**: `TypeError` — 숫자가 아닌 입력(str, None 등) 및 bool 입력 시

패키지 레벨 노출:

```python
# app/__init__.py
from app.temperature import celsius_to_fahrenheit
__all__ = ["celsius_to_fahrenheit"]
```

→ `from app import celsius_to_fahrenheit` 및
`from app.temperature import celsius_to_fahrenheit` 모두 동작.

## 엣지케이스 처리

| 입력 | 처리 | 근거(수용 기준) |
|------|------|------------------|
| `0` | `32.0` 반환 | `0 → 32.0` |
| `100` | `212.0` 반환 | `100 → 212.0` |
| `-40` | `-40.0` 반환 (음수 정상 처리) | `-40 → -40.0` |
| `37.5` (float) | `99.5` 반환 | `37.5 → 99.5` |
| `int` 입력 | `float`로 캐스팅 후 반환 | 반환 타입 항상 float |
| `"10"` (str) | `TypeError` | 문자열 거부 |
| `None` | `TypeError` | None 거부 |
| `True` / `False` (bool) | `TypeError` | bool을 숫자로 취급 금지 |

검증 로직 순서(함수 진입부):

1. `isinstance(celsius, bool)` 이면 즉시 `TypeError` 발생.
   - 이유: `bool`은 `int`의 서브클래스이므로 일반 숫자 검사보다 **먼저** 걸러야 한다.
2. `isinstance(celsius, (int, float))`가 아니면 `TypeError` 발생.
   - `str`, `None`, 기타 객체 모두 여기서 거부된다.
3. 통과 시 `float(celsius) * 9 / 5 + 32` 계산 후 반환.

부동소수점 주의: `37.5 → 99.5`처럼 명세에 명시된 값은 정확히 표현되지만, 테스트에서
부동소수점 오차 가능성이 있는 비교는 `assertAlmostEqual`로 작성하고, 정수 경계값
(`32.0`, `212.0`, `-40.0`)은 `assertEqual`로 정확 비교한다. 반올림/유효 자릿수 정책은
범위에서 제외(명세 "다루지 않을 것")이므로 별도 처리하지 않는다.
