# WI-0003 기술 설계 — 단어 수 계산 함수

## 접근 방식

명세의 계산 규칙(1~6)을 순수 함수 하나(`count_words`)로 구현한다. 외부 라이브러리·정규식 없이 Python 표준 문자열 연산만으로 처리한다.

핵심은 **인자 없는 `str.split()`** 의 동작이 명세의 단어 분리 규칙과 정확히 일치한다는 점이다.

- 인자 없는 `split()`은 모든 공백 문자(스페이스 `' '`, 탭 `'\t'`, 개행 `'\n'`, `'\r'`, `'\f'`, `'\v'` 등)를 구분자로 사용한다 → 규칙 2.
- 문자열 앞뒤의 공백은 무시한다 → 규칙 3.
- 연속된 공백을 하나의 구분자로 취급하여 빈 토큰을 만들지 않는다 → 규칙 4.
- 공백만 있거나 빈 문자열이면 빈 리스트 `[]`를 반환한다 → 규칙 6 (`len([]) == 0`).

따라서 본문은 사실상 타입 검사 후 `return len(value.split())` 한 줄로 규칙 2~6을 모두 만족한다. 직접 순회/카운트 루프를 작성하는 대신 표준 동작을 활용하여 구현을 단순화하고 버그 표면을 줄인다.

핵심 결정과 이유:

- **신설 모듈 `app/text.py`에 배치.** 단어 수 계산은 "유효성 판별(True/False)"이 아니라 "텍스트 통계"이므로, 검증 전용 모듈인 `app/validators.py`와 관심사가 다르다. 기존 WI-0002가 `cart.py`(도메인)와 `validators.py`(검증)를 분리한 관례를 이어받아, 텍스트 유틸리티는 별도 모듈로 둔다. 향후 줄 수·문자 수 등 다른 텍스트 통계가 추가될 때도 이 모듈에 모은다.
- **`app/__init__.py`에서 재노출(re-export).** 기존 `calculate_cart_total`, `is_valid_email`이 `from app import ...` 형태로 노출되는 관례를 그대로 따라, 수용 기준 "`app` 패키지에서 import하여 호출"을 충족한다.
- **타입 검사를 가장 먼저 수행.** `value`가 `str`이 아니면 곧바로 `TypeError`를 발생시킨다(규칙 1). 비문자열에 대해 `split()` 호출로 인한 `AttributeError`가 새어 나가지 않고, 항상 명시적 `TypeError`가 나도록 보장한다. `validators.py`의 `is_valid_email`과 동일한 가드 스타일·예외 메시지 형식을 따른다.
- **`split()` vs 정규식.** `re.split` 등은 불필요하다. 인자 없는 `split()`이 명세가 요구하는 "모든 공백 문자" 기준 분리·trim·연속 공백 병합을 표준으로 보장하므로 의존성을 추가하지 않는다.

처리 순서:
1. `value`가 `str`인가 → 아니면 `TypeError` (규칙 1)
2. `return len(value.split())` (규칙 2~6 일괄 처리)

## 변경/추가 파일

- **`app/text.py`** (신설) — 단어 수 계산 함수 `count_words`를 정의한다. 모듈 docstring과 함수 docstring은 기존 `app/validators.py`의 한국어 docstring 스타일(설명 + Args/Returns/Raises)을 따른다.
- **`app/__init__.py`** (수정) — `from app.text import count_words`를 추가하고 `__all__`에 `"count_words"`를 포함시켜 `from app import count_words`로 접근 가능하게 한다.
- **`tests/test_count_words.py`** (신설) — 명세의 수용 기준 전체를 검증하는 `unittest` 기반 단위 테스트. `from app import count_words`로 import 하며, `tests/test_validators.py`의 구조(클래스 + 메서드별 AC 매핑 주석, 비문자열은 `subTest` 반복)를 따른다. 파일명은 `harness.yaml`의 테스트 디스커버리 패턴 `test_*.py`에 부합한다.

## 인터페이스/시그니처

```python
# app/text.py
def count_words(value: str) -> int:
    ...
```

- **이름:** `count_words`
- **인자:** `value: str` — 단어 수를 셀 대상 문자열.
- **반환:** `int` — 공백으로 분리된 단어의 개수(0 이상). 빈 문자열·공백만 있는 문자열은 `0`.
- **예외:** `TypeError` — `value`가 `str`이 아닐 때. 메시지 형식은 `is_valid_email`과 통일: `f"value must be str, got {type(value).__name__}"`.

공개 경로:

```python
from app import count_words          # 권장 (수용 기준)
from app.text import count_words     # 모듈 직접 접근도 가능
```

## 엣지케이스 처리

| 입력 | 처리 / 적용 규칙 | 결과 |
|---|---|---|
| `"hello world"` | `split()` → `["hello", "world"]` | `2` |
| `"hello"` | 단어 1개 | `1` |
| `"  hello world  "` | 앞뒤 공백 무시(규칙 3) | `2` |
| `"hello    world"` | 연속 공백 1구분자 처리(규칙 4) | `2` |
| `"hello\tworld\nfoo"` | 탭·개행도 구분자(규칙 2) | `3` |
| `""` | `split()` → `[]` (규칙 6) | `0` |
| `"   "` | 공백만 → `[]` (규칙 6) | `0` |
| `"\t\n "` | 공백류만 → `[]` (규칙 6) | `0` |
| `123`, `None`, `["hello"]` | `str` 아님 (규칙 1) | `TypeError` |

추가 경계 고려사항:

- **`bool` 입력:** Python에서 `bool`은 `int`의 하위 타입이지만 `str`은 아니므로, `isinstance(value, str)` 검사에서 자연스럽게 `TypeError`로 처리된다.
- **구두점·하이픈·언더스코어:** `"a,b"`, `"a-b"`, `"a_b"`는 내부에 공백이 없으므로 각각 `1`로 센다. 구두점 기반 분리는 명세의 "다루지 않을 것"에 해당하므로 의도된 동작이며, 별도 처리를 추가하지 않는다.
- **유니코드 공백:** `str.split()`은 일반 ASCII 공백뿐 아니라 일부 유니코드 공백도 처리하지만, 명세는 UAX #29 정밀 처리를 범위에서 제외했으므로 표준 `split()` 동작을 그대로 채택하고 추가 정규화는 하지 않는다.
- **순서 의존성:** 타입 검사를 최우선으로 두어, 비문자열 입력이 항상 명시적 `TypeError`로 귀결되도록 보장한다(규칙 1 우선).
