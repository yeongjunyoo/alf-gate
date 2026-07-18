# 실행 결과

모든 입력 데이터는 SYNTHETIC 목업이다.

## 실행 수치

- 테스트 케이스: 6개
- 문의 로그 커버리지: 8/8, 100%
- 안전 해결률 변경 전: 6/6, 100%
- 안전 해결률 변경 후: 3/6, 50%
- 해결률 변화: -50%p
- 약속 위반 변경 전: 0건
- 약속 위반 변경 후: 4건
- 깨진 케이스: 3개
- 배포 판정: HOLD
- 전체 실행 시간: 14.41초

## LLM 실행

- 성공 호출: 없음
- 로컬 폴백 호출: llm_customer, llm_bot_before, llm_bot_candidate
- 실패 사유: Claude 세션 한도
- 기본 명령: claude -p --max-turns 1 --model sonnet
- 실패 폴백: claude -p --max-turns 1 --model haiku

## 실행법

프로젝트 루트에서 실행한다.

    python3 builds/codex-build/run.py

Claude를 쓸 수 없는 오프라인 환경에서도 완주 여부를 확인할 수 있다.

    GATE_OFFLINE=1 python3 builds/codex-build/run.py

결과 리포트는 builds/codex-build/report.html이다.

## 산출물

- data/: 카페24와 채널톡 공개 필드명 기반 SYNTHETIC 목업
- output/cases.json: 자동 생성된 고객 목표, 성공 기준, 페르소나
- output/simulations_before.json: 승인 지식 대화
- output/simulations_candidate.json: 배포 후보 지식 대화
- output/audit_before.json: 변경 전 결정론 감사
- output/audit_candidate.json: 변경 후 결정론 감사
- output/regression.json: 전후 비교와 배포 판정
- output/llm_runs.json: 모델 호출과 폴백 기록
- report.html: 외부 CDN 없는 단일 한국어 리포트

## 한계

결정론 감사는 정책 날조, 발송 허위, 과잉 확약, 권한 밖 실행 네 범주만 다룬다. 실제 배포에서는 정책 승인 이력과 권한 시스템, 태스크 실행 결과를 연결해야 한다.
