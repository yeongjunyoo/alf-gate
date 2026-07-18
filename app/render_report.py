#!/usr/bin/env python3
"""report.json을 template.html에 주입해 단일 HTML 리포트를 생성한다.

사용법: python3 app/render_report.py <report.json> <out.html>
"""
import json
import os
import sys


def main():
    if len(sys.argv) != 3:
        print("사용법: python3 app/render_report.py <report.json> <out.html>", file=sys.stderr)
        sys.exit(1)

    report_path, out_path = sys.argv[1], sys.argv[2]
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)
    report_json = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    if "__REPORT_JSON__" not in template:
        print("오류: template.html에 __REPORT_JSON__ 자리표시자가 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 스크립트 인젝션 방지: "</" 를 "<\/" 로 이스케이프
    safe_json = report_json.replace("</", "<\\/")

    html = template.replace("__REPORT_JSON__", safe_json)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print("생성 완료: " + out_path)


if __name__ == "__main__":
    main()
