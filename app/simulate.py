"""지식 아티클만 사용하는 AI 상담 대화를 시뮬레이션한다."""

import json
import re

try:
    from . import llm
except ImportError:
    import llm


_FORBIDDEN_PUNCTUATION = str.maketrans({"\u2014": ", ", "\u2013": ", ", "\u00b7": ", "})
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


def clean_text(value) -> str:
    """LLM 출력에서 금지 문장 부호와 이모지를 제거한다."""
    text = str(value or "").translate(_FORBIDDEN_PUNCTUATION)
    text = _EMOJI_RE.sub("", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _knowledge_payload(knowledge_articles):
    return [
        {
            "id": str(article.get("id", "")),
            "title": str(article.get("title", "")),
            "body": str(article.get("body", "")),
        }
        for article in knowledge_articles
        if isinstance(article, dict)
    ]


def _customer_system(case) -> str:
    persona = case.get("persona") or {}
    return f"""당신은 이커머스 고객 역할이다.
이름은 {persona.get('name', '고객')}이다.
성격은 {persona.get('traits', '자연스럽고 간결함')}이다.
상황은 {persona.get('situation', '')}이다.
상담 목표는 {case.get('goal', '')}이다.

규칙:
1. 첫 발화에서는 상황과 목표에 맞는 문의를 한국어로 자연스럽게 시작한다.
2. 이후에는 상담 봇의 마지막 답변을 보고 필요한 후속 질문 하나만 한다.
3. 목표를 달성했거나 더 물을 내용이 없으면 다른 말 없이 [END]만 출력한다.
4. 고객에게 공개되지 않은 정책이나 지식을 미리 아는 것처럼 말하지 않는다.
5. 답변은 한두 문장으로 짧게 쓴다.
6. 엠대시, 엔대시, 중간점, 이모지, 과장어를 쓰지 않는다."""


def _agent_system() -> str:
    return """당신은 이커머스 AI 상담 봇 ALF 역할이다.
오직 제공된 지식 아티클의 body에 적힌 내용만 사실 근거로 사용한다.
title과 id는 문서를 찾는 용도로만 사용하고 사실 근거로 삼지 않는다.
지식에 없는 정책, 수치, 금액, 기한, 주문 상태, 처리 결과를 추측하거나 만들지 않는다.
근거가 없으면 확인 후 안내드리겠습니다와 같이 답한다.
실제로 실행하지 않은 환불, 취소, 쿠폰 발급을 완료했다고 말하지 않는다.
고객에게 친절하고 간결한 한국어로 답한다.
엠대시, 엔대시, 중간점, 이모지, 과장어를 쓰지 않는다."""


def _next_customer(case, transcript) -> str:
    if transcript:
        prompt = "지금까지의 상담은 다음과 같다. 다음 고객 발화만 출력하라.\n\n"
        prompt += json.dumps(transcript, ensure_ascii=False, indent=2)
    else:
        prompt = "상담을 시작하는 첫 고객 발화만 출력하라."
    return clean_text(llm.ask(prompt, system=_customer_system(case)))


def _next_agent(knowledge_articles, transcript) -> str:
    prompt = """다음 지식 아티클과 상담 기록을 보고 상담 봇의 다음 답변만 출력하라.

[지식 아티클]
{}

[상담 기록]
{}""".format(
        json.dumps(_knowledge_payload(knowledge_articles), ensure_ascii=False, indent=2),
        json.dumps(transcript, ensure_ascii=False, indent=2),
    )
    return clean_text(llm.ask(prompt, system=_agent_system()))


def simulate_case(case, knowledge_articles, max_customer_turns=3):
    """고객과 ALF를 번갈아 호출해 role, text 형식의 대화를 만든다."""
    if not isinstance(case, dict):
        raise TypeError("case는 객체여야 합니다")
    if not isinstance(knowledge_articles, list):
        raise TypeError("knowledge_articles는 배열이어야 합니다")
    if not isinstance(max_customer_turns, int) or max_customer_turns < 1:
        raise ValueError("max_customer_turns는 1 이상의 정수여야 합니다")

    transcript = []
    for _ in range(max_customer_turns):
        customer_text = _next_customer(case, transcript)
        if not customer_text:
            raise RuntimeError("고객 역할이 빈 답변을 반환했습니다")
        if "[END]" in customer_text:
            break

        transcript.append({"role": "customer", "text": customer_text})
        agent_text = _next_agent(knowledge_articles, transcript)
        if not agent_text:
            raise RuntimeError("상담 봇이 빈 답변을 반환했습니다")
        transcript.append({"role": "agent", "text": agent_text})

    return transcript

