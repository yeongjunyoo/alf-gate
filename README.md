# alf-gate

alf-gate는 ALF 테스트의 빈 시험지를 로그로 채우는 세팅 게이트다.

## 문제 배경

ALF 테스트에는 운영자가 직접 입력해야 하는 목 상황과 질문이 필요하다.
과거 상담 로그에는 실제 고객이 반복한 질문과 맥락이 쌓여 있다.
alf-gate는 이 로그를 ALF 테스트 호환 케이스로 바꾸고 지식 변경 전후를 검사한다.

## 아키텍처

- 입력 데이터: 카페24 상품 파일, 채널톡 상담 파일, 지식 아티클, 정책 원장을 읽는다.
- 케이스 생성: 상담을 규칙으로 분류하고 LLM으로 목표, 판정 기준, 페르소나를 만든다.
- 시뮬레이션: LLM 고객과 LLM 상담 봇이 지식 아티클을 바탕으로 대화한다.
- 감사: 봇 답변을 원장과 대조하고 정책 날조, 발송 상태 허위, 과잉 확약, 권한 밖 실행 주장을 찾는다.
- 리그레션: 지식 변경 전후의 해결률, 위반 수, 케이스 판정 악화를 비교해 배포 여부를 권고한다.
- 리포트: 커버리지, 케이스, 실행 결과, 배포 권고를 단일 HTML 파일로 묶는다.

## 실행법

Python 3가 필요하다.
LLM 호출에는 로컬에서 인증된 `claude` 또는 `claude-kimi` CLI를 사용한다.
별도 Python 패키지는 필요하지 않다.

전체 파이프라인을 실행한다.

```bash
python3 app/gate.py all
```

단계별 실행은 아래 순서를 따른다.

```bash
python3 app/gate.py gen
python3 app/gate.py baseline
python3 app/gate.py change
python3 app/gate.py candidate
python3 app/gate.py report
```

- `gen`: 상담 로그에서 테스트 케이스와 커버리지를 만든다.
- `baseline`: 원본 지식으로 변경 전 시뮬레이션을 실행한다.
- `change`: 배송 안내에서 당일 출고 기준을 삭제한 모의 변경본을 만든다.
- `candidate`: 변경된 지식으로 시뮬레이션을 다시 실행한다.
- `report`: 결과를 조립해 `out/report.json`과 `out/report.html`을 만든다.

결과 리포트는 [out/report.html](out/report.html)에서 확인한다.

라이브 웹 데모는 아래로 실행한다. 브라우저에서 파이프라인 단계를 누르며 시뮬레이션 대화를 실시간으로 본다.

```bash
python3 app/server.py
# http://127.0.0.1:8899
```

미리 렌더링된 결과물 예시는 [sample-report.html](sample-report.html)에서 바로 볼 수 있다.

## 3트랙 독립 빌드

같은 컨셉을 서로 다른 에이전트 스택이 각자 처음부터 끝까지 구현했다. 루트 app/은 gajae-code 세션, `builds/codex-build/`는 Codex CLI(gpt-5.6-sol), `builds/kimi-build/`는 Claude Code(Kimi K3)가 독립 빌드한 결과물이며 각 폴더의 RESULT.md에 실행 수치가 있다.

## 데이터

`data/`의 모든 파일은 SYNTHETIC 합성 데이터다. 실제 고객 정보가 아니다.
CSV 열 이름은 카페24 상품 엑셀과 채널톡 상담 다운로드 시트의 공개 문서를 기준으로 했다.

- `cafe24_products.csv`: 상품, 가격, 배송, 교환, 반품 원장이다.
- `channeltalk_userchats.csv`: 상담방 메타데이터다.
- `channeltalk_messages.csv`: 상담 메시지 로그다.
- `knowledge_articles.json`: 상담 봇이 참조하는 지식 아티클이다.
- `policies.json`: 감사에 쓰는 정책 원장이다.

## 한계

- 시뮬레이션 고객과 상담 봇은 모두 LLM이다.
- 감사는 원장에 있는 사실만 대조한다.
- 로그 학습 자체는 글로벌 제품에 이미 존재한다. 차별점은 국내 원본 파일에서 ALF 테스트 호환까지 잇는 한 흐름이다.
