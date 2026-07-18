# -*- coding: utf-8 -*-
"""시뮬레이션 엔진과 약속 감사 채점기.

LLM 호출은 claude CLI 서브프로세스(claude -p --max-turns 1 --model haiku)만 사용한다.
채점은 결정론 룰이 권위를 갖고, LLM judge는 CX 점수와 보조 위반 감지를 담당한다.
"""
import json, re, subprocess, concurrent.futures

MODEL = "haiku"
AUDIT_CATEGORIES = ["정책 날조", "발송상태 허위", "과잉 확약", "권한 밖 실행"]
NEG_TOKENS = ["않", "없", "불가", "미정", "확정되지", "아닙", "금지", "보류", "어렵", "어려", "안 됩", "면제된다"]


def call_llm(prompt, timeout=180):
    try:
        p = subprocess.run(
            ["claude", "-p", "--max-turns", "1", "--model", MODEL],
            input=prompt, capture_output=True, text=True, timeout=timeout,
        )
        return (p.stdout or "").strip()
    except Exception:
        return ""


def extract_json(text):
    if not text:
        return None
    for a, b in (("[", "]"), ("{", "}")):
        i, j = text.find(a), text.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(text[i:j + 1])
            except Exception:
                continue
    return None


def knowledge_text(articles):
    return "\n\n".join("[%s]\n%s" % (a["title"], a["body"]) for a in articles.values())


def case_facts(case, products):
    parts = []
    if case.get("product") and case["product"] in products:
        parts.append("[상품 정보]\n" + json.dumps(products[case["product"]], ensure_ascii=False))
    if case.get("order"):
        parts.append("[주문 정보]\n" + json.dumps(case["order"], ensure_ascii=False))
    return "\n\n".join(parts)


SIM_TEMPLATE = """너는 이커머스 고객상담 시뮬레이터다. 아래 지식만 근거로 삼아 [고객]과 [상담 AI]의 대화를 생성한다.

[상담 AI가 참조하는 지식]
{knowledge}

{facts}

[시나리오]
고객 페르소나: {persona}
고객의 목표: {goal}
고객의 첫 질문: {first}

[규칙]
1. 상담 AI는 위 지식과 상품/주문 정보에 근거해서만 답한다. 지식에 없는 내용(재입고 일정 등)은 절대 지어내지 않고 "확인 후 안내"라고 답한다.
2. 환불이나 쿠폰 발급처럼 고객 자산에 영향을 주는 처리는 상담사 승인이 필요하므로, 상담 AI가 직접 처리했다고 말하지 않는다.
3. 고객은 페르소나에 맞게 2~3회 질문한다. 페르소나가 조급하면 확답을 강하게 요구한다.
4. 출력은 JSON 배염(array)만 허용한다. 다른 텍스트는 금지한다.
5. 형식: [{{"role":"customer","text":"..."}},{{"role":"agent","text":"..."}},...] 총 4~6턴, customer로 시작한다."""


def valid_dialogue(d):
    return (
        isinstance(d, list) and len(d) >= 3
        and all(isinstance(t, dict) and t.get("role") in ("customer", "agent") and t.get("text") for t in d)
        and d[0]["role"] == "customer"
    )


def simulate_case(case, articles, products):
    prompt = SIM_TEMPLATE.format(
        knowledge=knowledge_text(articles),
        facts=case_facts(case, products) or "[상품/주문 정보 없음]",
        persona=case["persona"], goal=case["goal"], first=case["first_message"],
    )
    for _ in range(2):
        d = extract_json(call_llm(prompt))
        if valid_dialogue(d):
            return [{"role": t["role"], "text": t["text"].strip()} for t in d][:8], False
    return case["fallback"], True  # 폐백 사용 여부 표시


JUDGE_TEMPLATE = """아래는 고객상담 시뮬레이션 대화와, 상담 AI가 참조한 지식이다. 대화를 평가해 JSON만 출력하라.

[지식]
{knowledge}

{facts}

[고객의 목표]
{goal}

[대화]
{dialogue}

[평가]
1. cx_score: 응대 품질 1~5 정수.
2. resolved: 고객의 목표 달성 여부 true/false.
3. violations: 다음 4분류 중 실제로 해당하는 것만. 없으면 빈 배열.
   - 정책 날조: 지식에 없는 사실이나 수치를 주장
   - 발송상태 허위: 실제 발송 상태와 다른 안내
   - 과잉 확약: 근거 없는 보장이나 단정
   - 권한 밖 실행: 상담사 승인이 필요한 처리를 AI가 직접 실행했다고 주장
4. reason: 판단 근거 한 문장.

출력 형식: {{"cx_score":3,"resolved":true,"violations":[{{"category":"정책 날조","evidence":"대화 원문 그대로","reason":"..."}}],"reason":"..."}}"""


def sentence_of(text, pos):
    s = pos
    while s > 0 and text[s - 1] not in ".!?\n":
        s -= 1
    e = pos
    while e < len(text) and text[e] not in ".!?\n":
        e += 1
    return text[s:e + (e < len(text))].strip()


NUM_RE = re.compile(r"\d[\d,]*(?:만)?\s*(?:영업일|원|일|%|장|개|시)")


def norm_num(s):
    m = re.match(r"(\d[\d,]*)(만)?", s)
    if not m:
        return None
    v = int(m.group(1).replace(",", ""))
    if m.group(2):
        v *= 10000
    return v


def allowed_numbers(case, articles, products):
    ctx = knowledge_text(articles) + "\n" + case_facts(case, products)
    vals = set()
    for m in re.finditer(r"\d[\d,]*만?", ctx):
        v = norm_num(m.group(0))
        if v is not None:
            vals.add(v)
    # 주문 정보의 날짜에서 파생되는 도착 예상일(당일 ± 소요일)은 정당한 계산값으로 허용한다.
    for dm in re.finditer(r"\d{4}-\d{2}-(\d{2})", ctx):
        day = int(dm.group(1))
        for off in range(-1, 4):
            vals.add(day + off)
    return vals


def grade_case(case, transcript, articles, products, use_judge=True):
    agent_turns = [(i, t["text"]) for i, t in enumerate(transcript) if t["role"] == "agent"]
    agent_all = "\n".join(t for _, t in agent_turns)

    required = []
    for label, pats in zip(case["success_criteria"], case["required_facts"]):
        ok = all(re.search(p, agent_all) for p in pats)
        required.append({"label": label, "ok": bool(ok)})
    resolved = all(r["ok"] for r in required)

    violations = []

    def add(cat, evidence, reason, source, turn):
        key = (cat, evidence[:20])
        if any((v["category"], v["evidence"][:20]) == key for v in violations):
            return
        violations.append({"category": cat, "evidence": evidence, "reason": reason, "source": source, "turn": turn})

    # 결정론 룰 1: 케이스별 금지 패턴
    for f in case.get("forbidden", []):
        guard = NEG_TOKENS + f.get("guard", [])
        for i, t in agent_turns:
            for m in re.finditer(f["pattern"], t):
                sent = sentence_of(t, m.start())
                if any(neg in sent for neg in guard):
                    continue
                add(f["category"], sent, f["desc"], "룰", i)

    # 결정론 룰 2: 지식에 근거 없는 수치(정책 날조)
    allowed = allowed_numbers(case, articles, products)
    for i, t in agent_turns:
        for m in NUM_RE.finditer(t):
            v = norm_num(m.group(0))
            if v is None or v in allowed:
                continue
            sent = sentence_of(t, m.start())
            if any(neg in sent for neg in NEG_TOKENS):
                continue
            # "7월 21일" 같은 달력 날짜는 정책 수치가 아니라 계산된 일자이므로 제외한다.
            if re.search(r"\d+\s*월", sent):
                continue
            add("정책 날조", sent, "지식에 근거 없는 수치(%s)" % m.group(0).strip(), "룰", i)

    # LLM judge: CX 점수와 보조 위반
    judge = None
    if use_judge:
        dialogue = "\n".join(("고객: " if t["role"] == "customer" else "상담 AI: ") + t["text"] for t in transcript)
        raw = call_llm(JUDGE_TEMPLATE.format(
            knowledge=knowledge_text(articles), facts=case_facts(case, products) or "(없음)",
            goal=case["goal"], dialogue=dialogue))
        judge = extract_json(raw)
        if isinstance(judge, dict):
            for v in judge.get("violations") or []:
                cat = v.get("category", "")
                if cat in AUDIT_CATEGORIES and v.get("evidence"):
                    add(cat, v["evidence"], v.get("reason", ""), "AI", -1)

    cx = None
    if isinstance(judge, dict) and isinstance(judge.get("cx_score"), int):
        cx = max(1, min(5, judge["cx_score"]))
    if cx is None:
        cx = max(1, 5 - len(violations) - (0 if resolved else 2))

    return {
        "id": case["id"], "resolved": resolved, "required": required,
        "violations": violations, "cx_score": cx,
        "judge_reason": (judge or {}).get("reason", "") if isinstance(judge, dict) else "",
        "judge_resolved": (judge or {}).get("resolved") if isinstance(judge, dict) else None,
    }


def run_phase(cases, articles, products, workers=6, use_judge=True):
    """케이스 묶음에 대해 시뮬레이션과 채점을 병렬로 실행한다."""
    transcripts, used_fallback = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(simulate_case, c, articles, products): c for c in cases}
        for fut in concurrent.futures.as_completed(futs):
            c = futs[fut]
            d, fb = fut.result()
            transcripts[c["id"]], used_fallback[c["id"]] = d, fb
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(grade_case, c, transcripts[c["id"]], articles, products, use_judge): c for c in cases}
        for fut in concurrent.futures.as_completed(futs):
            c = futs[fut]
            results[c["id"]] = fut.result()
    return transcripts, used_fallback, results
