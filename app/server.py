"""alf-gate 라이브 데모 서버.

사용법: python3 app/server.py  (기본 http://localhost:8787)
브라우저에서 파이프라인을 단계별로 실행하고 시뮬레이션 대화를 실시간으로 본다.
외부 의존 없음. LLM은 로컬 CLI 체인.
"""
import http.server
import json
import os
import sys
import threading
import urllib.parse

sys.path.insert(0, "app")

PORT = int(os.environ.get("PORT", "8899"))
EVENTS = []
LOCK = threading.Lock()
STATE = {"busy": False, "done_steps": []}


def emit(etype, **data):
    with LOCK:
        EVENTS.append({"seq": len(EVENTS), "type": etype, **data})


def _load(path):
    return json.load(open(path, encoding="utf-8"))


def _run_stage(run_id, label, knowledge_path):
    from score2 import run_cases
    cases = _load("out/cases.json")["cases"]
    knowledge = _load(knowledge_path)
    policies = _load("data/policies.json")
    run = run_cases(cases, knowledge, policies, "data/cafe24_products.csv",
                    label, run_id, on_event=emit)
    json.dump(run, open(f"out/{run_id}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    emit("summary", runId=run_id, label=label, summary=run["summary"])
    return run

def _changed_article_ids(new_knowledge_path):
    orig = {a["id"]: a["body"] for a in _load("data/knowledge_articles.json")}
    new = {a["id"]: a["body"] for a in _load(new_knowledge_path)}
    diff = [i for i in orig if new.get(i) != orig[i]]
    return diff or [i for i in new if i not in orig]


def _run_stage_scoped(run_id, label, knowledge_path):
    """변경 영향 케이스만 재실행하고 나머지는 변경 전 결과를 유지한다.
    무관 케이스의 실행 분산이 리그레션 신호를 오염시키지 않게 한다."""
    import datetime
    from score2 import run_cases
    import casegen
    all_cases = _load("out/cases.json")["cases"]
    base = _load("out/run-baseline.json")
    changed = _changed_article_ids(knowledge_path)
    affected = [c for c in all_cases
                if any(a in casegen.KNOWLEDGE_MAP.get(c["cluster"], []) for a in changed)]
    aff_ids = {c["id"] for c in affected}
    case_by_id = {c["id"]: c for c in all_cases}
    emit("scope", changedArticles=changed,
         affectedCases=sorted(aff_ids),
         reusedCount=len(all_cases) - len(affected))
    knowledge = _load(knowledge_path)
    policies = _load("data/policies.json")
    partial = run_cases(affected, knowledge, policies, "data/cafe24_products.csv",
                        label, run_id, on_event=emit)
    new_by_id = {r["caseId"]: r for r in partial["results"]}
    results = []
    for r in base["results"]:
        if r["caseId"] in new_by_id:
            results.append(new_by_id[r["caseId"]])
        else:
            rr = dict(r)
            rr["reused"] = True
            results.append(rr)
            emit("case_start", caseId=rr["caseId"], case=case_by_id.get(rr["caseId"], {}))
            emit("case_done", caseId=rr["caseId"], result=rr, reused=True)
    ok = [r for r in results if r["outcome"] != "error"]
    summary = {
        "caseCount": len(results),
        "resolutionRate": round(sum(1 for r in ok if r["resolved"]) / max(len(ok), 1), 2),
        "passCount": sum(1 for r in results if r["outcome"] == "pass"),
        "warnCount": sum(1 for r in results if r["outcome"] == "warn"),
        "failCount": sum(1 for r in results if r["outcome"] in ("fail", "error")),
        "violationCount": sum(len(r["audit"]["violations"]) for r in results),
    }
    run = {"runId": run_id, "label": label,
           "startedAt": datetime.datetime.now().isoformat(timespec="seconds"),
           "settingsSnapshot": {"articleCount": len(knowledge), "changedArticles": changed},
           "summary": summary, "results": results}
    json.dump(run, open(f"out/{run_id}.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    emit("summary", runId=run_id, label=label, summary=summary)
    return run


KNOWN_SCHEMAS = [
    ("cafe24_products.csv", "카페24 상품 엑셀",
     ["상품 코드", "상품명", "판매가", "상품 배송 안내", "교환/반품 안내"]),
    ("channeltalk_userchats.csv", "채널톡 UserChat data 시트",
     ["id", "tags", "state", "createdAt", "profile.csat"]),
    ("channeltalk_messages.csv", "채널톡 Message data 시트",
     ["ChatId", "PersonType", "CreatedAt", "PlainText"]),
]


def step_ingest():
    import csv as _csv
    emit("stage_start", step="ingest", label="데이터 연결",
         detail="셀러가 실제로 내려받는 원본 파일을 그대로 읽는다")
    for fname, kind, expect in KNOWN_SCHEMAS:
        path = f"data/{fname}"
        rows = list(_csv.reader(open(path, encoding="utf-8-sig")))
        header, count = rows[0], len(rows) - 1
        matched = [c for c in expect if c in header]
        emit("file_detected", file=fname, kind=kind, rows=count,
             columns=header, matchedColumns=matched,
             schemaOk=len(matched) == len(expect))
    arts = _load("data/knowledge_articles.json")
    emit("file_detected", file="knowledge_articles.json", kind="ALF 지식 아티클",
         rows=len(arts), columns=[a["title"] for a in arts],
         matchedColumns=[], schemaOk=True)


def step_diagnose_and_emit(base, cand, reg):
    """LLM 자율 진단: 원인 분석과 수정안 제안. 적용 여부는 사람이 결정한다."""
    import llm
    orig = {a["id"]: a for a in _load("data/knowledge_articles.json")}
    changed = {a["id"]: a for a in _load("out/knowledge_changed.json")}
    diffs = [{"id": k, "title": orig[k]["title"], "before": orig[k]["body"],
              "after": changed[k]["body"]}
             for k in orig if orig[k]["body"] != changed.get(k, orig[k])["body"]]
    broken = [{"caseId": b["caseId"], "reason": b["reason"]} for b in reg["brokenCases"]]
    try:
        diag = llm.ask_json(
            "AI 상담 지식 변경 후 리그레션이 발생했다. 원인을 진단하고 수정안을 제안하라.\n"
            f"[변경된 아티클]\n{json.dumps(diffs, ensure_ascii=False)}\n"
            f"[깨진 케이스]\n{json.dumps(broken, ensure_ascii=False)}\n"
            f"[해결률] {base['summary']['resolutionRate']} 에서 {cand['summary']['resolutionRate']} 로\n\n"
            '{"rootCause": "원인 한두 문장, 대시 금지", "proposal": "수정 방향 한 문장", '
            '"articleId": "수정할 아티클 id", "patchedBody": "제안하는 아티클 본문 전체"} 형식 JSON만.')
        assert diag.get("articleId") in orig and diag.get("patchedBody")
    except Exception:
        diag = {"rootCause": "배송 안내 아티클에서 당일 출고 기준 문구가 삭제되어 출고 시각 질문에 답하지 못함",
                "proposal": "삭제된 출고 기준 문구를 복원한다",
                "articleId": "KA-01",
                "patchedBody": orig["KA-01"]["body"]}
    json.dump(diag, open("out/diagnosis.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    emit("diagnosis", diagnosis=diag,
         articleTitle=orig.get(diag["articleId"], {}).get("title", diag["articleId"]))


def do_step(step):
    try:
        if step == "ingest":
            step_ingest()
        elif step == "gen":
            if os.path.exists("out/cases-pinned.json"):
                emit("stage_start", step=step, label="케이스 생성",
                     detail="검증된 케이스 세트 재사용 (out/cases-pinned.json)")
                pinned = _load("out/cases-pinned.json")
                json.dump(pinned, open("out/cases.json", "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
                cases, coverage = pinned["cases"], pinned["coverage"]
            else:
                emit("stage_start", step=step, label="케이스 생성",
                     detail="상담 로그 120건 클러스터링, LLM 케이스 합성")
                import casegen
                cases, coverage = casegen.generate()
            emit("coverage", coverage=coverage)
            for c in cases:
                emit("case_created", case=c)
        elif step == "baseline":
            emit("stage_start", step=step, label="시뮬레이션과 감사 (변경 전)",
                 detail="가상 고객 12명과 동시 대화, 정책 원장 대조")
            _run_stage("run-baseline", "변경 전", "data/knowledge_articles.json")
        elif step == "change":
            emit("stage_start", step=step, label="지식 변경 감지",
                 detail="배송 안내 아티클 수정")
            import gate
            gate.step_change()
            emit("change", change=_load("out/change.json"))
        elif step == "candidate":
            emit("stage_start", step=step, label="자동 재검증 (변경 후)",
                 detail="변경 영향 범위를 산정해 해당 케이스만 재실행, 나머지는 변경 전 결과 유지")
            _run_stage_scoped("run-candidate", "변경 후", "out/knowledge_changed.json")
            import gate
            base = _load("out/run-baseline.json")
            cand = _load("out/run-candidate.json")
            reg = gate._regression(base, cand)
            json.dump(reg, open("out/regression.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            emit("regression", regression=reg,
                 baseSummary=base["summary"], candSummary=cand["summary"])
            if reg["recommendation"] == "hold":
                step_diagnose_and_emit(base, cand, reg)
        elif step == "fix":
            emit("stage_start", step=step, label="수정안 적용 후 재검증",
                 detail="사람 승인을 받은 제안을 적용하고 영향 케이스를 다시 돌린다")
            if not os.path.exists("out/diagnosis.json"):
                emit("stage_error", step=step, error="적용할 진단 제안이 없습니다. 게이트가 보류일 때만 생성됩니다")
                raise RuntimeError("no diagnosis")
            diag = _load("out/diagnosis.json")
            arts = _load("out/knowledge_changed.json")
            for a in arts:
                if a["id"] == diag["articleId"]:
                    a["body"] = diag["patchedBody"]
            json.dump(arts, open("out/knowledge_fixed.json", "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            fixed = _run_stage_scoped("run-fixed", "수정 후", "out/knowledge_fixed.json")
            import gate
            base = _load("out/run-baseline.json")
            reg2 = gate._regression(base, fixed)
            emit("regression", regression=reg2,
                 baseSummary=base["summary"], candSummary=fixed["summary"])
        elif step == "report":
            emit("stage_start", step=step, label="리포트 생성", detail="")
            import gate
            gate.step_report()
            emit("report_ready", url="/report")
        STATE["done_steps"].append(step)
        emit("stage_done", step=step)
    except Exception as e:
        emit("stage_error", step=step, error=str(e)[:200])
    finally:
        STATE["busy"] = False


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            html = open("app/demo.html", encoding="utf-8").read()
            self._send(200, html.encode(), "text/html; charset=utf-8")
        elif url.path == "/events":
            q = urllib.parse.parse_qs(url.query)
            since = int(q.get("since", ["0"])[0])
            with LOCK:
                out = EVENTS[since:since + 400]
            self._send(200, {"events": out, "busy": STATE["busy"],
                             "doneSteps": STATE["done_steps"]})
        elif url.path == "/report":
            if not os.path.exists("out/report.html"):
                self._send(404, {"error": "리포트가 아직 없습니다"})
                return
            self._send(200, open("out/report.html", encoding="utf-8").read().encode(),
                       "text/html; charset=utf-8")
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/reset":
            if STATE["busy"]:
                self._send(409, {"error": "실행 중에는 초기화할 수 없습니다"})
                return
            with LOCK:
                EVENTS.clear()
            STATE["done_steps"] = []
            self._send(200, {"ok": True})
        elif url.path == "/action":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            step = body.get("step")
            if step not in ("ingest", "gen", "baseline", "change", "candidate", "fix", "report"):
                self._send(400, {"error": "unknown step"})
                return
            if STATE["busy"]:
                self._send(409, {"error": "이미 실행 중입니다"})
                return
            STATE["busy"] = True
            threading.Thread(target=do_step, args=(step,), daemon=True).start()
            self._send(200, {"ok": True, "step": step})
        else:
            self._send(404, {"error": "not found"})


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"alf-gate 라이브 데모: http://localhost:{PORT}")
    server.serve_forever()
