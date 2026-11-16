# GovBondDashboard

외화 국채 정보 대시보드. 각국 재무부·중앙은행이 공개한 데이터를 매일 받아 한 화면에 보여준다.

## 운영 정책

이 저장소는 공개 저장소다. 아래 네 가지는 예외 없이 지킨다.

1. 공용 API에서 받은 공개 데이터만 다룬다.
2. 내부 자료(보유 잔고, 거래 내역, 한도, 사내 문서)는 일절 올리지 않는다.
3. KP물 등 개별 회사채, 투자 검토 대상 목록처럼 투자 판단과 직결된 정보는 싣지 않는다. 국채 입찰 결과처럼 시장 전체에 공개된 발행 통계만 싣는다.
4. 수집 대상은 `config/allowlist.json`에 등록된 주소로 한정한다. 추가는 PR로만 한다.

정책은 코드로도 막아 둔다.

- 수집 스크립트는 허용 목록 밖 주소를 호출하면 그 자리에서 멈춘다. 리다이렉트로 목록 밖으로 나가는 경우도 같다.
- PR과 일별 실행 때마다 `scripts/check_policy.py`가 돈다. 허용 목록 밖 주소, 등록되지 않은 데이터 파일, 엑셀·PDF 같은 수동 자료가 있으면 실패한다.

## 현재 범위

| 국가 | 내용 | 출처 |
|---|---|---|
| 미국 | 수익률 곡선(일별), 입찰 결과·예정 | 미 재무부, TreasuryDirect, Fiscal Data |

예정: 캐나다, 독일, 영국, 일본, 유로존 커브.

## 구조

```
config/allowlist.json        수집 허용 주소, 산출 파일 목록
scripts/common.py            허용 목록 검사, 호출 공용 함수
scripts/fetch_us.py          미국채 수집
scripts/check_policy.py      정책 점검
scripts/probe.py             새 출처 응답 확인 (로그에만 출력)
tests/                       파싱 단위 테스트
docs/index.html              대시보드 화면 (GitHub Pages)
docs/data/us.json            수집 결과 (자동 생성, 손으로 고치지 않는다)
.github/workflows/daily.yml  일별 수집
.github/workflows/policy.yml PR 점검
.github/workflows/probe.yml  새 출처 응답 확인 (probe/ 브랜치에서만 실행)
```

## 동작

- 매일 08:47(KST)에 수집해서 `docs/data/`를 갱신한다. 미국 장 마감 후 재무부가 당일 곡선을 올린 뒤 시각이다.
- 외부 라이브러리는 쓰지 않는다. 파이썬 표준 라이브러리만 쓴다.
- 화면도 외부 스크립트나 글꼴을 불러오지 않는다.

## 로컬 실행

```
python3 scripts/check_policy.py
python3 -m unittest discover -s tests
python3 scripts/fetch_us.py
python3 -m http.server -d docs 8000
```
