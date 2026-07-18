"""AI 상담 케이스를 시뮬레이션하고 감사 결과를 채점한다."""

import argparse
import csv
import datetime as dt
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

try:
    from . import llm
    from .simulate import clean_text, simulate_case
except ImportError:
    import llm
    from simulate import clean_text, simulate_case


TYPE_LABELS = {
    "policy_fabrication": "정책 날조",
    "shipping_state_false": "발송 상태 허위",
    "overpromise": "과잉 확약",
    "unauthorized_action": "권한 밖 실행",
}

NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>만원|퍼센트|개월|시간|원|%|일|시|분|주|개|회)?"
)
CANDIDATE_RE = re.compile(
    r"\d|무료|보장|즉시|무조건|반드시|당일|오늘|내일|"
    r"발송|출고|배송\s*(?:완료|중|준비)|상품\s*준비|환불|취소|교환|쿠폰"
)
ACTION_CLAIM_RE = re.compile(
    r"(?P<action>환불|주문\s*취소|취소|교환|반품|쿠폰|할인).{0,16}?"
    r"(?:처리|완료|발급|적용|접수)\s*"
    r"(?:해\s*드렸|했습니다|하였습니다|됐습니다|됐어요|되었습니다|완료했|해\s*드리겠|해\s*드릴게요|할게요|하겠습니다)"
)
AUTHORITY_DENIAL_RE = re.compile(
    r"권한(?:이)?\s*없|직접.{0,8}불가|처리.{0,8}불가|자동.{0,8}불가|"
    r"담당자.{0,12}확인|관리자.{0,12}승인|승인.{0,8}필요|"
    r"상담원.{0,8}이관|접수만\s*가능|미처리|미환불|처리하지\s*않|"
    r"NOT_REFUNDED|PENDING|FALSE",
    re.I,
)

ANCHOR_TERMS = {
    "shipping_fee": ("배송비", "반품비", "교환비", "택배비", "운임", "고객 부담", "shipping fee", "shipping_fee", "return fee", "return_fee"),
    "return_deadline": ("반품", "교환", "청약 철회", "수령 후", "return window", "return_window", "exchange window", "exchange_window"),
    "refund_duration": ("환불", "입금", "결제 취소", "refund duration", "refund_duration"),
    "shipping_cutoff": ("당일 출고", "출고 기준", "결제", "마감", "shipping cutoff", "shipping_cutoff", "same day"),
    "shipping_duration": ("배송 기간", "도착", "배송 예정", "출고 후", "shipping duration", "shipping_duration", "delivery days", "delivery_days"),
    "discount_rate": ("할인율", "할인", "쿠폰", "discount rate", "discount_rate", "coupon"),
    "minimum_order": ("최소 주문", "주문 금액", "이상 주문", "이상 구매", "minimum order", "minimum_order", "min order", "min_order"),
    "price": ("판매가", "상품가", "가격", "price", "sale price", "sale_price"),
    "refund_amount": ("환불 금액", "전액 환불", "부분 환불", "refund amount", "refund_amount"),
    "stock": ("재고", "수량", "품절", "재입고", "stock", "quantity"),
}

STATE_PATTERNS = [
    ("not_shipped", re.compile(r"미발송|발송\s*전|출고\s*전|발송되지\s*않|출고되지\s*않|발송\s*완료.{0,6}아니|출고\s*완료.{0,6}아니|상품\s*준비\s*중|배송\s*준비\s*중|\bNOT_SHIPPED\b|\bUNFULFILLED\b|\bPREPARING\b|\bREADY\b|\bPAID\b", re.I)),
    ("shipped", re.compile(r"발송\s*완료|출고\s*완료|발송됐|출고됐|발송되었|출고되었|\bSHIPPED\b", re.I)),
    ("in_transit", re.compile(r"배송\s*중|운송\s*중|\bIN_TRANSIT\b", re.I)),
    ("delivered", re.compile(r"배송\s*완료|배달\s*완료|\bDELIVERED\b", re.I)),
]
STATE_LABELS = {
    "not_shipped": "미발송",
    "shipped": "발송 완료",
    "in_transit": "배송 중",
    "delivered": "배송 완료",
}


@dataclass(frozen=True)
class NumberFact:
    value: float
    unit: str
    raw: str
    role: str


def _now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _unwrap_list(value, keys):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), list):
                return value[key]
    raise ValueError("배열 데이터를 찾을 수 없습니다")


def _load_products(products):
    if isinstance(products, (str, os.PathLike)):
        path = os.fspath(products)
        with open(path, encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows, path
    if isinstance(products, list):
        return products, "products.csv"
    if isinstance(products, dict):
        rows = _unwrap_list(products, ("products", "rows", "data"))
        return rows, "products.csv"
    raise TypeError("products는 CSV 경로나 배열이어야 합니다")


def _normalize_keywords(value):
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[,|/]", value) if part.strip()]
    if isinstance(value, list):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _policy_truths(policies):
    truths = []
    for policy in policies:
        if not isinstance(policy, dict) or not str(policy.get("fact", "")).strip():
            continue
        topic = str(policy.get("topic", "")).strip()
        keywords = _normalize_keywords(policy.get("keywords"))
        source = str(policy.get("source") or "정책 원장")
        fact = str(policy["fact"]).strip()
        truths.append({
            "kind": "policy",
            "topic": topic,
            "keywords": [topic] + keywords if topic else keywords,
            "fact": fact,
            "searchText": f"{topic} {fact}",
            "source": f"{source}: {fact}",
        })
    return truths


def _identity_values(row):
    values = []
    for key, value in row.items():
        key_text = str(key or "").lower().replace("_", "")
        value_text = str(value or "").strip()
        if not value_text:
            continue
        if any(token in key_text for token in (
            "sku", "productid", "productno", "productcode", "productname",
            "상품코드", "상품번호", "상품명", "품목코드", "품번",
        )):
            values.append(value_text)
    return values


def _product_truths(products, context):
    rows, source_path = _load_products(products)
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        identities = _identity_values(row)
        if identities and any(value in context for value in identities):
            selected.append(row)
    if not selected and len(rows) == 1 and isinstance(rows[0], dict):
        selected = rows

    truths = []
    for row in selected:
        identities = _identity_values(row)
        identity = identities[0] if identities else "상품"
        for field, value in row.items():
            field_text = str(field or "").strip()
            value_text = str(value or "").strip()
            if not field_text or not value_text or value_text in identities:
                continue
            fact = f"{field_text}: {value_text}"
            truths.append({
                "kind": "product",
                "topic": field_text,
                "keywords": [field_text],
                "fact": fact,
                "searchText": fact,
                "source": f"{source_path} > {identity} > {fact}",
            })
    return truths


def _sentences(text):
    return [part.strip() for part in re.split(r"(?<=[.!?])\s*|\n+", text) if part.strip()]


def _agent_candidates(transcript):
    candidates = []
    previous_customer = ""
    for message in transcript:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        text = clean_text(message.get("text", ""))
        if role == "customer":
            previous_customer = text
            continue
        if role != "agent":
            continue
        for sentence in _sentences(text):
            if CANDIDATE_RE.search(sentence):
                candidates.append({"claim": sentence, "context": f"{previous_customer} {sentence}".strip()})
    return candidates


def _role_for_number(text, unit):
    compact = re.sub(r"\s+", " ", text).lower()
    if unit in ("%", "퍼센트") and any(term in compact for term in ANCHOR_TERMS["discount_rate"]):
        return "discount_rate"
    if unit in ("원", "만원"):
        if any(term in compact for term in ANCHOR_TERMS["shipping_fee"]):
            return "shipping_fee"
        if (
            "최소" in compact or "이상 주문" in compact or "이상 구매" in compact
            or "minimum" in compact or "min_order" in compact
            or (
                any(cue in compact for cue in ("이상", "초과", "부터"))
                and ("주문" in compact or "구매" in compact or "쿠폰" in compact)
            )
        ):
            return "minimum_order"
        if "더 담" in compact or "추가하면" in compact:
            return "topup"
        if any(term in compact for term in ANCHOR_TERMS["refund_amount"]):
            return "refund_amount"
        if any(term in compact for term in ANCHOR_TERMS["price"]):
            return "price"
        if "할인" in compact or "쿠폰" in compact:
            return "discount_amount"
    if unit == "시" and any(term in compact for term in ANCHOR_TERMS["shipping_cutoff"]):
        return "shipping_cutoff"
    if unit in ("일", "주", "개월", "시간", "분"):
        if any(term in compact for term in ANCHOR_TERMS["return_deadline"]):
            return "return_deadline"
        if any(term in compact for term in ANCHOR_TERMS["refund_duration"]):
            return "refund_duration"
        if any(term in compact for term in ANCHOR_TERMS["shipping_duration"]):
            return "shipping_duration"
    if unit in ("개", "회") and any(term in compact for term in ANCHOR_TERMS["stock"]):
        return "stock"
    return "generic"


def _number_facts(text):
    facts = []
    for match in NUMBER_RE.finditer(text):
        unit = match.group("unit") or ""
        raw_value = match.group("number").replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:
            continue
        normalized_unit = unit
        if unit == "만원":
            value *= 10000
            normalized_unit = "원"
        elif unit == "퍼센트":
            normalized_unit = "%"
        elif not unit:
            lowered = text.lower()
            if re.search(r"(?:days?|_days?)", lowered):
                normalized_unit = "일"
                unit = "일"
            elif re.search(r"(?:hours?|_hours?)", lowered):
                normalized_unit = "시간"
                unit = "시간"
            elif re.search(r"(?:cutoff|마감).{0,18}(?:hour|_at|time)", lowered):
                normalized_unit = "시"
                unit = "시"
            elif any(term in lowered for term in ("fee", "price", "amount", "배송비", "판매가", "가격", "금액")):
                normalized_unit = "원"
                unit = "원"
            elif any(term in lowered for term in ("discount_rate", "percent", "할인율")):
                normalized_unit = "%"
                unit = "%"
        facts.append(NumberFact(value, normalized_unit, match.group(0), _role_for_number(text, unit)))
    return facts


def _truth_relevant(truth, context, role=None):
    if truth["kind"] == "product":
        if role and role != "generic":
            if not any(number.role == role for number in _number_facts(truth["searchText"])):
                return False
            truth_text = truth["searchText"].lower()
            context_text = context.lower()
            scopes = (
                (("반품", "return"), ("반품", "return")),
                (("교환", "exchange"), ("교환", "exchange")),
                (("해외", "overseas", "international"), ("해외", "overseas", "international")),
            )
            matched_scopes = []
            for truth_terms, context_terms in scopes:
                if any(term in truth_text for term in truth_terms):
                    matched_scopes.append(context_terms)
            if matched_scopes:
                return any(
                    term in context_text
                    for context_terms in matched_scopes
                    for term in context_terms
                )
            if role == "shipping_fee" and any(term in context_text for term in ("반품", "return", "교환", "exchange")):
                return False
            return True
        return any(keyword and keyword in context for keyword in truth["keywords"])
    return any(keyword and keyword in context for keyword in truth["keywords"])


def _detect_state(text):
    for state, pattern in STATE_PATTERNS:
        if pattern.search(text):
            return state
    return None


def _make_violation(kind, claim, truth, evidence, severity):
    return {
        "type": kind,
        "typeLabel": TYPE_LABELS[kind],
        "botClaim": clean_text(claim),
        "sourceOfTruth": clean_text(truth["source"]),
        "evidence": clean_text(evidence),
        "severity": severity,
    }


def _truth_expectation(matches):
    if not matches:
        return None
    grouped = {}
    truth_by_source = {}
    for truth, number in matches:
        source = truth["source"]
        grouped.setdefault(source, set()).add((number.value, number.unit))
        truth_by_source[source] = truth
    expected_sets = list(grouped.values())
    if any(values != expected_sets[0] for values in expected_sets[1:]):
        return None
    source = next(iter(grouped))
    return expected_sets[0], truth_by_source[source]


def _audit_shipping_state(candidates, truths):
    violations = []
    for candidate in candidates:
        claim_state = _detect_state(candidate["claim"])
        if not claim_state:
            continue
        matches = []
        for truth in truths:
            truth_state = _detect_state(truth["searchText"])
            if truth["kind"] != "product" and not _truth_relevant(truth, candidate["context"]):
                continue
            if truth["kind"] == "product" and truth_state:
                field = truth["topic"].lower()
                if not any(term in field for term in (
                    "status", "state", "shipping", "delivery", "상태", "배송", "발송", "출고", "주문",
                )):
                    continue
            if truth_state:
                matches.append((truth, truth_state))
        truth_states = {state for _, state in matches}
        if len(truth_states) != 1 or claim_state in truth_states:
            continue
        truth, truth_state = matches[0]
        evidence = (
            f"원장 상태는 {STATE_LABELS[truth_state]}이지만 "
            f"봇은 {STATE_LABELS[claim_state]}라고 안내했습니다."
        )
        violations.append(_make_violation(
            "shipping_state_false", candidate["claim"], truth, evidence, "high"
        ))
    return violations


def _positive_commitment(text, word):
    index = text.find(word)
    if index < 0:
        return False
    nearby = text[max(0, index - 10):index + 28]
    if re.search(r"아니|않|불가|어렵|확인|여부|보장할\s*수\s*없", nearby):
        return False
    patterns = {
        "무료": r"무료\s*(?:입니다|예요|이에요|로|반품|교환|배송|처리|가능)",
        "보장": r"보장\s*(?:합니다|됩니다|해|할\s*수\s*있)",
        "무조건": r"무조건",
        "즉시": r"즉시.{0,18}(?:처리|완료|환불|발송|출고|배송|가능|됩니다|해\s*드리)",
    }
    return bool(re.search(patterns.get(word, re.escape(word)), text))


def _audit_overpromise(candidates, truths):
    violations = []
    for candidate in candidates:
        claim = candidate["claim"]
        relevant = [truth for truth in truths if _truth_relevant(truth, candidate["context"])]

        if _positive_commitment(claim, "무료"):
            fee_truths = []
            for truth in truths:
                if truth["kind"] == "product" and not _truth_relevant(truth, candidate["context"], "shipping_fee"):
                    continue
                if truth["kind"] != "product" and truth not in relevant:
                    continue
                numbers = [number for number in _number_facts(truth["searchText"]) if number.role == "shipping_fee"]
                if any(number.value > 0 for number in numbers):
                    fee_truths.append(truth)
            if fee_truths:
                violations.append(_make_violation(
                    "overpromise", claim, fee_truths[0],
                    "원장에는 고객 부담 비용이 있지만 봇은 무료라고 안내했습니다.", "high"
                ))

        if _positive_commitment(claim, "보장") or _positive_commitment(claim, "무조건"):
            denied = next((truth for truth in relevant if re.search(
                r"보장하지\s*않|보장\s*불가|확정되지\s*않|확정\s*불가|상황에\s*따라", truth["searchText"]
            )), None)
            if denied:
                violations.append(_make_violation(
                    "overpromise", claim, denied,
                    "원장은 결과를 확정하지 않지만 봇은 결과를 보장했습니다.", "high"
                ))

        if _positive_commitment(claim, "즉시"):
            duration_matches = []
            for truth in truths:
                if truth["kind"] == "product" and not any(
                    _truth_relevant(truth, candidate["context"], role)
                    for role in ("refund_duration", "shipping_duration")
                ):
                    continue
                if truth["kind"] != "product" and truth not in relevant:
                    continue
                for number in _number_facts(truth["searchText"]):
                    if number.role in ("refund_duration", "shipping_duration") and number.value > 0:
                        duration_matches.append(truth)
            if duration_matches:
                violations.append(_make_violation(
                    "overpromise", claim, duration_matches[0],
                    "원장에는 처리 기간이 있지만 봇은 즉시 처리된다고 안내했습니다.", "medium"
                ))
    return violations


def _audit_unauthorized_action(candidates, truths):
    violations = []
    for candidate in candidates:
        match = ACTION_CLAIM_RE.search(candidate["claim"])
        if not match:
            continue
        if "접수" in candidate["claim"] and not re.search(r"처리|환불\s*완료|취소\s*완료", candidate["claim"]):
            continue
        action = re.sub(r"\s+", "", match.group("action"))
        action_key = action.replace("주문", "")
        action_terms = {
            "환불": ("환불", "refund"),
            "취소": ("취소", "cancel"),
            "교환": ("교환", "exchange"),
            "반품": ("반품", "return"),
            "쿠폰": ("쿠폰", "coupon"),
            "할인": ("할인", "discount"),
        }.get(action_key, (action_key,))
        denied = next((
            truth for truth in truths
            if (truth["kind"] == "product" or _truth_relevant(truth, candidate["context"]))
            and any(term in re.sub(r"\s+", "", truth["searchText"].lower()) for term in action_terms)
            and AUTHORITY_DENIAL_RE.search(truth["searchText"])
        ), None)
        if denied:
            violations.append(_make_violation(
                "unauthorized_action", candidate["claim"], denied,
                "원장에는 별도 확인이나 승인이 필요하지만 봇은 실행을 약속하거나 완료했다고 주장했습니다.",
                "high",
            ))
    return violations


def _audit_numeric_fabrication(candidates, truths):
    violations = []
    high_roles = {
        "shipping_fee", "return_deadline", "discount_rate", "minimum_order",
        "price", "refund_amount", "discount_amount",
    }
    for candidate in candidates:
        for claim_number in _number_facts(candidate["claim"]):
            if claim_number.role in ("generic", "topup"):
                continue
            matches = []
            for truth in truths:
                if not _truth_relevant(truth, candidate["context"], claim_number.role):
                    continue
                for truth_number in _number_facts(truth["searchText"]):
                    if truth_number.role == claim_number.role and truth_number.unit == claim_number.unit:
                        matches.append((truth, truth_number))
            expectation = _truth_expectation(matches)
            if not expectation:
                continue
            expected_values, truth = expectation
            if (claim_number.value, claim_number.unit) in expected_values:
                continue
            severity = "high" if claim_number.role in high_roles else "medium"
            expected_text = " 또는 ".join(
                f"{value:g}{unit}" for value, unit in sorted(expected_values)
            )
            evidence = (
                f"원장 값은 {expected_text}이지만 "
                f"봇은 {claim_number.value:g}{claim_number.unit}이라고 안내했습니다."
            )
            violations.append(_make_violation(
                "policy_fabrication", candidate["claim"], truth, evidence, severity
            ))
    return violations


def _dedupe_violations(violations):
    seen = set()
    result = []
    for violation in violations:
        key = (violation["type"], violation["botClaim"], violation["sourceOfTruth"])
        if key in seen:
            continue
        seen.add(key)
        result.append(violation)
    return result


def audit_transcript(case, transcript, policies, products):
    """명시적 원장 모순만 네 가지 감사 유형으로 반환한다."""
    context = json.dumps({"case": case, "transcript": transcript}, ensure_ascii=False)
    truths = _policy_truths(policies) + _product_truths(products, context)
    candidates = _agent_candidates(transcript)
    violations = []
    violations.extend(_audit_shipping_state(candidates, truths))
    violations.extend(_audit_overpromise(candidates, truths))
    violations.extend(_audit_unauthorized_action(candidates, truths))
    violations.extend(_audit_numeric_fabrication(candidates, truths))
    return _dedupe_violations(violations)


def _one_sentence(value):
    text = re.sub(r"\s+", " ", clean_text(value))
    match = re.search(r"(?<!\d)[.!?](?!\d)", text)
    if match:
        text = text[:match.end()]
    if len(text) > 120:
        text = text[:119].rstrip() + "."
    return text or "평가 근거가 제공되지 않았습니다."


def _judge(case, transcript):
    prompt = """다음 AI 상담이 성공 기준을 달성했는지 평가하라.

[성공 기준]
{}

[상담 기록]
{}

다음 JSON 객체를 출력하라.
{{"resolved": true 또는 false, "cxScore": 1부터 5 사이의 실수, "judgeReason": "한국어 한 문장"}}

resolved는 고객 목표와 성공 기준의 핵심 항목이 충족됐을 때만 true다.
cxScore는 정확성, 명료성, 친절성을 함께 평가한다.
judgeReason은 짧은 한국어 한 문장으로 쓴다.
judgeReason에 엠대시, 엔대시, 중간점, 이모지, 과장어를 쓰지 않는다.""".format(
        case.get("successCriteria", ""),
        json.dumps(transcript, ensure_ascii=False, indent=2),
    )
    result = llm.ask_json(
        prompt,
        system="주어진 성공 기준과 상담 기록만 근거로 보수적으로 판정한다.",
    )
    if not isinstance(result, dict):
        raise ValueError("LLM 채점 결과가 객체가 아닙니다")
    if not isinstance(result.get("resolved"), bool):
        raise ValueError("resolved가 불리언이 아닙니다")
    if not isinstance(result.get("judgeReason"), str):
        raise ValueError("judgeReason이 문자열이 아닙니다")
    try:
        cx_score = float(result["cxScore"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("cxScore가 숫자가 아닙니다") from exc
    if isinstance(result.get("cxScore"), bool) or not 1.0 <= cx_score <= 5.0:
        raise ValueError("cxScore가 허용 범위를 벗어났습니다")
    return result["resolved"], round(cx_score, 1), _one_sentence(result.get("judgeReason"))


def score_case(case, transcript, policies, products):
    """대화 하나를 감사하고 LLM으로 해결 여부와 고객 경험을 채점한다."""
    violations = audit_transcript(case, transcript, policies, products)
    resolved, cx_score, judge_reason = _judge(case, transcript)
    severities = {violation["severity"] for violation in violations}
    if "high" in severities or not resolved:
        outcome = "fail"
    elif "medium" in severities or cx_score < 3.5:
        outcome = "warn"
    else:
        outcome = "pass"
    return {
        "caseId": str(case.get("id", "")),
        "outcome": outcome,
        "resolved": resolved,
        "cxScore": cx_score,
        "judgeReason": judge_reason,
        "audit": {"violations": violations},
        "transcript": transcript,
    }


def _error_result(case, exc):
    return {
        "caseId": str(case.get("id", "")) if isinstance(case, dict) else "",
        "outcome": "error",
        "resolved": False,
        "cxScore": 1.0,
        "judgeReason": "실행 오류로 채점을 완료하지 못했습니다.",
        "audit": {"violations": []},
        "transcript": [],
        "error": type(exc).__name__,
    }


def run_cases(cases, knowledge, policies, products, label, run_id, max_customer_turns=3):
    """여섯 개 작업자로 케이스를 병렬 실행하고 실행 단위 결과를 만든다."""
    started_at = _now_iso()

    def run_one(case):
        try:
            transcript = simulate_case(case, knowledge, max_customer_turns=max_customer_turns)
            return score_case(case, transcript, policies, products)
        except Exception as exc:
            return _error_result(case, exc)

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(run_one, cases))

    case_count = len(results)
    counts = {name: sum(result["outcome"] == name for result in results)
              for name in ("pass", "warn", "fail", "error")}
    resolved_count = sum(result.get("resolved") is True for result in results)
    violation_count = sum(
        len(result.get("audit", {}).get("violations", [])) for result in results
    )
    return {
        "runId": str(run_id),
        "label": str(label),
        "startedAt": started_at,
        "settingsSnapshot": {"articleCount": len(knowledge), "changedArticles": []},
        "summary": {
            "caseCount": case_count,
            "resolutionRate": round(resolved_count / case_count, 3) if case_count else 0.0,
            "passCount": counts["pass"],
            "warnCount": counts["warn"],
            "failCount": counts["fail"],
            "errorCount": counts["error"],
            "violationCount": violation_count,
        },
        "results": results,
    }


def _selftest():
    knowledge = [
        {
            "id": "KA-TEST-01",
            "title": "반품 안내",
            "body": "단순변심 반품은 수령 후 7일 이내 가능합니다. 반품 배송비 3,000원은 고객 부담입니다. 마이페이지 주문 내역에서 접수합니다.",
        },
        {
            "id": "KA-TEST-02",
            "title": "배송 안내",
            "body": "평일 오후 2시 이전 결제 건은 당일 출고합니다. 출고 후 배송에는 보통 1일부터 2일이 걸립니다.",
        },
    ]
    policies = [
        {
            "topic": "단순변심 반품",
            "keywords": ["반품", "배송비", "수령 후"],
            "fact": "수령 후 7일 이내 가능하며 반품 배송비 3,000원은 고객 부담",
            "source": "SELFTEST SYNTHETIC 정책 원장",
        },
        {
            "topic": "당일 출고",
            "keywords": ["배송", "출고", "오후 2시"],
            "fact": "평일 오후 2시 이전 결제 건만 당일 출고",
            "source": "SELFTEST SYNTHETIC 정책 원장",
        },
    ]
    cases = [{
        "id": "C-SELFTEST",
        "cluster": "반품",
        "goal": "단순변심 반품 기한과 비용, 접수 방법을 확인한다",
        "successCriteria": "수령 후 7일 이내, 배송비 3,000원 고객 부담, 마이페이지 접수를 모두 안내하면 성공",
        "persona": {
            "name": "테스트 고객",
            "traits": "꼼꼼함, 짧은 문장",
            "situation": "SELFTEST SYNTHETIC, 3일 전 에코백 GB-TEST-01을 수령하고 단순변심 반품을 원함",
        },
        "synthetic": True,
    }]

    with tempfile.TemporaryDirectory(prefix="alf-gate-selftest-") as temp_dir:
        products_path = os.path.join(temp_dir, "products.csv")
        with open(products_path, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["상품코드", "상품명", "판매가", "교환 반품 안내"])
            writer.writeheader()
            writer.writerow({
                "상품코드": "GB-TEST-01",
                "상품명": "SELFTEST SYNTHETIC 에코백",
                "판매가": "29000원",
                "교환 반품 안내": "단순변심 반품은 수령 후 7일 이내, 배송비 3,000원 고객 부담",
            })
        run = run_cases(
            cases, knowledge, policies, products_path,
            "SELFTEST SYNTHETIC", "run-selftest", max_customer_turns=1,
        )

    result = run["results"][0]
    if result["outcome"] == "error":
        raise RuntimeError(f"셀프테스트 실패: {result.get('error', 'unknown')}")
    required = {"caseId", "outcome", "resolved", "cxScore", "judgeReason", "audit", "transcript"}
    if not required.issubset(result):
        raise RuntimeError("셀프테스트 결과 스키마가 맞지 않습니다")
    print(json.dumps({
        "selftest": "ok",
        "outcome": result["outcome"],
        "resolved": result["resolved"],
        "cxScore": result["cxScore"],
        "violations": len(result["audit"]["violations"]),
        "turns": len(result["transcript"]),
    }, ensure_ascii=False))


def _save_json(value, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="AI 상담 시뮬레이션과 채점 실행기")
    parser.add_argument("--cases")
    parser.add_argument("--knowledge")
    parser.add_argument("--policies")
    parser.add_argument("--products")
    parser.add_argument("--label")
    parser.add_argument("--run-id")
    parser.add_argument("--out")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)

    if args.selftest:
        _selftest()
        return

    required = ("cases", "knowledge", "policies", "products", "label", "run_id", "out")
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        parser.error("필수 인자가 없습니다: " + ", ".join(missing))

    cases = _unwrap_list(_load_json(args.cases), ("cases",))
    knowledge = _unwrap_list(_load_json(args.knowledge), ("knowledge", "articles"))
    policies = _unwrap_list(_load_json(args.policies), ("policies",))
    run = run_cases(cases, knowledge, policies, args.products, args.label, args.run_id)
    _save_json(run, args.out)
    summary = run["summary"]
    print(
        f"실행 완료: cases={summary['caseCount']} pass={summary['passCount']} "
        f"warn={summary['warnCount']} fail={summary['failCount']} error={summary['errorCount']}"
    )


if __name__ == "__main__":
    main()
