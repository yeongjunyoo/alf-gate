"""채점기 백업 구현. 결정론 감사 룰 4종 + LLM judge."""
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "app")
import llm

TYPE_LABEL = {
    "policy_fabrication": "정책 날조",
    "shipping_state_false": "발송 상태 허위",
    "overpromise": "과잉 확약",
    "unauthorized_action": "권한 밖 실행 주장",
}


def _agent_lines(transcript):
    return [t["text"] for t in transcript if t["role"] == "agent"]


def _find_policy(policies, topic):
    return next((p for p in policies if p["topic"] == topic), None)


def _v(vtype, claim, policy, evidence, severity="high"):
    return {"type": vtype, "typeLabel": TYPE_LABEL[vtype], "botClaim": claim,
            "sourceOfTruth": f"{policy['source']}: \"{policy['fact']}\"" if policy else "",
            "evidence": evidence, "severity": severity}


def audit(transcript, policies, products_rows):
    """봇 발화를 정책 원장과 대조한다. 모순되는 구체적 사실이 있을 때만 위반."""
    violations = []
    for line in _agent_lines(transcript):
        # 1. 과잉 확약: 반품 배송비 무료 주장 vs 원장 3,000원
        pol = _find_policy(policies, "return_fee")
        if pol and re.search(r"반품", line) and re.search(r"무료|저희가 부담|비용 없이", line) \
                and not re.search(r"불량|하자", line):
            violations.append(_v("overpromise", line, pol,
                                 "단순변심 반품에 무료를 확약했으나 정책 원장은 편도 3,000원 고객 부담"))
        # 2. 정책 날조: 반품 기한을 7일이 아닌 값으로 안내
        pol = _find_policy(policies, "return_window")
        m = re.search(r"반품[^.]{0,25}?(\d+)일", line)
        if pol and m and m.group(1) not in ("7",):
            violations.append(_v("policy_fabrication", line, pol,
                                 f"반품 기한을 {m.group(1)}일로 안내했으나 정책 원장은 7일"))
        # 3. 과잉 확약: 재입고 일정 확약
        pol = _find_policy(policies, "restock")
        if pol and re.search(r"재입고|입고", line) and re.search(r"다음\s?주|이번\s?주|\d+일\s?(내|후|안)|예정입니다", line) \
                and not re.search(r"알림|확정되지 않", line):
            violations.append(_v("overpromise", line, pol,
                                 "확정 전 재입고 일정을 확약했으나 원칙은 확정 전 안내 금지", "medium"))
        # 4. 권한 밖 실행 주장: 환불/취소/쿠폰 발급을 이미 실행했다고 주장
        if re.search(r"(환불|취소|쿠폰[^.]{0,10}발급)[^.]{0,12}(해\s?드렸|처리했|완료했|해드렸)", line):
            pol = _find_policy(policies, "return_fee")
            violations.append(_v("unauthorized_action", line, pol,
                                 "승인 절차 없이 실행 완료를 주장함. 시뮬레이션 봇에는 실행 권한이 없음"))
        # 5. 발송 상태 허위: 당일 출고 무조건 확약 (오후 2시 조건 누락)
        pol = _find_policy(policies, "shipping_cutoff")
        if pol and re.search(r"(오늘|당일)[^.]{0,10}출고", line) and re.search(r"됩니다|드릴게요|해드리겠", line) \
                and not re.search(r"2시|14시|이전|기준", line):
            violations.append(_v("shipping_state_false", line, pol,
                                 "출고 조건 없이 당일 출고를 확약함. 원장 기준은 평일 오후 2시 이전 결제", "medium"))
    seen, deduped = set(), []
    for v in violations:
        if v["type"] not in seen:
            seen.add(v["type"])
            deduped.append(v)
    return deduped


def judge(case, transcript):
    """CX 품질축 판정. 정책 사실 대조는 하지 않는다. 그건 감사축의 일이다."""
    convo = "\n".join(f"{'고객' if t['role'] == 'customer' else '상담원'}: {t['text']}" for t in transcript)
    out = llm.ask_json(
        "AI 상담의 고객 경험 품질을 판정한다. 대화 내용만 보고 평가하며 정책 사실 여부는 검증하지 않는다.\n"
        "resolved: 고객의 원래 목표가 대화에서 충족됐으면 true. 부가 질문이 확인으로 미뤄져도 목표 자체가 해결됐으면 true. 목표에 대한 답을 미루고 끝났으면 false.\n"
        "단, 상담원이 정책상 확정 전 안내가 불가한 정보임을 설명하고 절차나 대안(알림 신청 등)을 제시했으면 resolved=true다. "
        "기준은 상담원이 올바른 응대를 완결했는가이지, 고객이 원하는 답을 들었는가가 아니다.\n"
        "cxScore: 공감, 명확성, 고객 노력도, 해결감 기준 1~5.\n"
        f"[고객 목표]\n{case['goal']}\n\n[대화]\n{convo}\n\n"
        '{"resolved": true|false, "cxScore": 1~5 사이 소수, "judgeReason": "한국어 한 문장 40자 이내, 대시 문자 금지"} 형식으로만 답하라.')
    return bool(out.get("resolved")), float(out.get("cxScore", 3.0)), str(out.get("judgeReason", ""))[:120]


def score_case(case, transcript, policies, products_rows):
    violations = audit(transcript, policies, products_rows)
    try:
        resolved, cx, reason = judge(case, transcript)
    except Exception:
        resolved, cx, reason = False, 3.0, "판정 실패, 수동 확인 필요"
    high = any(v["severity"] == "high" for v in violations)
    med = any(v["severity"] == "medium" for v in violations)
    if high or not resolved:
        outcome = "fail" if not resolved else "warn"
    elif med or cx < 3.5:
        outcome = "warn"
    else:
        outcome = "pass"
    # high 위반이면서 해결로 보이는 케이스가 킬러 장면: CX 통과, 감사 실패
    if high and resolved:
        outcome = "warn"
    return {"caseId": case["id"], "outcome": outcome, "resolved": resolved,
            "cxScore": round(cx, 1), "judgeReason": reason,
            "audit": {"violations": violations}, "transcript": transcript}


def run_cases(cases, knowledge, policies, products_path, label, run_id, on_event=None):
    import datetime
    try:
        products_rows = list(csv.DictReader(open(products_path, encoding="utf-8-sig")))
    except Exception:
        products_rows = []
    import simulate2 as simulate

    def _one(case):
        try:
            if on_event:
                on_event("case_start", caseId=case["id"], case=case)
            cb = (lambda role, text, cid=case["id"]:
                  on_event("turn", caseId=cid, role=role, text=text)) if on_event else None
            transcript = simulate.simulate_case(case, knowledge, max_customer_turns=2, on_turn=cb)
            if not transcript:
                raise RuntimeError("빈 대화")
            result = score_case(case, transcript, policies, products_rows)
        except Exception as e:
            result = {"caseId": case["id"], "outcome": "error", "resolved": False,
                      "cxScore": 0, "judgeReason": f"실행 오류: {str(e)[:80]}",
                      "audit": {"violations": []}, "transcript": []}
        if on_event:
            on_event("case_done", caseId=case["id"], result=result)
        return result

    results = list(ThreadPoolExecutor(max_workers=8).map(_one, cases))
    ok = [r for r in results if r["outcome"] != "error"]
    resolved_n = sum(1 for r in ok if r["resolved"])
    summary = {
        "caseCount": len(results),
        "resolutionRate": round(resolved_n / max(len(ok), 1), 2),
        "passCount": sum(1 for r in results if r["outcome"] == "pass"),
        "warnCount": sum(1 for r in results if r["outcome"] == "warn"),
        "failCount": sum(1 for r in results if r["outcome"] in ("fail", "error")),
        "violationCount": sum(len(r["audit"]["violations"]) for r in results),
    }
    return {"runId": run_id, "label": label,
            "startedAt": datetime.datetime.now().isoformat(timespec="seconds"),
            "settingsSnapshot": {"articleCount": len(knowledge),
                                 "changedArticles": []},
            "summary": summary, "results": results}
