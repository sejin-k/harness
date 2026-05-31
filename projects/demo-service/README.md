# demo-service

하네스 end-to-end 검증용 데모 서비스 (Python, 표준 라이브러리만 사용).

- 비즈니스 로직 모듈을 `app/` 아래에 둔다.
- 테스트는 `tests/` 아래 `test_*.py` 로 작성한다.
- 테스트 실행: `python3 -m unittest discover -p "test_*.py"`
