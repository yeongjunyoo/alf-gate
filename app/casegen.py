"""로그에서 테스트 케이스, 평가 기준, 페르소나, 커버리지를 생성한다.

파이프라인:
1. 채널톡 메시지 시트를 상담 단위로 묶는다
2. 키워드 룰로 클러스터링한다 (결정론, 설명 가능)
3. 클러스터별로 지식 아티클 매칭을 확인한다. 매칭이 없으면 미커버로 남긴다
4. 커버 클러스터는 LLM이 실제 문답과 정책 원장을 근거로 케이스를 합성한다
5. 커버리지 지표를 계산한다

LLM 실패 시 클러스터별 결정론 폴백 케이스를 쓴다. 데모가 죽는 일은 없다.
"""
import csv
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "app")
import llm

CLUSTER_RULES = [
    ("배송 조회/지연", ["배송", "출고", "송장", "도착", "언제 받", "택배"]),
    ("반품/교환 절차", ["반품", "교환", "환불", "취소", "불량"]),
    ("재고/재입고", ["재입고", "품절", "재고", "입고"]),
    ("쿠폰/할인", ["쿠폰", "할인", "적용"]),
    ("상품 정보", ["세탁", "소재", "사이즈", "수납", "글자", "자수 몇"]),
    ("해외 배송", ["해외", "미국", "일본", "관세"]),
    ("대량 구매/B2B", ["단체", "대량", "견적", "로고", "기업"]),
]

# 클러스터 -> 관련 지식 아티클 id (매칭 없으면 미커버)
KNOWLEDGE_MAP = {
    "배송 조회/지연": ["KA-01", "KA-09"],
    "반품/교환 절차": ["KA-02", "KA-04", "KA-07"],
    "재고/재입고": ["KA-06"],
    "쿠폰/할인": ["KA-05"],
    "상품 정보": ["KA-07", "KA-08"],
    "해외 배송": [],
    "대량 구매/B2B": [],
}
UNCOVERED_REASON = {
    "해외 배송": "지식과 정책 원문이 없어 케이스를 만들 수 없음. 과거 답변도 전부 확인 후 안내로 이탈함. 다음 온보딩 단계로 제안",
    "대량 구매/B2B": "과거 답변이 건별로 달라 정책 확정이 필요함. 담당자 정책 결정 후 케이스 생성 가능",
}
CASES_PER_CLUSTER = {"배송 조회/지연": 3, "반품/교환 절차": 4, "재고/재입고": 2, "쿠폰/할인": 2, "상품 정보": 1}


def load_chats(msg_path, uc_path):
    chats = defaultdict(list)
    for row in csv.DictReader(open(msg_path, encoding="utf-8-sig")):
        chats[row["ChatId"]].append(row)
    names = {}
    for row in csv.DictReader(open(uc_path, encoding="utf-8-sig")):
        names[row["id"]] = row.get("name", "")
    return chats, names


def classify(chats):
    clusters = defaultdict(list)
    for cid, msgs in chats.items():
        first_user = next((m["PlainText"] for m in msgs if m["PersonType"] == "user"), "")
        hit = None
        for cname, kws in CLUSTER_RULES:
            if any(k in first_user for k in kws):
                hit = cname
                break
        clusters[hit or "기타"].append(cid)
    return clusters


def sample_dialogues(chats, cids, n=4):
    out = []
    for cid in cids[:n]:
        lines = []
        for m in chats[cid]:
            who = "고객" if m["PersonType"] == "user" else "상담원"
            lines.append(f"{who}: {m['PlainText']}")
        out.append({"chatId": cid, "dialogue": "\n".join(lines)})
    return out


def synth_cluster_cases(cluster, dialogues, policies, names, count):
    pol = [p for p in policies]
    prompt = f"""이커머스 CX의 AI 상담 테스트 케이스를 만든다. 아래는 '{cluster}' 유형의 실제 과거 상담과 정책 원장이다.

[과거 상담 샘플]
{json.dumps(dialogues, ensure_ascii=False, indent=1)}

[정책 원장]
{json.dumps(pol, ensure_ascii=False, indent=1)}

케이스 {count}개를 JSON 배열로 만들어라. 각 원소:
{{"goal": "고객이 이 상담으로 이루려는 것 한 문장", "successCriteria": "정책 원장의 구체 수치와 사실을 포함한 성공 판정 기준 한두 문장", "persona": {{"name": "한국 이름", "traits": "성격 두세 단어", "situation": "구체적 상황 한 문장"}}, "sourceChatIds": [실제 chatId 1~2개]}}

규칙: successCriteria는 반드시 정책 원장의 수치를 인용한다. 서로 다른 세부 시나리오여야 한다. 엠대시와 중간점 금지, 짧은 문장."""
    return llm.ask_json(prompt)


FALLBACK = {
    "배송 조회/지연": [{"goal": "당일 출고 기준을 확인한다", "successCriteria": "평일 오후 2시 이전 결제 건만 당일 출고임을 안내하면 성공",
                    "persona": {"name": "이지우", "traits": "급함", "situation": "선물용이라 내일까지 필요"}, "sourceChatIds": []}],
    "반품/교환 절차": [{"goal": "단순변심 반품 비용과 기한을 확인한다", "successCriteria": "7일 이내, 편도 3,000원 고객 부담을 안내하면 성공",
                    "persona": {"name": "김하윤", "traits": "꼼꼼함", "situation": "3일 전 수령한 에코백 색상 불만"}, "sourceChatIds": []}],
    "재고/재입고": [{"goal": "품절 상품 재입고 일정을 묻는다", "successCriteria": "확정 전 일정 확약 없이 재입고 알림 신청을 안내하면 성공",
                  "persona": {"name": "정도윤", "traits": "집요함", "situation": "크로스 에코백 네이비 품절"}, "sourceChatIds": []}],
    "쿠폰/할인": [{"goal": "첫 구매 쿠폰 미적용 사유를 확인한다", "successCriteria": "30,000원 이상 조건과 중복 불가를 안내하면 성공",
                "persona": {"name": "박서준", "traits": "성급함", "situation": "장바구니 27,000원에서 쿠폰 실패"}, "sourceChatIds": []}],
    "상품 정보": [{"goal": "에코백 세탁 방법을 확인한다", "successCriteria": "찬물 단독 손세탁과 건조기 금지를 안내하면 성공",
                "persona": {"name": "강서연", "traits": "신중함", "situation": "첫 세탁을 앞두고 문의"}, "sourceChatIds": []}],
}


def generate(msg_path="data/channeltalk_messages.csv", uc_path="data/channeltalk_userchats.csv",
             policies_path="data/policies.json", out_path="out/cases.json"):
    chats, names = load_chats(msg_path, uc_path)
    policies = json.load(open(policies_path, encoding="utf-8"))
    clusters = classify(chats)
    total = len(chats)

    jobs = []
    for cluster, count in CASES_PER_CLUSTER.items():
        cids = clusters.get(cluster, [])
        jobs.append((cluster, sample_dialogues(chats, cids, 4), count))

    def _run(job):
        cluster, dialogues, count = job
        try:
            cases = synth_cluster_cases(cluster, dialogues, policies, names, count)
            assert isinstance(cases, list) and cases
            return cluster, cases, True
        except Exception:
            return cluster, list(FALLBACK[cluster]), False

    results = list(ThreadPoolExecutor(max_workers=5).map(_run, jobs))

    all_cases, cluster_summary = [], []
    idx = 0
    for cluster, cases, from_llm in results:
        ids = []
        for c in cases:
            idx += 1
            cid = f"C{idx:02d}"
            ids.append(cid)
            src = c.get("sourceChatIds") or clusters.get(cluster, [])[:2]
            all_cases.append({
                "id": cid, "cluster": cluster, "goal": c["goal"],
                "successCriteria": c["successCriteria"], "persona": c["persona"],
                "sourceChatIds": src[:2], "alfTestCompatible": True,
                "generatedBy": "llm" if from_llm else "fallback",
            })
        cluster_summary.append({"name": cluster, "chatCount": len(clusters.get(cluster, [])),
                                "covered": True, "caseIds": ids})

    uncovered = []
    covered_chats = sum(c["chatCount"] for c in cluster_summary)
    for cluster, reason in UNCOVERED_REASON.items():
        cids = clusters.get(cluster, [])
        first_q = ""
        if cids:
            first_q = next((m["PlainText"] for m in chats[cids[0]] if m["PersonType"] == "user"), "")
        uncovered.append({"name": cluster, "chatCount": len(cids), "sampleQuestion": first_q, "reason": reason})

    coverage = {
        "totalChats": total, "coveredChats": covered_chats,
        "coveragePct": round(covered_chats * 100.0 / total, 1),
        "clusters": cluster_summary, "uncovered": uncovered,
    }
    json.dump({"cases": all_cases, "coverage": coverage},
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"cases={len(all_cases)} coverage={coverage['coveragePct']}% "
          f"(llm={sum(1 for c in all_cases if c['generatedBy'] == 'llm')}, "
          f"fallback={sum(1 for c in all_cases if c['generatedBy'] == 'fallback')})")
    return all_cases, coverage


if __name__ == "__main__":
    generate()
