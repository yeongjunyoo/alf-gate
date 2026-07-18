#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ALF 세팅 게이트 엔드투엔드 파이프라인.

합성 데이터 생성 → 케이스 자동 합성 → 시뮬레이션 → 약속 감사 채점 →
지식 변경 리그레션 재실행 → report.html 생성.
"""
import os, sys, json, time, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from data import write_all, build_cases, products_dict, ARTICLES, A2_PATCH, STAMP
from engine import run_phase
from report import render


def log(msg):
    print("[%s] %s" % (datetime.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def summarize(cases, results):
    n = len(cases)
    resolved = sum(1 for c in cases if results[c["id"]]["resolved"])
    viols = [(c["id"], v) for c in cases for v in results[c["id"]]["violations"]]
    return resolved, n, viols


def main():
    t0 = time.time()
    data_dir = os.path.join(BASE, "data")

    log("1/5 합성 데이터 생성 (%s)" % STAMP)
    write_all(data_dir)
    cases, coverage = build_cases()
    products = products_dict()
    log("    케이스 %d개, 로그 커버리지 %d/%d (%.1f%%)" % (
        len(cases), coverage["covered_logs"], coverage["total_logs"], coverage["rate"] * 100))

    log("2/5 기준선 시뮬레이션 + 약속 감사 (claude -p --model haiku)")
    transcripts, fallback, results = run_phase(cases, ARTICLES, products)
    resolved_n, n, viols = summarize(cases, results)
    log("    해결 %d/%d, 위반 %d건" % (resolved_n, n, len(viols)))

    log("3/5 지식 변경 감지: '%s' 개정안" % ARTICLES["A2"]["title"])
    articles2 = {k: dict(v) for k, v in ARTICLES.items()}
    articles2["A2"]["body"] = A2_PATCH["body"]
    re_cases = [c for c in cases if c["article_id"] == "A2"]
    log("4/5 영향 케이스 %d개 자동 재실행" % len(re_cases))
    transcripts2, fallback2, results2 = run_phase(re_cases, articles2, products)

    after_results = dict(results)
    after_results.update(results2)
    resolved2_n = sum(1 for c in cases if after_results[c["id"]]["resolved"])
    viols2 = [(c["id"], v) for c in cases for v in after_results[c["id"]]["violations"]]

    before_rate = round(resolved_n / n * 100)
    after_rate = round(resolved2_n / n * 100)
    delta = after_rate - before_rate

    new_viols = []
    for cid, v in viols2:
        before_keys = {(vv["category"], vv["evidence"][:20]) for cc, vv in viols if cc == cid}
        if (v["category"], v["evidence"][:20]) not in before_keys:
            new_viols.append((cid, v))

    broken = []
    for c in cases:
        b, a = results[c["id"]], after_results[c["id"]]
        lost = b["resolved"] and not a["resolved"]
        added = sum(1 for cc, _ in new_viols if cc == c["id"])
        if lost or added:
            broken.append((c, lost, added))

    hold = delta < 0 or bool(new_viols) or bool(broken)
    log("    해결률 %d%% → %d%% (Δ %+d%%p), 신규 위반 %d건 → %s" % (
        before_rate, after_rate, delta, len(new_viols), "배포 보류 권고" if hold else "배포 승인 가능"))

    # 감사 요약
    cat_names = ["정책 날조", "발송상태 허위", "과잉 확약", "권한 밖 실행"]
    cats = []
    for name in cat_names:
        hits = [(cid, v) for cid, v in viols if v["category"] == name]
        cats.append({"name": name, "count": len(hits),
                     "example": hits[0][1]["evidence"] if hits else ""})
    hidden = [c for c in cases if results[c["id"]]["resolved"] and results[c["id"]]["violations"]]
    hidden_note = ""
    if hidden:
        hidden_note = "품질 기준으로는 해결됐지만 감사 축에서 실패한 케이스 %d개(%s). CX 점수만으로는 잡히지 않는 위반입니다." % (
            len(hidden), ", ".join(c["id"] for c in hidden))

    # 게이트 판정 문구
    reasons = []
    if delta < 0:
        reasons.append("해결률 %+d%%p (%d%% → %d%%)" % (delta, before_rate, after_rate))
    if new_viols:
        reasons.append("신규 약속 위반 %d건" % len(new_viols))
    for c, lost, added in broken:
        bits = []
        if lost:
            bits.append("미해결 전환")
        if added:
            bits.append("위반 %d건 추가" % added)
        reasons.append("%s %s: %s" % (c["id"], c["title"], ", ".join(bits)))
    if not reasons:
        reasons.append("변경 전후 지표 변화 없음")
    gate = {
        "hold": hold,
        "summary": ("지식 '%s' 개정으로 영향 케이스 %d개를 자동 재실행한 결과 품질 퇴행이 감지됐습니다. "
                    "사람이 승인하기 전까지 배포를 보류하는 것을 권고합니다." % (ARTICLES["A2"]["title"], len(re_cases)))
                   if hold else
                   "지식 변경 후에도 해결률과 약속 감사 지표가 유지됩니다. 사람 승인 후 배포 가능합니다.",
        "reasons": reasons,
    }

    payload = {
        "meta": {
            "run_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "duration": "%.1f초" % (time.time() - t0),
            "model": "claude haiku (claude -p)",
            "cases": n, "logs": coverage["total_logs"],
        },
        "gate": gate,
        "kpi": {
            "resolved_rate": before_rate, "resolved_n": resolved_n, "cases": n,
            "violations": len(viols), "violated_cases": len({cid for cid, _ in viols}),
            "coverage": round(coverage["rate"] * 100), "uncovered": len(coverage["uncovered"]),
            "delta": delta,
        },
        "coverage": coverage,
        "audit": {"categories": cats, "hidden_note": hidden_note},
        "cases": [{
            "id": c["id"], "title": c["title"], "tag": c["tag"],
            "persona": c["persona"], "persona_name": c["persona_name"],
            "goal": c["goal"], "log_count": c["log_count"],
            "transcript": transcripts[c["id"]],
            "resolved": results[c["id"]]["resolved"],
            "required": results[c["id"]]["required"],
            "violations": results[c["id"]]["violations"],
            "cx_score": results[c["id"]]["cx_score"],
            "judge_reason": results[c["id"]]["judge_reason"],
        } for c in cases],
        "regression": {
            "article": ARTICLES["A2"]["title"],
            "removed": A2_PATCH["removed"], "added": A2_PATCH["added"],
            "before_rate": before_rate, "after_rate": after_rate,
            "rows": [{
                "id": c["id"], "title": c["title"],
                "before": ("해결" if results[c["id"]]["resolved"] else "미해결") +
                          (", 위반 %d" % len(results[c["id"]]["violations"]) if results[c["id"]]["violations"] else ""),
                "after": ("해결" if results2[c["id"]]["resolved"] else "미해결") +
                         (", 위반 %d" % len(results2[c["id"]]["violations"]) if results2[c["id"]]["violations"] else ""),
                "delta": ("해결 → 미해결" if results[c["id"]]["resolved"] and not results2[c["id"]]["resolved"]
                          else ("위반 %+d건" % (len(results2[c["id"]]["violations"]) - len(results[c["id"]]["violations"]))
                                if len(results2[c["id"]]["violations"]) != len(results[c["id"]]["violations"])
                                else "변화 없음")),
                "broken": bool((results[c["id"]]["resolved"] and not results2[c["id"]]["resolved"])
                               or len(results2[c["id"]]["violations"]) > len(results[c["id"]]["violations"])),
            } for c in re_cases],
            "verdict": gate["summary"],
        },
    }

    log("5/5 리포트 생성")
    out = render(os.path.join(BASE, "report.html"), payload)
    with open(os.path.join(BASE, "out.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    stats = {
        "duration_sec": round(time.time() - t0, 1),
        "cases": n, "resolved": resolved_n, "before_rate": before_rate,
        "after_rate": after_rate, "delta": delta,
        "violations": len(viols), "new_violations": len(new_viols),
        "coverage_rate": round(coverage["rate"] * 100, 1),
        "fallback_used": [cid for cid, fb in {**fallback, **fallback2}.items() if fb],
        "hold": hold,
    }
    with open(os.path.join(BASE, "stats.json"), "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    log("완료: %s (%.1f초)" % (out, time.time() - t0))
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
