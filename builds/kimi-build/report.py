# -*- coding: utf-8 -*-
"""단일 파일 HTML 리포트 생성. 외부 CDN 없음, 한국어 UI."""

TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ALF 세팅 게이트 · 사전 검증 리포트</title>
<style>
:root{
  --bg:#f7f6f3; --card:#ffffff; --ink:#1a1c21; --sub:#6d7280; --faint:#9aa0ad;
  --line:#e8e5de; --line2:#f0eee8;
  --brand:#5b4bd4; --brand-ink:#4338b8; --brand-soft:#efedfb;
  --ok:#1e9e62; --ok-soft:#e4f4ec;
  --bad:#e0454f; --bad-soft:#fcebeb;
  --warn:#c07a12; --warn-soft:#fbf1de;
  --mono:ui-monospace,"SF Mono","Pretendard",Menlo,monospace;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  background:var(--bg); color:var(--ink);
  font-family:"Pretendard Variable","Pretendard",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif;
  font-size:15px; line-height:1.6; -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1060px;margin:0 auto;padding:0 28px 120px}
.num{font-family:var(--mono); font-variant-numeric:tabular-nums}

/* 헤더 */
header{padding:52px 0 34px;border-bottom:1px solid var(--line);margin-bottom:34px}
.eyebrow{display:flex;align-items:center;gap:10px;margin-bottom:16px}
.mark{width:26px;height:26px;border-radius:8px;background:linear-gradient(135deg,#6d5ef0,#4338b8);box-shadow:0 2px 8px rgba(91,75,212,.35)}
.eyebrow span{font-size:13px;font-weight:700;letter-spacing:.14em;color:var(--brand-ink)}
h1{font-size:34px;font-weight:800;letter-spacing:-.03em;line-height:1.25}
.sub{color:var(--sub);margin-top:10px;font-size:15.5px;max-width:640px}
.meta{display:flex;flex-wrap:wrap;gap:8px;margin-top:20px}
.meta .chip{background:var(--card);border:1px solid var(--line);color:var(--sub);font-size:12.5px;padding:5px 12px;border-radius:999px}
.chip.syn{background:var(--warn-soft);border-color:#eed9b4;color:var(--warn);font-weight:700}

/* 게이트 배너 */
.gate{border-radius:18px;padding:26px 30px;margin-bottom:36px;border:1px solid;display:flex;gap:20px;align-items:flex-start}
.gate.hold{background:linear-gradient(180deg,#fff8f0,#fdf1e3);border-color:#efd9b5}
.gate.pass{background:linear-gradient(180deg,#f2faf5,#e4f4ec);border-color:#bfe3cf}
.gate .icon{width:44px;height:44px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;flex:none}
.gate.hold .icon{background:#f3d9a8}.gate.pass .icon{background:#bfe3cf}
.gate h2{font-size:20px;font-weight:800;letter-spacing:-.02em}
.gate p{color:var(--sub);margin-top:6px;font-size:14.5px}
.gate .reasons{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.gate .reason{background:#fff;border:1px solid #eed9b4;color:var(--warn);font-size:12.5px;font-weight:600;padding:4px 11px;border-radius:999px}
.gate.pass .reason{border-color:#bfe3cf;color:var(--ok)}

/* 섹션 공통 */
section{margin-bottom:52px}
.sec-head{display:flex;align-items:baseline;gap:12px;margin-bottom:18px}
.sec-head .no{font-family:var(--mono);font-size:13px;color:var(--brand);font-weight:700}
.sec-head h2{font-size:20px;font-weight:800;letter-spacing:-.02em}
.sec-head .desc{color:var(--faint);font-size:13px;margin-left:auto}

/* KPI */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px 22px}
.kpi .label{font-size:12.5px;color:var(--sub);font-weight:600;margin-bottom:10px}
.kpi .value{font-size:32px;font-weight:800;letter-spacing:-.03em;font-family:var(--mono)}
.kpi .value small{font-size:16px;color:var(--faint);font-weight:600}
.kpi .foot{font-size:12.5px;margin-top:8px;color:var(--sub)}
.kpi .foot.up{color:var(--ok)}.kpi .foot.down{color:var(--bad)}

/* 커버리지 */
.cov{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px 26px}
.cov-row{display:grid;grid-template-columns:110px 1fr 76px;gap:14px;align-items:center;padding:9px 0;border-bottom:1px solid var(--line2)}
.cov-row:last-child{border-bottom:none}
.cov-row .tag{font-size:13.5px;font-weight:600}
.cov-row .tag .miss{color:var(--warn);font-size:11.5px;font-weight:700;margin-left:6px;border:1px solid #eed9b4;border-radius:6px;padding:1px 6px;background:var(--warn-soft)}
.bar{height:10px;border-radius:6px;background:var(--line2);overflow:hidden}
.bar i{display:block;height:100%;border-radius:6px;background:var(--brand)}
.cov-row.missed .bar i{background:repeating-linear-gradient(45deg,#f0cf9a,#f0cf9a 5px,#f7e3c2 5px,#f7e3c2 10px)}
.cov-row .cnt{text-align:right;font-size:13px;color:var(--sub);font-family:var(--mono)}
.cov-next{margin-top:16px;padding:13px 16px;background:var(--brand-soft);border-radius:12px;font-size:13.5px;color:var(--brand-ink)}
.cov-next b{font-weight:800}

/* 감사 요약 */
.audit-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}
.audit{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px}
.audit.hot{border-color:#f2c4c8;background:linear-gradient(180deg,#fff,#fdf3f4)}
.audit .cat{font-size:13px;font-weight:700;color:var(--sub)}
.audit.hot .cat{color:var(--bad)}
.audit .n{font-size:28px;font-weight:800;font-family:var(--mono);margin-top:6px}
.audit .ev{font-size:12px;color:var(--sub);margin-top:8px;line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.note{font-size:13px;color:var(--sub);background:var(--card);border:1px dashed var(--line);border-radius:12px;padding:12px 16px}

/* 케이스 */
.case{background:var(--card);border:1px solid var(--line);border-radius:16px;margin-bottom:14px;overflow:hidden}
.case summary{list-style:none;cursor:pointer;padding:18px 22px;display:flex;align-items:center;gap:14px}
.case summary::-webkit-details-marker{display:none}
.case summary:hover{background:#fbfaf7}
.case .cid{font-family:var(--mono);font-size:12px;font-weight:700;color:var(--brand);background:var(--brand-soft);border-radius:8px;padding:4px 9px;flex:none}
.case .ct{font-weight:700;font-size:15.5px}
.case .ctag{font-size:12px;color:var(--faint);margin-left:2px}
.pill{font-size:11.5px;font-weight:700;border-radius:999px;padding:4px 11px;flex:none}
.pill.ok{background:var(--ok-soft);color:var(--ok)}
.pill.no{background:#f1f2f4;color:var(--sub)}
.pill.bad{background:var(--bad-soft);color:var(--bad)}
.pill.cx{background:var(--brand-soft);color:var(--brand-ink)}
.case .arrow{margin-left:auto;color:var(--faint);transition:transform .2s;flex:none}
.case[open] .arrow{transform:rotate(180deg)}
.case-body{border-top:1px solid var(--line2);padding:22px;display:grid;grid-template-columns:300px 1fr;gap:26px}
.field{margin-bottom:16px}
.field .fl{font-size:11.5px;font-weight:700;letter-spacing:.08em;color:var(--faint);margin-bottom:5px}
.field .fv{font-size:13.5px;color:var(--ink)}
.crit{list-style:none;margin-top:2px}
.crit li{font-size:13px;padding:5px 0 5px 24px;position:relative;color:var(--sub)}
.crit li::before{content:"";position:absolute;left:0;top:8px;width:16px;height:16px;border-radius:50%;background:#f1f2f4;color:#fff;font-size:10px;line-height:16px;text-align:center}
.crit li.ok{color:var(--ink)}
.crit li.ok::before{background:var(--ok);content:"✓"}
.crit li.no::before{background:var(--bad);content:"✕"}

/* 대화 */
.chat{display:flex;flex-direction:column;gap:10px}
.msg{max-width:86%;padding:11px 15px;border-radius:16px;font-size:13.8px;line-height:1.65;position:relative}
.msg .who{display:block;font-size:11px;font-weight:700;margin-bottom:4px;letter-spacing:.04em}
.msg.c{align-self:flex-start;background:#f2f1ec;border-bottom-left-radius:5px}
.msg.c .who{color:var(--sub)}
.msg.a{align-self:flex-end;background:var(--brand-soft);border-bottom-right-radius:5px}
.msg.a .who{color:var(--brand-ink)}
.msg.a.viol{outline:2px solid var(--bad);outline-offset:-2px;background:#fdf0f0}
.msg.a.viol::after{content:"위반";position:absolute;top:-9px;right:10px;background:var(--bad);color:#fff;font-size:10px;font-weight:800;border-radius:6px;padding:2px 8px}
mark{background:#ffd9db;color:#a11d26;border-radius:4px;padding:0 3px;font-weight:600}

/* 위반 증거 */
.viol-box{margin-top:16px;border:1px solid #f2c4c8;background:#fdf6f6;border-radius:12px;padding:14px 16px}
.viol-box .vh{font-size:12px;font-weight:800;color:var(--bad);letter-spacing:.06em;margin-bottom:8px}
.viol-item{padding:9px 0;border-top:1px dashed #f0d5d8;font-size:13px}
.viol-item:first-of-type{border-top:none}
.viol-item .vc{display:inline-block;font-size:11px;font-weight:800;color:var(--bad);background:var(--bad-soft);border-radius:6px;padding:2px 8px;margin-right:8px}
.viol-item .vs{font-size:11px;color:var(--faint);margin-left:6px}
.viol-item .ve{color:var(--ink);margin:6px 0 4px;font-size:13.5px}
.viol-item .vr{color:var(--sub);font-size:12.5px}
.judge{margin-top:14px;background:var(--brand-soft);border-radius:12px;padding:12px 16px;font-size:13px;color:var(--brand-ink)}
.judge b{font-weight:800}

/* 리그레션 */
.reg{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px 26px}
.diff{border-radius:12px;overflow:hidden;border:1px solid var(--line);margin-bottom:20px}
.diff .row{display:grid;grid-template-columns:52px 1fr;font-size:13.5px}
.diff .row span{padding:10px 14px}
.diff .row .sig{font-weight:800;text-align:center;font-family:var(--mono)}
.diff .del{background:#fdf1f1}.diff .del .sig{background:#f8d7d9;color:var(--bad)}
.diff .add{background:#eef8f2;border-top:1px solid var(--line)}.diff .add .sig{background:#d3ecdd;color:var(--ok)}
.reg-bars{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.reg-bar .rl{font-size:12.5px;color:var(--sub);font-weight:600;margin-bottom:8px;display:flex;justify-content:space-between}
.reg-bar .rl b{font-family:var(--mono);color:var(--ink)}
.reg-bar .bar{height:14px}
.reg-bar.before .bar i{background:#c9c4ee}
.reg-bar.after .bar i{background:var(--bad)}
.reg-table{width:100%;border-collapse:collapse;font-size:13.5px}
.reg-table th{text-align:left;font-size:11.5px;letter-spacing:.08em;color:var(--faint);padding:8px 10px;border-bottom:1px solid var(--line)}
.reg-table td{padding:10px;border-bottom:1px solid var(--line2)}
.reg-table tr:last-child td{border-bottom:none}
.delta{font-family:var(--mono);font-weight:700}
.delta.down{color:var(--bad)}
.delta.flat{color:var(--sub)}

footer{border-top:1px solid var(--line);padding-top:26px;color:var(--faint);font-size:12.5px}
.pipeline{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.pipeline span{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:5px 11px;font-weight:600;color:var(--sub)}
.pipeline i{color:var(--line);font-style:normal;align-self:center}

@media(max-width:860px){
  .kpis,.audit-grid{grid-template-columns:repeat(2,1fr)}
  .case-body{grid-template-columns:1fr}
  .reg-bars{grid-template-columns:1fr}
}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script>
const DATA = __DATA__;

const $ = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};
const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const pct = v => Math.round(v * 100);

/* ---------- 헤더 ---------- */
const app = document.getElementById("app");
const M = DATA.meta;

app.appendChild((() => {
  const h = $("header");
  h.appendChild($("div","eyebrow")).appendChild($("div","mark"));
  h.querySelector(".eyebrow").appendChild($("span",null,"ALF SETTING GATE"));
  h.appendChild($("h1",null,"세팅 게이트 사전 검증 리포트"));
  h.appendChild($("p","sub","과거 문의 로그에서 생성한 테스트 케이스로 상담 AI를 시뮬레이션하고, 약속 감사 4축으로 채점한 뒤, 지식 변경의 리그레션을 자동 재실행한 결과입니다."));
  const meta = $("div","meta");
  [["실행",M.run_at],["소요",M.duration],["모델",M.model],["케이스",M.cases+"건"],["문의 로그",M.logs+"건"]].forEach(([k,v])=>{
    meta.appendChild($("span","chip", k+" <b class='num'>"+esc(v)+"</b>"));
  });
  meta.appendChild($("span","chip syn","SYNTHETIC 데이터"));
  h.appendChild(meta);
  return h;
})());

/* ---------- 게이트 배너 ---------- */
const G = DATA.gate;
app.appendChild((() => {
  const g = $("div","gate "+(G.hold?"hold":"pass"));
  g.appendChild($("div","icon", G.hold?"⏸":"▶"));
  const body = $("div");
  body.appendChild($("h2",null, G.hold ? "게이트 판정: 배포 보류 권고" : "게이트 판정: 배포 승인 가능"));
  body.appendChild($("p",null, esc(G.summary)));
  const rs = $("div","reasons");
  G.reasons.forEach(r => rs.appendChild($("span","reason",esc(r))));
  body.appendChild(rs);
  g.appendChild(body);
  return g;
})());

/* ---------- KPI ---------- */
const K = DATA.kpi;
app.appendChild((() => {
  const s = $("section");
  s.appendChild($("div","sec-head")).innerHTML =
    "<span class='no'>01</span><h2>핵심 지표</h2><span class='desc'>배포 전 예상 수치</span>";
  const grid = $("div","kpis");
  const items = [
    ["예상 해결률", K.resolved_rate+"<small>%</small>", K.resolved_n+" / "+K.cases+" 케이스 해결", ""],
    ["약속 위반", String(K.violations)+"<small>건</small>", K.violated_cases+"개 케이스에서 감지", K.violations? "down":"up"],
    ["로그 커버리지", K.coverage+"<small>%</small>", "미커버 유형 "+K.uncovered+"개", ""],
    ["Δ 해결률", (K.delta>0?"+":"")+K.delta+"<small>%p</small>", "지식 변경 재실행 기준", K.delta<0?"down":"up"],
  ];
  items.forEach(([l,v,f,c])=>{
    const k = $("div","kpi");
    k.appendChild($("div","label",l));
    k.appendChild($("div","value num",v));
    k.appendChild($("div","foot "+c,f));
    grid.appendChild(k);
  });
  s.appendChild(grid);
  return s;
})());

/* ---------- 커버리지 ---------- */
const C = DATA.coverage;
app.appendChild((() => {
  const s = $("section");
  s.appendChild($("div","sec-head")).innerHTML =
    "<span class='no'>02</span><h2>커버리지 맵</h2><span class='desc'>과거 문의 유형 대비 케이스 생성률</span>";
  const box = $("div","cov");
  const max = Math.max(...C.by_tag.map(t=>t.count));
  C.by_tag.forEach(t=>{
    const row = $("div","cov-row"+(t.covered?"":" missed"));
    row.appendChild($("div","tag", esc(t.tag)+(t.covered?"":"<span class='miss'>미커버</span>")));
    const bar = $("div","bar"); const i = $("i");
    i.style.width = Math.max(4, pct(t.count/max))+"%";
    bar.appendChild(i); row.appendChild(bar);
    row.appendChild($("div","cnt", t.count+"건"));
    box.appendChild(row);
  });
  const next = $("div","cov-next",
    "<b>다음 세팅 후보</b> · 미커버 유형 "+C.uncovered.map(u=>esc(u.tag)+"("+u.count+"건)").join(", ")+
    " · 케이스 "+DATA.meta.cases+"개가 전체 로그의 "+pct(C.rate)+"%를 커버합니다.");
  box.appendChild(next);
  s.appendChild(box);
  return s;
})());

/* ---------- 약속 감사 요약 ---------- */
const A = DATA.audit;
app.appendChild((() => {
  const s = $("section");
  s.appendChild($("div","sec-head")).innerHTML =
    "<span class='no'>03</span><h2>약속 감사</h2><span class='desc'>품질 점수와 별개인 리스크 4축</span>";
  const grid = $("div","audit-grid");
  A.categories.forEach(c=>{
    const a = $("div","audit"+(c.count?" hot":""));
    a.appendChild($("div","cat",esc(c.name)));
    a.appendChild($("div","n",String(c.count)));
    a.appendChild($("div","ev", c.example ? "“"+esc(c.example)+"”" : "감지 없음"));
    grid.appendChild(a);
  });
  s.appendChild(grid);
  if (A.hidden_note) s.appendChild($("div","note", esc(A.hidden_note)));
  return s;
})());

/* ---------- 케이스 상세 ---------- */
app.appendChild((() => {
  const s = $("section");
  s.appendChild($("div","sec-head")).innerHTML =
    "<span class='no'>04</span><h2>테스트 케이스 상세</h2><span class='desc'>ALF 테스트 포맷(목표·성공 기준·페르소나) 호환</span>";
  DATA.cases.forEach(cs=>{
    const d = $("details","case");
    const sum = $("summary");
    sum.appendChild($("span","cid",cs.id));
    const t = $("span","ct", esc(cs.title)+" <span class='ctag'>"+esc(cs.tag)+"</span>");
    sum.appendChild(t);
    sum.appendChild($("span","pill "+(cs.resolved?"ok":"no"), cs.resolved?"해결":"미해결"));
    if (cs.violations.length) sum.appendChild($("span","pill bad","위반 "+cs.violations.length));
    sum.appendChild($("span","pill cx","CX "+cs.cx_score));
    sum.appendChild($("span","arrow","▾"));
    d.appendChild(sum);

    const body = $("div","case-body");
    const left = $("div");
    const fields = [["페르소나",cs.persona],["고객 목표",cs.goal],["근거 유형 로그",cs.log_count+"건"]];
    fields.forEach(([l,v])=>{
      const f = $("div","field");
      f.appendChild($("div","fl",l));
      f.appendChild($("div","fv",esc(v)));
      left.appendChild(f);
    });
    const f = $("div","field");
    f.appendChild($("div","fl","성공 기준"));
    const ul = $("ul","crit");
    cs.required.forEach(r=>{
      ul.appendChild($("li", r.ok?"ok":"no", esc(r.label)));
    });
    f.appendChild(ul); left.appendChild(f);
    body.appendChild(left);

    const right = $("div");
    const chat = $("div","chat");
    const violTurns = {};
    cs.violations.forEach(v=>{ if (v.turn>=0) (violTurns[v.turn]=violTurns[v.turn]||[]).push(v); });
    cs.transcript.forEach((t,i)=>{
      const m = $("div","msg "+(t.role==="customer"?"c":"a")+(violTurns[i]?" viol":""));
      let txt = esc(t.text);
      (violTurns[i]||[]).forEach(v=>{
        const ev = esc(v.evidence);
        const needle = ev.length>40 ? ev.slice(0,40) : ev;
        if (txt.includes(needle)) txt = txt.replace(needle,"<mark>"+needle+"</mark>");
      });
      m.innerHTML = "<span class='who'>"+(t.role==="customer"?esc(cs.persona_name):"상담 AI")+"</span>"+txt;
      chat.appendChild(m);
    });
    right.appendChild(chat);

    if (cs.violations.length){
      const vb = $("div","viol-box");
      vb.appendChild($("div","vh","약속 위반 증거 "+cs.violations.length+"건"));
      cs.violations.forEach(v=>{
        const it = $("div","viol-item");
        it.appendChild($("span","vc",esc(v.category)));
        it.appendChild($("span","vs",v.source==="AI"?"AI 판정":"결정론 룰"));
        it.appendChild($("div","ve","“"+esc(v.evidence)+"”"));
        it.appendChild($("div","vr",esc(v.reason)));
        vb.appendChild(it);
      });
      right.appendChild(vb);
    }
    if (cs.judge_reason) right.appendChild($("div","judge","<b>AI 채점 근거</b> · "+esc(cs.judge_reason)));
    body.appendChild(right);
    d.appendChild(body);
    s.appendChild(d);
  });
  return s;
})());

/* ---------- 리그레션 ---------- */
const R = DATA.regression;
app.appendChild((() => {
  const s = $("section");
  s.appendChild($("div","sec-head")).innerHTML =
    "<span class='no'>05</span><h2>리그레션 게이트</h2><span class='desc'>지식 변경 감지 시 자동 재실행</span>";
  const box = $("div","reg");
  const diff = $("div","diff");
  R.removed.forEach(t=>{
    const r = $("div","row del");
    r.appendChild($("span","sig","−"));
    r.appendChild($("span",null,esc(t)));
    diff.appendChild(r);
  });
  R.added.forEach(t=>{
    const r = $("div","row add");
    r.appendChild($("span","sig","+"));
    r.appendChild($("span",null,esc(t)));
    diff.appendChild(r);
  });
  box.appendChild($("div","fl","변경된 지식 · "+esc(R.article)));
  box.appendChild(diff);

  const bars = $("div","reg-bars");
  [["before","변경 전 해결률",R.before_rate],["after","변경 후 해결률",R.after_rate]].forEach(([cls,l,v])=>{
    const b = $("div","reg-bar "+cls);
    b.appendChild($("div","rl",l+"<b>"+v+"%</b>"));
    const bar = $("div","bar"); const i = $("i"); i.style.width = v+"%";
    bar.appendChild(i); b.appendChild(bar);
    bars.appendChild(b);
  });
  box.appendChild(bars);

  const tbl = $("table","reg-table");
  tbl.innerHTML = "<tr><th>재실행 케이스</th><th>변경 전</th><th>변경 후</th><th>변화</th></tr>";
  R.rows.forEach(r=>{
    const tr = $("tr");
    tr.appendChild($("td",null,"<b>"+r.id+"</b> "+esc(r.title)));
    tr.appendChild($("td",null,r.before));
    tr.appendChild($("td",null,r.after));
    tr.appendChild($("td","delta "+(r.broken?"down":"flat"), esc(r.delta)));
    tbl.appendChild(tr);
  });
  box.appendChild(tbl);
  box.appendChild($("div","note", esc(R.verdict)));
  s.appendChild(box);
  return s;
})());

/* ---------- 푸터 ---------- */
app.appendChild((() => {
  const f = $("footer");
  const p = $("div","pipeline");
  ["합성 데이터","케이스 자동 생성","시뮬레이션","약속 감사","리그레션 게이트","사람 승인"].forEach((s,i)=>{
    if (i) p.appendChild($("i",null,"→"));
    p.appendChild($("span",null,s));
  });
  f.appendChild(p);
  f.appendChild($("div",null,"본 리포트의 상품·문의·지식·대화는 모두 SYNTHETIC 합성 데이터입니다. 생성된 케이스는 채널톡 ALF 테스트의 케이스 포맷(목표, 성공 기준, 페르소나)과 필드가 호환됩니다."));
  return f;
})());
</script>
</body>
</html>
"""


def render(path, payload):
    import json
    html = TEMPLATE.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
