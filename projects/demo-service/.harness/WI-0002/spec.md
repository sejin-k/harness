# 개요

문자열을 입력받아 이메일 형식의 유효성을 판별하는 검증 함수를 `app` 패키지에 제공한다. 입력 검증의 공통 로직을 한 곳에 모아 재사용성과 테스트 가능성을 확보하기 위함이다. 정규식 라이브러리 등 외부 의존 없이 명확한 규칙 기반으로 `True`/`False`를 반환한다.

## 범위

**이번 작업에서 다룰 것**
- `app` 패키지에 이메일 형식 검증 함수 1개 제공
- `'@'` 개수, local/domain 비어있음 여부, domain 내 `'.'` 존재 및 위치 규칙 검증
- 입력이 문자열이 아닐 경우 `TypeError` 발생

**이번 작업에서 다루지 않을 것**
- RFC 5322 등 이메일 표준의 완전한 준수(따옴표 처리, 주석, IP 도메인 리터럴 등)
- MX 레코드 조회, 실제 메일 발송 가능 여부 확인
- 도메인 화이트리스트/블랙리스트, 국제화 도메인(IDN/유니코드) 정규화
- 영속화(DB 저장), API 엔드포인트, UI

## 함수 시그니처(제안)

```python
# app 패키지 내
def is_valid_email(value: str) -> bool:
    ...
```

- 입력: `value` — 검증 대상 문자열
- 출력: 유효한 이메일이면 `True`, 아니면 `False`
- 예외: `value`가 `str`이 아니면 `TypeError`

## 검증 규칙

1. `'@'` 문자가 정확히 1개 존재한다.
2. `'@'`를 기준으로 앞부분(local)과 뒷부분(domain)으로 분리한다.
3. local이 비어있지 않다(길이 ≥ 1).
4. domain이 비어있지 않다(길이 ≥ 1).
5. domain에 `'.'`이 최소 1개 존재한다.
6. domain이 `'.'`으로 시작하지 않는다.
7. domain이 `'.'`으로 끝나지 않는다.

위 규칙을 모두 만족하면 `True`, 하나라도 위반하면 `False`를 반환한다.

## 수용 기준 / Acceptance Criteria

- [ ] `app` 패키지에서 이메일 검증 함수를 import하여 호출할 수 있다.
- [ ] 유효한 이메일 `"user@example.com"`을 입력하면 `True`를 반환한다.
- [ ] `'@'`가 하나도 없는 `"userexample.com"`을 입력하면 `False`를 반환한다.
- [ ] `'@'`가 2개 이상인 `"user@@example.com"` 또는 `"a@b@example.com"`을 입력하면 `False`를 반환한다.
- [ ] local이 비어있는 `"@example.com"`을 입력하면 `False`를 반환한다.
- [ ] domain이 비어있는 `"user@"`를 입력하면 `False`를 반환한다.
- [ ] domain에 `'.'`이 없는 `"user@example"`을 입력하면 `False`를 반환한다.
- [ ] domain이 `'.'`으로 시작하는 `"user@.example.com"`을 입력하면 `False`를 반환한다.
- [ ] domain이 `'.'`으로 끝나는 `"user@example.com."`을 입력하면 `False`를 반환한다.
- [ ] 빈 문자열 `""`을 입력하면 `False`를 반환한다.
- [ ] 문자열이 아닌 입력(예: `123`, `None`, `["user@example.com"]`)을 전달하면 `TypeError`가 발생한다.

## 영향 받는 파일/모듈

- `app/` 패키지: 이메일 검증 함수가 추가될 모듈(예: `app/validators.py` 신설 또는 기존 모듈에 추가 후 `app/__init__.py`에서 노출)
- 테스트: 위 수용 기준을 검증하는 단위 테스트(예: `tests/test_validators.py`)
