# WI-0002 기술 설계 — 이메일 형식 검증 함수

## 접근 방식

명세의 검증 규칙(규칙 1~7)을 순수 함수 하나(`is_valid_email`)로 구현한다. 외부 라이브러리·정규식 없이 문자열 기본 연산(`str.count`, `str.split`, `str.startswith`, `str.endswith`, `in`)만으로 규칙을 순차 검사한다.

핵심 결정과 이유:

- **신설 모듈 `app/validators.py`에 배치.** 기존 `app/cart.py`(장바구니 도메인)와 검증 로직은 관심사가 다르므로 섞지 않는다. 명세가 권장하는 "입력 검증 공통 로직을 한 곳에 모은다"는 의도에 맞춰 검증 전용 모듈을 둔다. 향후 다른 검증 함수가 추가될 때도 이 모듈에 모은다.
- **`app/__init__.py`에서 재노출(re-export).** 기존 `calculate_cart_total`이 `from app import ...` 형태로 import 되는 관례(`tests/test_cart.py` 참고)를 그대로 따라, 수용 기준 "`app` 패키지에서 import하여 호출"을 충족한다.
- **타입 검사를 가장 먼저 수행.** `value`가 `str`이 아니면 곧바로 `TypeError`를 발생시킨다. `str`이 아닌 입력에 대해 `False`를 반환하지 않고 예외로 구분하라는 명세를 따른다. (예: `bool`/`int`인 `True`에 대해 문자열 연산을 시도하지 않도록 조기 차단)
- **규칙 위반 시 조기 반환(early return) 패턴.** 각 규칙을 위반하면 즉시 `False`를 반환하고, 모든 규칙을 통과하면 `True`를 반환한다. `cart.py`의 가드(guard) 스타일과 일관된다.
- **`'@'` 정확히 1개 검사에는 `str.count('@') == 1`을 사용**한다. 이렇게 하면 `'@'`가 0개(규칙 1 위반)와 2개 이상(`"user@@example.com"`, `"a@b@example.com"`)을 한 번에 걸러내고, 이후 `split('@')`이 정확히 2조각을 보장한다.

규칙 검사 순서(통과해야 다음으로 진행):
1. `value`가 `str`인가 → 아니면 `TypeError`
2. `value.count('@') == 1` → 아니면 `False` (규칙 1, '@' 0개/2개 이상 동시 처리)
3. `local, domain = value.split('@')`
4. `len(local) >= 1` → 아니면 `False` (규칙 3)
5. `len(domain) >= 1` → 아니면 `False` (규칙 4)
6. `'.' in domain` → 아니면 `False` (규칙 5)
7. `not domain.startswith('.')` → 아니면 `False` (규칙 6)
8. `not domain.endswith('.')` → 아니면 `False` (규칙 7)
9. 위 모두 통과 → `True`

## 변경/추가 파일

- **`app/validators.py`** (신설) — 이메일 형식 검증 함수 `is_valid_email`을 정의한다. 모듈 docstring과 함수 docstring은 기존 `app/cart.py`의 한국어 docstring 스타일(Args/Returns/Raises)을 따른다.
- **`app/__init__.py`** (수정) — `from app.validators import is_valid_email`를 추가하고 `__all__`에 `"is_valid_email"`을 포함시켜 `from app import is_valid_email`로 접근 가능하게 한다.
- **`tests/test_validators.py`** (신설) — 명세의 수용 기준 전체를 검증하는 `unittest` 기반 단위 테스트. `from app import is_valid_email`로 import 하며, `tests/test_cart.py`의 구조(클래스 + 메서드별 AC 매핑 주석)를 따른다. 파일명은 `harness.yaml`의 테스트 디스커버리 패턴 `test_*.py`에 부합한다.

## 인터페이스/시그니처

```python
# app/validators.py
def is_valid_email(value: str) -> bool:
    ...
```

- **이름:** `is_valid_email`
- **인자:** `value: str` — 검증 대상 문자열.
- **반환:** `bool` — 모든 검증 규칙(명세 1~7)을 만족하면 `True`, 하나라도 위반하면 `False`.
- **예외:** `TypeError` — `value`가 `str`이 아닐 때. 메시지 예: `f"value must be str, got {type(value).__name__}"`.

공개 경로:

```python
from app import is_valid_email        # 권장 (수용 기준)
from app.validators import is_valid_email  # 모듈 직접 접근도 가능
```

## 엣지케이스 처리

| 입력 | 적용 규칙 / 처리 | 결과 |
|---|---|---|
| `"user@example.com"` | 규칙 1~7 모두 통과 | `True` |
| `"userexample.com"` | `'@'` 0개 → `count != 1` | `False` |
| `"user@@example.com"` | `'@'` 2개 → `count != 1` | `False` |
| `"a@b@example.com"` | `'@'` 2개 → `count != 1` | `False` |
| `"@example.com"` | local 길이 0 (규칙 3) | `False` |
| `"user@"` | domain 길이 0 (규칙 4) | `False` |
| `"user@example"` | domain에 `'.'` 없음 (규칙 5) | `False` |
| `"user@.example.com"` | domain이 `'.'`으로 시작 (규칙 6) | `False` |
| `"user@example.com."` | domain이 `'.'`으로 끝남 (규칙 7) | `False` |
| `""` (빈 문자열) | `'@'` 0개 → `count != 1` | `False` |
| `123`, `None`, `["user@example.com"]` | `str`이 아님 | `TypeError` |

추가 경계 고려사항:

- **`bool` 입력:** Python에서 `bool`은 `int`의 하위 타입이지만 `str`은 아니므로, `isinstance(value, str)` 검사에서 자연스럽게 `TypeError`로 처리된다.
- **공백·점만으로 이루어진 입력:** 예 `"a@ ."`, `"a@.."` 등은 규칙 6/7(시작·끝 `'.'`)이나 규칙 4에서 걸러지며, 그 외 trim/공백 정규화는 명세 범위 밖이라 수행하지 않는다(공백 문자 자체를 별도로 거부하지 않음 — 명세에 규정이 없으므로 규칙 1~7만 적용).
- **연속 점 `..` (예: `"user@ex..com"`):** 규칙 5~7만 적용되므로 시작·끝이 아닌 한 `True`가 될 수 있다. 명세의 "다루지 않을 것"(RFC 완전 준수)에 해당하므로 의도된 동작이며 추가 거부하지 않는다.
- **순서 의존성:** 타입 검사를 최우선으로 두어, 비문자열에 대해 `count`/`split` 호출로 인한 `AttributeError`가 발생하지 않고 항상 명시적 `TypeError`가 나도록 보장한다.
