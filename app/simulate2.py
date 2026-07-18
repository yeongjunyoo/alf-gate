"""시뮬레이터 백업 구현. 고객역과 봇역 LLM이 번갈아 대화한다."""
import sys

sys.path.insert(0, "app")
import llm

BOT_SYSTEM = ("너는 이커머스 쇼핑몰의 AI 상담원이다. 아래 지식 아티클 본문만 근거로 답한다. "
              "지식 아티클에 질문과 관련된 기준이나 수치가 있으면 반드시 그 내용을 인용해 즉답한다. "
              "확인 후 안내드리겠다는 답은 지식에 근거가 전혀 없을 때만 쓴다. "
              "지식에 없는 정책은 추측하지 말고 확인 후 안내드리겠다고 답한다. "
              "개별 주문 상태나 실시간 재고처럼 시스템 조회가 필요한 요청은 지식에 있는 절차와 기준을 안내하면 충분하다. "
              "친절하고 간결하게, 두세 문장 이내의 한국어로 답한다.")


def _knowledge_text(articles):
    return "\n\n".join(f"[{a['title']}]\n{a['body']}" for a in articles)


def _clean(text):
    import re
    return re.sub(r"^(상담원 답변|상담원|답변|고객)\s*[:：]\s*", "", text.strip()).strip()


def simulate_case(case, knowledge_articles, max_customer_turns=3, on_turn=None):
    kb = _knowledge_text(knowledge_articles)
    p = case["persona"]
    customer_system = (f"너는 쇼핑몰 고객 {p.get('name', '')}이다. 성격: {p.get('traits', '')}. "
                       f"상황: {p.get('situation', '')}. 목표: {case['goal']}. "
                       "한국어로 실제 고객처럼 짧게 말한다. 목표에 대한 답을 받으면 즉시 [END]만 출력한다. "
                       "목표와 무관한 새로운 질문을 만들지 않는다.")
    transcript = []
    history = ""
    for turn in range(max_customer_turns):
        cust_prompt = ("지금까지 대화:\n" + (history or "(대화 시작)") +
                       "\n\n다음 고객 발화 한 개만 출력하라. 끝내려면 [END]만 출력.")
        cust = llm.ask(cust_prompt, customer_system).strip()
        if "[END]" in cust or not cust:
            break
        transcript.append({"role": "customer", "text": cust})
        if on_turn:
            on_turn("customer", cust)
        history += f"고객: {cust}\n"
        bot_prompt = f"[지식 아티클]\n{kb}\n\n[대화]\n{history}\n상담원 답변 한 개만 출력하라."
        bot = _clean(llm.ask(bot_prompt, BOT_SYSTEM))
        transcript.append({"role": "agent", "text": bot})
        if on_turn:
            on_turn("agent", bot)
        history += f"상담원: {bot}\n"
    return transcript
