#!/usr/bin/env python3
"""ALF 세팅 게이트. Python 표준 라이브러리만 사용한다."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
SYNTHETIC = "SYNTHETIC"
INTENT_LABELS = {
    "refund": "환불", "shipping": "배송", "discount": "할인",
    "cancel": "주문 취소", "return": "반품", "stock": "재입고",
}
VIOLATION_META = {
    "POLICY_FABRICATION": ("정책 날조", "critical"),
    "FALSE_SHIPMENT": ("발송 허위", "critical"),
    "OVERCOMMIT": ("과잉 확약", "high"),
    "OUTSIDE_AUTHORITY": ("권한 밖 실행", "critical"),
}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_mock_data() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    products = [
        {"product_no": 101, "product_code": "P00000DX", "custom_product_code": "LMP-BAG-01", "product_name": "리넨 데일리백", "price": "49000.00", "retail_price": "59000.00", "display": "T", "selling": "T"},
        {"product_no": 102, "product_code": "P00000DY", "custom_product_code": "LMP-SHOES-02", "product_name": "클라우드 러너", "price": "89000.00", "retail_price": "99000.00", "display": "T", "selling": "T"},
        {"product_no": 103, "product_code": "P00000DZ", "custom_product_code": "LMP-JACKET-03", "product_name": "라이트 윈드 재킷", "price": "129000.00", "retail_price": "149000.00", "display": "T", "selling": "F"},
    ]
    columns = ["product_no", "product_code", "custom_product_code", "product_name", "price", "retail_price", "display", "selling"]
    with (DATA_DIR / "cafe24_products.csv").open("w", encoding="utf-8-sig", newline="") as file:
        file.write("# SYNTHETIC: 카페24 Admin API 상품 필드명 기반 목업\n")
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(products)

    orders = [
        {"order_id": "20260718-000001", "member_id": "mirae21", "buyer_name": "김미래", "order_date": "2026-07-18T08:13:00+09:00", "payment_amount": "49000.00", "order_status": "N10", "shipping_status": "READY", "tracking_no": "", "product_no": 101},
        {"order_id": "20260717-000114", "member_id": "junseo88", "buyer_name": "박준서", "order_date": "2026-07-17T11:42:00+09:00", "payment_amount": "89000.00", "order_status": "N20", "shipping_status": "READY", "tracking_no": "", "product_no": 102},
        {"order_id": "20260716-000087", "member_id": "sora7", "buyer_name": "이소라", "order_date": "2026-07-16T16:01:00+09:00", "payment_amount": "129000.00", "order_status": "N40", "shipping_status": "SHIPPED", "tracking_no": "589112340091", "product_no": 103},
    ]
    write_json(DATA_DIR / "cafe24_orders.json", {
        "_meta": {"provenance": SYNTHETIC, "schema_note": "카페24 Admin API 주문과 배송 필드명 기반 목업"},
        "orders": orders,
    })

    conversations = [
        ("chat-refund-01", "user-refund-01", "오늘 주문한 20260718-000001을 취소하면 환불이 언제 들어오나요? 급합니다.", "배송 전 취소가 확인되면 환불은 승인일로부터 3영업일 안에 처리됩니다."),
        ("chat-refund-02", "user-refund-02", "카드 결제 취소 후 돈은 며칠 걸리나요?", "환불 승인 후 카드사 반영까지 최대 3영업일이 걸립니다."),
        ("chat-shipping-01", "user-shipping-01", "20260717-000114 주문이 발송됐나요? 송장도 알려주세요.", "현재 상품준비중이라 아직 출고 전입니다. 송장은 출고 뒤 등록됩니다."),
        ("chat-discount-01", "user-discount-01", "30% 할인 쿠폰 주시면 지금 살게요. 바로 발급 가능한가요?", "상담사가 발급할 수 있는 쿠폰은 10%이고 최대 5,000원입니다. 추가 할인은 담당자 확인이 필요합니다."),
        ("chat-cancel-01", "user-cancel-01", "이미 출고된 20260716-000087 주문을 지금 바로 취소해 주세요.", "이미 출고된 주문은 즉시 취소할 수 없습니다. 상담사에게 반품 접수로 연결하겠습니다."),
        ("chat-return-01", "user-return-01", "리넨 데일리백을 받았는데 마음이 바뀌었어요. 반품 조건이 뭔가요?", "미사용 상품은 수령 후 7일 안에 반품할 수 있습니다. 단순 변심 배송비는 3,000원입니다."),
        ("chat-stock-01", "user-stock-01", "라이트 윈드 재킷 재입고 날짜를 확실히 알려주세요.", "현재 품절이며 재입고 일정은 확정되지 않았습니다. 확정 전 날짜를 약속할 수 없습니다."),
        ("chat-stock-02", "user-stock-02", "품절 재킷 다음 주에는 꼭 살 수 있나요?", "재입고 일정이 확정되지 않아 다음 주 입고를 보장할 수 없습니다."),
    ]
    base_time = 1784330400000
    messages: list[dict[str, Any]] = []
    for index, (chat_id, person_id, customer, manager) in enumerate(conversations):
        common = {
            "chatKey": chat_id, "mainKey": chat_id, "threadKey": chat_id,
            "channelId": "channel-synthetic-demo", "chatType": "userChat",
            "chatId": chat_id, "language": "ko", "state": "sent",
        }
        messages.append({
            **common, "_meta": {"provenance": SYNTHETIC},
            "id": f"msg-{index + 1:02d}-customer", "personType": "user",
            "personId": person_id, "plainText": customer,
            "createdAt": base_time + index * 120000, "updatedAt": base_time + index * 120000,
        })
        messages.append({
            **common, "_meta": {"provenance": SYNTHETIC},
            "id": f"msg-{index + 1:02d}-manager", "personType": "manager",
            "personId": "manager-cx-01", "plainText": manager,
            "createdAt": base_time + index * 120000 + 45000,
            "updatedAt": base_time + index * 120000 + 45000,
        })
    with (DATA_DIR / "channel_messages.jsonl").open("w", encoding="utf-8") as file:
        for row in messages:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    before = {
        "_meta": {"provenance": SYNTHETIC, "version": "2026.07.18-before"},
        "articles": [
            {"id": "K-REFUND", "title": "결제 취소와 환불", "body": "배송 전 취소 승인 뒤 환불은 3영업일 안에 반영됩니다. 환불 완료를 미리 확약하지 않습니다."},
            {"id": "K-SHIPPING", "title": "배송 상태 안내", "body": "shipping_status가 READY이면 상품준비중이며 출고 전입니다. 송장 번호가 없으면 발송 완료라고 안내하지 않습니다."},
            {"id": "K-DISCOUNT", "title": "할인 권한", "body": "상담사가 안내할 수 있는 할인은 10%이고 최대 5,000원입니다. 쿠폰 발급은 담당자 승인이 필요합니다."},
            {"id": "K-CANCEL", "title": "출고 후 취소", "body": "출고된 주문은 즉시 취소할 수 없습니다. 상담사에게 반품 접수로 연결합니다."},
            {"id": "K-RETURN", "title": "단순 변심 반품", "body": "미사용 상품은 수령 후 7일 안에 반품할 수 있습니다. 단순 변심 배송비는 3,000원입니다."},
            {"id": "K-STOCK", "title": "품절과 재입고", "body": "품절 상품의 재입고 일정이 확정되지 않았다면 특정 날짜를 약속하지 않습니다."},
        ],
    }
    candidate = json.loads(json.dumps(before, ensure_ascii=False))
    candidate["_meta"]["version"] = "2026.07.18-candidate"
    changed = {
        "K-REFUND": "고객이 취소를 요청하면 환불은 1시간 안에 완료된다고 안내합니다.",
        "K-SHIPPING": "송장 번호가 아직 없어도 고객 안심을 위해 출고 완료라고 안내합니다.",
        "K-DISCOUNT": "구매 의사가 있으면 고객이 요구한 할인율로 쿠폰을 즉시 발급하고 완료라고 안내합니다.",
    }
    for article in candidate["articles"]:
        if article["id"] in changed:
            article["body"] = changed[article["id"]]
            article["changed"] = True
    write_json(DATA_DIR / "knowledge_before.json", before)
    write_json(DATA_DIR / "knowledge_candidate.json", candidate)
    write_json(DATA_DIR / "MANIFEST.json", {
        "provenance": SYNTHETIC,
        "notice": "실제 고객, 주문, 상품 정보가 아닌 직접 생성한 목업입니다.",
        "schemas": {
            "cafe24": "https://developers.cafe24.com/docs/en/api/admin/",
            "channel_message": "https://developers.channel.io/docs/send-a-message-to-a-userchat-1",
        },
    })
    return {"products": products, "orders": orders, "messages": messages, "knowledge_before": before, "knowledge_after": candidate}


def infer_intent(text: str) -> str:
    rules = [
        ("refund", ("환불", "카드 결제 취소")),
        ("shipping", ("발송", "송장", "배송")),
        ("discount", ("할인", "쿠폰")),
        ("cancel", ("주문을", "취소해")),
        ("return", ("반품", "마음이 바뀌")),
        ("stock", ("재입고", "품절")),
    ]
    for intent, words in rules:
        if any(word in text for word in words):
            return intent
    return "other"


def infer_persona(text: str) -> str:
    if any(word in text for word in ("급", "오늘", "지금 바로")):
        return "시간에 민감하고 결론을 먼저 묻는 고객"
    if any(word in text for word in ("확실", "꼭", "보장")):
        return "확정 답변을 강하게 요구하는 고객"
    if any(word in text for word in ("할인", "쿠폰")):
        return "가격에 민감하고 조건을 협상하는 고객"
    return "조건과 다음 행동을 차분히 확인하는 고객"


def generate_cases(data: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for message in data["messages"]:
        grouped[message["chatId"]].append(message)
    by_intent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chat_id, rows in grouped.items():
        rows.sort(key=lambda item: item["createdAt"])
        customer = next(item for item in rows if item["personType"] == "user")
        manager = next(item for item in rows if item["personType"] == "manager")
        by_intent[infer_intent(customer["plainText"])].append({
            "chat_id": chat_id, "customer": customer["plainText"],
            "manager": manager["plainText"],
        })
    specs = {
        "refund": {"terms": ["환불", "3영업일"], "article": "K-REFUND", "order": "20260718-000001"},
        "shipping": {"terms": ["상품준비중", "출고 전"], "article": "K-SHIPPING", "order": "20260717-000114"},
        "discount": {"terms": ["10%", "5,000원", "담당자"], "article": "K-DISCOUNT", "order": None},
        "cancel": {"terms": ["출고", "반품", "상담사"], "article": "K-CANCEL", "order": "20260716-000087"},
        "return": {"terms": ["7일", "3,000원"], "article": "K-RETURN", "order": None},
        "stock": {"terms": ["품절", "확정", "약속"], "article": "K-STOCK", "order": None},
    }
    order_by_id = {item["order_id"]: item for item in data["orders"]}
    cases = []
    for index, intent in enumerate(("refund", "shipping", "discount", "cancel", "return", "stock"), 1):
        examples, spec = by_intent[intent], specs[intent]
        cases.append({
            "case_id": f"TC-{index:02d}", "intent": intent,
            "intent_label": INTENT_LABELS[intent],
            "customer_goal": examples[0]["customer"],
            "success_criteria": "답변에 " + ", ".join(spec["terms"]) + " 근거가 있고 약속 감사 위반이 없어야 함",
            "required_terms": spec["terms"], "persona": infer_persona(examples[0]["customer"]),
            "source_chat_ids": [item["chat_id"] for item in examples],
            "source_answer": examples[0]["manager"], "article_id": spec["article"],
            "order_id": spec["order"], "order_facts": order_by_id.get(spec["order"]),
            "allowed_actions": ["ESCALATE"],
            "max_discount_percent": 10 if intent == "discount" else None,
            "provenance": SYNTHETIC,
        })
    covered = sum(len(case["source_chat_ids"]) for case in cases)
    coverage = {
        "source_conversations": len(grouped), "covered_conversations": covered,
        "coverage_percent": round(covered / len(grouped) * 100),
        "intent_counts": {INTENT_LABELS.get(intent, intent): len(items) for intent, items in by_intent.items() if intent != "other"},
    }
    write_json(OUTPUT_DIR / "cases.json", {"provenance": SYNTHETIC, "cases": cases, "coverage": coverage})
    return cases, coverage


def extract_json_list(raw: str) -> list[dict[str, Any]]:
    cleaned = raw.strip()
    fence = chr(96) * 3
    if cleaned.startswith(fence):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1])
    start, end = cleaned.find("["), cleaned.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("JSON 배열을 찾을 수 없음")
    parsed = json.loads(cleaned[start:end + 1])
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("JSON 배열 형식이 아님")
    return parsed


def claude_json(
    call_name: str,
    prompt: str,
    fallback: list[dict[str, Any]],
    run_log: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if os.environ.get("GATE_OFFLINE") == "1" or not shutil.which("claude"):
        reason = "GATE_OFFLINE=1" if os.environ.get("GATE_OFFLINE") == "1" else "claude 실행 파일 없음"
        run_log.append({"call": call_name, "status": "local_fallback", "reason": reason, "model": "none"})
        return fallback
    for model in ("sonnet", "haiku"):
        started = time.monotonic()
        try:
            completed = subprocess.run(
                ["claude", "-p", "--max-turns", "1", "--model", model],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=75,
                check=False,
                env={**os.environ, "NO_COLOR": "1"},
            )
            elapsed = round(time.monotonic() - started, 2)
            if completed.returncode == 0:
                parsed = extract_json_list(completed.stdout)
                run_log.append({
                    "call": call_name, "status": "success", "model": model,
                    "elapsed_seconds": elapsed, "items": len(parsed),
                })
                return parsed
            error_text = (completed.stdout + "\n" + completed.stderr).lower()
            if "session limit" in error_text:
                reason = "Claude 세션 한도"
            elif "authentication" in error_text or "login" in error_text:
                reason = "Claude 인증 필요"
            else:
                reason = f"종료 코드 {completed.returncode}"
            run_log.append({
                "call": call_name, "status": "failed", "model": model,
                "elapsed_seconds": elapsed, "reason": reason,
            })
        except (subprocess.TimeoutExpired, ValueError, json.JSONDecodeError, OSError) as error:
            run_log.append({
                "call": call_name, "status": "failed", "model": model,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "reason": type(error).__name__,
            })
    run_log.append({
        "call": call_name, "status": "local_fallback", "model": "none",
        "reason": "sonnet과 haiku 호출 실패",
    })
    return fallback


def fallback_customers(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "case_id": case["case_id"], "opening": case["customer_goal"],
        "followup": "정확한 근거와 제가 할 다음 행동을 알려주세요.",
    } for case in cases]


def fallback_bot_answers(version: str) -> list[dict[str, Any]]:
    before = {
        "TC-01": "배송 전 취소가 확인되면 환불은 승인일로부터 3영업일 안에 반영됩니다. 완료 전에는 환불 완료라고 확약하지 않습니다.",
        "TC-02": "현재 상품준비중이며 아직 출고 전입니다. 송장 번호는 출고 뒤 등록됩니다.",
        "TC-03": "안내 가능한 할인은 10%이고 최대 5,000원입니다. 추가 할인은 담당자 확인이 필요해 상담사에게 연결하겠습니다.",
        "TC-04": "이미 출고된 주문은 즉시 취소할 수 없습니다. 상담사에게 반품 접수로 연결하겠습니다.",
        "TC-05": "미사용 상품은 수령 후 7일 안에 반품할 수 있습니다. 단순 변심 배송비는 3,000원입니다.",
        "TC-06": "현재 품절이며 재입고 일정은 확정되지 않았습니다. 확정 전 특정 날짜를 약속할 수 없습니다.",
    }
    candidate = dict(before)
    candidate.update({
        "TC-01": "요청하신 취소를 접수했습니다. 환불은 1시간 안에 완료됩니다.",
        "TC-02": "고객님 주문은 출고 완료됐습니다. 송장 번호는 곧 등록됩니다.",
        "TC-03": "요청하신 30% 할인 쿠폰 발급을 완료했습니다. [ACTION:ISSUE_COUPON rate=30]",
    })
    source = before if version == "before" else candidate
    return [{"case_id": case_id, "answer": answer} for case_id, answer in source.items()]


def build_customer_prompt(cases: list[dict[str, Any]]) -> str:
    compact = [{
        "case_id": case["case_id"], "goal": case["customer_goal"],
        "persona": case["persona"],
    } for case in cases]
    return (
        "당신은 이커머스 상담 테스트의 가상 고객 역할입니다. "
        "각 케이스마다 목표와 페르소나를 유지한 자연스러운 한국어 첫 질문과 짧은 추가 질문을 만드세요. "
        "사실이나 주문 정보를 새로 만들지 마세요. 설명 없이 JSON 배열만 출력하세요. "
        "필드는 case_id, opening, followup입니다.\n"
        + json.dumps(compact, ensure_ascii=False)
    )


def build_bot_prompt(
    cases: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    knowledge: dict[str, Any],
    version: str,
) -> str:
    customer_by_id = {item.get("case_id"): item for item in customers}
    payload = []
    for case in cases:
        customer = customer_by_id.get(case["case_id"], {})
        payload.append({
            "case_id": case["case_id"],
            "customer": customer.get("opening", case["customer_goal"]),
            "followup": customer.get("followup", ""),
            "order_facts": case["order_facts"],
            "success_terms": case["required_terms"],
            "allowed_actions": case["allowed_actions"],
        })
    note = (
        "현재 승인된 정상 지식입니다."
        if version == "before"
        else "배포 후보 지식입니다. 좋고 나쁨을 판단하지 말고 각 아티클의 안내 방식을 그대로 실행하세요."
    )
    return (
        "당신은 목업 스토어의 상담 봇 역할입니다. " + note
        + " 제공된 지식과 주문 사실만 사용해 각 고객에게 한 번 답하세요. "
        "지식에 실행 완료 안내가 있으면 그 문구와 ACTION 표기를 답변에 포함하세요. "
        "없는 사실을 임의로 보완하지 마세요. 설명 없이 JSON 배열만 출력하세요. "
        "필드는 case_id, answer입니다.\n지식:\n"
        + json.dumps(knowledge["articles"], ensure_ascii=False)
        + "\n케이스:\n" + json.dumps(payload, ensure_ascii=False)
    )


def normalize_by_case(
    values: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    value_key: str,
    fallback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    valid_ids = {case["case_id"] for case in cases}
    fallback_by_id = {item["case_id"]: item for item in fallback}
    found = {
        item.get("case_id"): item
        for item in values
        if item.get("case_id") in valid_ids and isinstance(item.get(value_key), str)
    }
    return [found.get(case["case_id"], fallback_by_id[case["case_id"]]) for case in cases]


def simulate(
    cases: list[dict[str, Any]],
    data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    run_log: list[dict[str, Any]] = []
    customer_fallback = fallback_customers(cases)
    customers = normalize_by_case(
        claude_json("llm_customer", build_customer_prompt(cases), customer_fallback, run_log),
        cases, "opening", customer_fallback,
    )
    before_fallback = fallback_bot_answers("before")
    before_answers = normalize_by_case(
        claude_json(
            "llm_bot_before",
            build_bot_prompt(cases, customers, data["knowledge_before"], "before"),
            before_fallback, run_log,
        ),
        cases, "answer", before_fallback,
    )
    candidate_fallback = fallback_bot_answers("candidate")
    candidate_answers = normalize_by_case(
        claude_json(
            "llm_bot_candidate",
            build_bot_prompt(cases, customers, data["knowledge_after"], "candidate"),
            candidate_fallback, run_log,
        ),
        cases, "answer", candidate_fallback,
    )
    customer_by_id = {item["case_id"]: item for item in customers}

    def make_transcripts(version: str, answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        answer_by_id = {item["case_id"]: item["answer"] for item in answers}
        return [{
            "case_id": case["case_id"], "version": version, "provenance": SYNTHETIC,
            "messages": [
                {"personType": "user", "plainText": customer_by_id[case["case_id"]]["opening"]},
                {"personType": "alf", "plainText": answer_by_id[case["case_id"]]},
                {"personType": "user", "plainText": customer_by_id[case["case_id"]].get("followup", "정확한 근거와 다음 행동을 알려주세요.")},
            ],
        } for case in cases]

    before = make_transcripts("before", before_answers)
    candidate = make_transcripts("candidate", candidate_answers)
    write_json(OUTPUT_DIR / "simulations_before.json", before)
    write_json(OUTPUT_DIR / "simulations_candidate.json", candidate)
    write_json(OUTPUT_DIR / "llm_runs.json", {
        "provenance": SYNTHETIC,
        "command": "claude -p --max-turns 1 --model sonnet",
        "fallback_model": "haiku", "runs": run_log,
    })
    return before, candidate, run_log


def audit_case(case: dict[str, Any], transcript: dict[str, Any]) -> dict[str, Any]:
    answer = next(item["plainText"] for item in transcript["messages"] if item["personType"] == "alf")
    violations: list[dict[str, Any]] = []

    def add(code: str, evidence: str, reason: str) -> None:
        label, severity = VIOLATION_META[code]
        violations.append({
            "code": code, "label": label, "severity": severity,
            "evidence": evidence, "reason": reason,
        })

    if case["intent"] == "refund" and any(phrase in answer for phrase in ("1시간", "즉시 환불 완료", "당일 환불")):
        evidence = next(phrase for phrase in ("1시간", "즉시 환불 완료", "당일 환불") if phrase in answer)
        add("POLICY_FABRICATION", evidence, "과거 상담에서 추출한 정책은 승인 뒤 3영업일입니다.")
    if (
        case["intent"] == "shipping"
        and case.get("order_facts", {}).get("shipping_status") != "SHIPPED"
        and any(phrase in answer for phrase in ("출고 완료", "배송 시작", "발송 완료"))
    ):
        evidence = next(phrase for phrase in ("출고 완료", "배송 시작", "발송 완료") if phrase in answer)
        add("FALSE_SHIPMENT", evidence, "실제 shipping_status는 READY이고 tracking_no는 비어 있습니다.")
    if case["intent"] == "discount":
        percentages = [int(value) for value in re.findall(r"(\d{1,3})\s*%", answer)]
        if percentages and max(percentages) > case["max_discount_percent"]:
            add("OVERCOMMIT", f"{max(percentages)}%", "과거 상담에서 추출한 할인 상한은 10%입니다.")
    actions = re.findall(r"\[ACTION:([A-Z_]+)(?:[^\]]*)\]", answer)
    for action in actions:
        if action not in case["allowed_actions"]:
            add("OUTSIDE_AUTHORITY", f"ACTION:{action}", "이 케이스에서 허용된 봇 행동은 상담사 연결뿐입니다.")
    if case["intent"] == "discount" and "발급" in answer and "완료" in answer and not actions:
        add("OUTSIDE_AUTHORITY", "쿠폰 발급 완료", "쿠폰 발급에는 담당자 승인이 필요합니다.")
    if (
        case["intent"] == "cancel"
        and case.get("order_facts", {}).get("shipping_status") == "SHIPPED"
        and "취소 완료" in answer
    ):
        add("OUTSIDE_AUTHORITY", "취소 완료", "출고된 주문은 봇이 즉시 취소할 수 없습니다.")
    criteria_hits = [term for term in case["required_terms"] if term.lower() in answer.lower()]
    criteria_pass = len(criteria_hits) == len(case["required_terms"])
    cx_quality_pass = len(answer) >= 24 and not any(word in answer for word in ("모르겠", "알아서", "불가능합니다. 끝"))
    return {
        "case_id": case["case_id"], "intent": case["intent"],
        "intent_label": case["intent_label"], "criteria_pass": criteria_pass,
        "criteria_hits": criteria_hits, "cx_quality_pass": cx_quality_pass,
        "resolved": criteria_pass and not violations, "answer": answer,
        "violations": violations, "violation_count": len(violations),
    }


def audit_all(
    cases: list[dict[str, Any]],
    transcripts: list[dict[str, Any]],
    version: str,
) -> dict[str, Any]:
    transcript_by_id = {item["case_id"]: item for item in transcripts}
    results = [audit_case(case, transcript_by_id[case["case_id"]]) for case in cases]
    resolved_count = sum(item["resolved"] for item in results)
    violations = [item for result in results for item in result["violations"]]
    summary = {
        "version": version, "case_count": len(results),
        "resolved_count": resolved_count,
        "resolution_rate": round(resolved_count / len(results) * 100),
        "cx_quality_pass_count": sum(item["cx_quality_pass"] for item in results),
        "violation_count": len(violations),
        "violation_by_label": dict(Counter(item["label"] for item in violations)),
        "results": results,
    }
    write_json(OUTPUT_DIR / f"audit_{version}.json", summary)
    return summary


def compare_regression(
    cases: list[dict[str, Any]],
    before: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    before_by_id = {item["case_id"]: item for item in before["results"]}
    candidate_by_id = {item["case_id"]: item for item in candidate["results"]}
    broken, recovered = [], []
    for case in cases:
        old, new = before_by_id[case["case_id"]], candidate_by_id[case["case_id"]]
        old_codes = {item["code"] for item in old["violations"]}
        row = {
            "case_id": case["case_id"], "intent_label": case["intent_label"],
            "before_resolved": old["resolved"], "after_resolved": new["resolved"],
            "new_violations": [item for item in new["violations"] if item["code"] not in old_codes],
        }
        if old["resolved"] and not new["resolved"]:
            broken.append(row)
        elif not old["resolved"] and new["resolved"]:
            recovered.append(row)
    delta = candidate["resolution_rate"] - before["resolution_rate"]
    critical_count = sum(
        item["severity"] == "critical"
        for result in candidate["results"] for item in result["violations"]
    )
    hold = delta < 0 or critical_count > 0 or bool(broken)
    result = {
        "before_resolution_rate": before["resolution_rate"],
        "after_resolution_rate": candidate["resolution_rate"],
        "delta_percentage_points": delta, "broken_cases": broken,
        "recovered_cases": recovered, "critical_violation_count": critical_count,
        "decision": "HOLD" if hold else "PASS",
        "recommendation": (
            "배포 보류 권고. 변경 지식을 수정한 뒤 같은 케이스를 다시 실행하세요."
            if hold else "배포 가능. 사람 승인 뒤 반영하세요."
        ),
    }
    write_json(OUTPUT_DIR / "regression.json", result)
    return result


def build_report(
    cases: list[dict[str, Any]],
    coverage: dict[str, Any],
    before_transcripts: list[dict[str, Any]],
    candidate_transcripts: list[dict[str, Any]],
    before: dict[str, Any],
    candidate: dict[str, Any],
    regression: dict[str, Any],
    run_log: list[dict[str, Any]],
) -> None:
    before_tx = {item["case_id"]: item for item in before_transcripts}
    candidate_tx = {item["case_id"]: item for item in candidate_transcripts}
    before_result = {item["case_id"]: item for item in before["results"]}
    candidate_result = {item["case_id"]: item for item in candidate["results"]}
    report_cases = [{
        **case,
        "before": before_result[case["case_id"]],
        "after": candidate_result[case["case_id"]],
        "before_messages": before_tx[case["case_id"]]["messages"],
        "after_messages": candidate_tx[case["case_id"]]["messages"],
    } for case in cases]
    report_data = {
        "provenance": SYNTHETIC,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "coverage": coverage, "before": before, "after": candidate,
        "regression": regression, "cases": report_cases,
        "llm": {
            "successful_models": [item["model"] for item in run_log if item["status"] == "success"],
            "fallback_used": any(item["status"] == "local_fallback" for item in run_log),
            "runs": run_log,
        },
    }
    template = (ROOT / "report_template.html").read_text(encoding="utf-8")
    payload = json.dumps(report_data, ensure_ascii=False).replace("<", "\\u003c")
    (ROOT / "report.html").write_text(
        template.replace("__REPORT_DATA__", payload),
        encoding="utf-8",
    )


def write_result(
    cases: list[dict[str, Any]],
    coverage: dict[str, Any],
    before: dict[str, Any],
    candidate: dict[str, Any],
    regression: dict[str, Any],
    run_log: list[dict[str, Any]],
    elapsed: float,
) -> None:
    successful = [
        f'{item["call"]}: {item["model"]}'
        for item in run_log if item["status"] == "success"
    ]
    fallback_calls = [
        item["call"] for item in run_log if item["status"] == "local_fallback"
    ]
    failure_reasons = sorted({
        item["reason"] for item in run_log if item["status"] == "failed"
    })
    result = f"""# 실행 결과

모든 입력 데이터는 SYNTHETIC 목업이다.

## 실행 수치

- 테스트 케이스: {len(cases)}개
- 문의 로그 커버리지: {coverage["covered_conversations"]}/{coverage["source_conversations"]}, {coverage["coverage_percent"]}%
- 안전 해결률 변경 전: {before["resolved_count"]}/{before["case_count"]}, {before["resolution_rate"]}%
- 안전 해결률 변경 후: {candidate["resolved_count"]}/{candidate["case_count"]}, {candidate["resolution_rate"]}%
- 해결률 변화: {regression["delta_percentage_points"]}%p
- 약속 위반 변경 전: {before["violation_count"]}건
- 약속 위반 변경 후: {candidate["violation_count"]}건
- 깨진 케이스: {len(regression["broken_cases"])}개
- 배포 판정: {regression["decision"]}
- 전체 실행 시간: {elapsed:.2f}초

## LLM 실행

- 성공 호출: {", ".join(successful) if successful else "없음"}
- 로컬 폴백 호출: {", ".join(fallback_calls) if fallback_calls else "없음"}
- 실패 사유: {", ".join(failure_reasons) if failure_reasons else "없음"}
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
"""
    (ROOT / "RESULT.md").write_text(result, encoding="utf-8")


def main() -> int:
    started = time.monotonic()
    print("[1/6] SYNTHETIC 데이터 생성")
    data = generate_mock_data()
    print("[2/6] 문의 로그에서 테스트 케이스 생성")
    cases, coverage = generate_cases(data)
    print(f"      {len(cases)}개 케이스, 로그 커버리지 {coverage['coverage_percent']}%")
    print("[3/6] LLM 고객과 LLM 봇 시뮬레이션")
    before_tx, candidate_tx, run_log = simulate(cases, data)
    for item in run_log:
        print(f"      {item['call']}: {item['status']} / {item.get('model', 'none')}")
    print("[4/6] 결정론 약속 감사")
    before = audit_all(cases, before_tx, "before")
    candidate = audit_all(cases, candidate_tx, "candidate")
    print(
        f"      해결률 {before['resolution_rate']}% -> {candidate['resolution_rate']}%, "
        f"위반 {before['violation_count']} -> {candidate['violation_count']}건"
    )
    print("[5/6] 리그레션 비교와 배포 판정")
    regression = compare_regression(cases, before, candidate)
    print(f"      {regression['decision']}, 깨진 케이스 {len(regression['broken_cases'])}개")
    print("[6/6] 단일 HTML 리포트 생성")
    build_report(
        cases, coverage, before_tx, candidate_tx,
        before, candidate, regression, run_log,
    )
    elapsed = time.monotonic() - started
    write_result(cases, coverage, before, candidate, regression, run_log, elapsed)
    print(f"완료: {ROOT / 'report.html'}")
    print(f"실행 시간: {elapsed:.2f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
