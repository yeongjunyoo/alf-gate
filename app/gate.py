"""alf-gate 오케스트레이터.

사용법:
  python3 app/gate.py all        전체 파이프라인 (생성, 기준 실행, 변경, 재실행, 리포트)
  python3 app/gate.py gen        로그에서 케이스와 커버리지 생성
  python3 app/gate.py baseline   변경 전 시뮬레이션 실행
  python3 app/gate.py change     지식 아티클 변경 적용 (배송 안내에서 출고 기준 삭제)
  python3 app/gate.py candidate  변경 후 재실행
  python3 app/gate.py report     리포트 조립과 렌더링
"""
import datetime
import json
import subprocess
import sys

sys.path.insert(0, "app")

DATA = "data"
OUT = "out"
RANK = {"pass": 0, "warn": 1, "fail": 2, "error": 2}


def _load(path):
    return json.load(open(path, encoding="utf-8"))


def _save(obj, path):
    json.dump(obj, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def step_gen():
    import casegen
    casegen.generate()


def _run(knowledge_path, label, run_id, out_path):
    from score2 import run_cases
    cases = _load(f"{OUT}/cases.json")["cases"]
    knowledge = _load(knowledge_path)
    policies = _load(f"{DATA}/policies.json")
    run = run_cases(cases, knowledge, policies, f"{DATA}/cafe24_products.csv", label, run_id)
    _save(run, out_path)
    s = run["summary"]
    print(f"{run_id}: 해결률 {s['resolutionRate']:.0%} pass={s['passCount']} "
          f"warn={s['warnCount']} fail={s['failCount']} 위반={s['violationCount']}")


def step_baseline():
    _run(f"{DATA}/knowledge_articles.json", "변경 전", "run-baseline", f"{OUT}/run-baseline.json")


def step_change():
    arts = _load(f"{DATA}/knowledge_articles.json")
    for a in arts:
        if a["id"] == "KA-01":
            a["body"] = a["body"].replace(
                "평일 오후 2시 이전 결제하신 주문은 당일 출고됩니다. ", "")
    _save(arts, f"{OUT}/knowledge_changed.json")
    _save({"type": "article_edit",
           "description": "배송 안내 아티클에서 당일 출고 기준(평일 오후 2시) 문구 삭제",
           "editedBy": "CX 매니저 (모의)",
           "at": datetime.datetime.now().isoformat(timespec="seconds")},
          f"{OUT}/change.json")
    print("변경 적용: KA-01 배송 안내에서 출고 기준 문구 삭제")


def step_candidate():
    _run(f"{OUT}/knowledge_changed.json", "변경 후", "run-candidate", f"{OUT}/run-candidate.json")


def _regression(base, cand):
    b_res = {r["caseId"]: r for r in base["results"]}
    c_res = {r["caseId"]: r for r in cand["results"]}
    broken = []
    for cid, cr in c_res.items():
        br = b_res.get(cid)
        if not br:
            continue
        if RANK.get(cr["outcome"], 2) > RANK.get(br["outcome"], 2):
            reason = cr.get("judgeReason") or ""
            if cr.get("audit", {}).get("violations"):
                v = cr["audit"]["violations"][0]
                reason = f"{v.get('typeLabel', '위반')}: {v.get('botClaim', '')[:60]}"
            broken.append({"caseId": cid, "before": br["outcome"], "after": cr["outcome"],
                           "reason": reason or "판정 악화"})
    delta = round(cand["summary"]["resolutionRate"] - base["summary"]["resolutionRate"], 3)
    # 노이즈 플로어: LLM 시뮬 분산으로 케이스 1~2개는 실행마다 뒤집힐 수 있다.
    # 델타 -5%p 이하, 위반 증가, 깨진 케이스 3개 이상일 때만 보류를 권고한다.
    hold = (delta <= -0.05 or len(broken) >= 3
            or cand["summary"]["violationCount"] > base["summary"]["violationCount"])
    return {
        "baselineRunId": base["runId"], "candidateRunId": cand["runId"],
        "change": _load(f"{OUT}/change.json"),
        "deltaResolutionRate": delta,
        "brokenCases": broken,
        "recommendation": "hold" if hold else "publish",
        "recommendationLabel": "배포 보류 권고, 승인 필요" if hold else "배포 가능",
    }


def step_report():
    cases_doc = _load(f"{OUT}/cases.json")
    base = _load(f"{OUT}/run-baseline.json")
    cand = _load(f"{OUT}/run-candidate.json")
    report = {
        "meta": {
            "product": "alf-gate",
            "tagline": "ALF 테스트의 빈 시험지를 로그로 채우는 세팅 게이트",
            "store": "그린백 스토어 (SYNTHETIC)",
            "generatedAt": datetime.datetime.now().isoformat(timespec="seconds"),
            "synthetic": True,
            "sourceFiles": [f"{DATA}/cafe24_products.csv", f"{DATA}/channeltalk_userchats.csv",
                            f"{DATA}/channeltalk_messages.csv", f"{DATA}/knowledge_articles.json"],
        },
        "coverage": cases_doc["coverage"],
        "cases": cases_doc["cases"],
        "runs": [base, cand],
        "regression": _regression(base, cand),
    }
    _save(report, f"{OUT}/report.json")
    subprocess.run([sys.executable, "app/render_report.py", f"{OUT}/report.json",
                    f"{OUT}/report.html"], check=True)
    print(f"리포트 생성: {OUT}/report.html")


STEPS = {"gen": step_gen, "baseline": step_baseline, "change": step_change,
         "candidate": step_candidate, "report": step_report}

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which == "all":
        for name in ["gen", "baseline", "change", "candidate", "report"]:
            print(f"== {name} ==")
            STEPS[name]()
    else:
        STEPS[which]()
