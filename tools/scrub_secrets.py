#!/usr/bin/env python3
"""Scrub secrets from submission logs (logs/**/*.jsonl).

Replaces secret values with "[REDACTED:secret]" without touching anything else.
Secrets are collected at runtime from local config files (never hardcoded here)
plus generic token-shaped regex patterns. Never prints secret values.

Usage: python3 tools/scrub_secrets.py   (run again at 12:10 after final log collection)
"""
import json
import os
import re
import sys

PLACEHOLDER = "[REDACTED:secret]"
MIN_LEN = 12  # ignore short strings to avoid false positives

GENERIC_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?<=Bearer )[A-Za-z0-9._~+/=\-]{16,}"),
    re.compile(r"(?<=Bearer\\u0020)[A-Za-z0-9._~+/=\-]{16,}"),  # unicode-escaped space in jsonl
]


def collect_secrets() -> set:
    home = os.path.expanduser("~")
    secrets = set()

    # ~/.codex/config.toml — any Authorization bearer values and inline api keys
    codex_cfg = os.path.join(home, ".codex", "config.toml")
    if os.path.isfile(codex_cfg):
        text = open(codex_cfg, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r'Bearer\s+([A-Za-z0-9._~+/=\-]{%d,})' % MIN_LEN, text):
            secrets.add(m.group(1))
        for m in re.finditer(r'(?i)(?:api_?key|token|secret)"?\s*=\s*"([^"]{%d,})"' % MIN_LEN, text):
            secrets.add(m.group(1))

    # ~/.claude-kimi/settings.json and ~/.claude/settings.json — env keys
    for rel in (".claude-kimi/settings.json", ".claude/settings.json"):
        p = os.path.join(home, rel)
        if os.path.isfile(p):
            try:
                env = json.load(open(p, encoding="utf-8")).get("env", {}) or {}
                for k, v in env.items():
                    if isinstance(v, str) and len(v) >= MIN_LEN and re.search(
                        r"(?i)key|token|secret", k
                    ):
                        secrets.add(v)
            except Exception:
                pass

    return {s for s in secrets if len(s) >= MIN_LEN}


def scrub_text(text: str, secrets: set) -> tuple:
    count = 0
    for s in sorted(secrets, key=len, reverse=True):
        for variant in (s, json.dumps(s)[1:-1]):  # raw + json-escaped
            if variant and variant in text:
                count += text.count(variant)
                text = text.replace(variant, PLACEHOLDER)
    for pat in GENERIC_PATTERNS:
        text, n = pat.subn(PLACEHOLDER, text)
        count += n
    return text, count


def main() -> int:
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
    root = os.path.normpath(root)
    if not os.path.isdir(root):
        print(f"scrub: no logs dir at {root}", file=sys.stderr)
        return 1
    secrets = collect_secrets()
    total_files = 0
    total_hits = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if not name.endswith((".jsonl", ".json", ".txt", ".md", ".log")):
                continue
            path = os.path.join(dirpath, name)
            raw = open(path, encoding="utf-8", errors="replace").read()
            cleaned, hits = scrub_text(raw, secrets)
            if hits:
                open(path, "w", encoding="utf-8").write(cleaned)
                total_files += 1
                total_hits += hits
                print(f"scrubbed {hits:3d} occurrence(s): {os.path.relpath(path, os.path.dirname(root))}")
    print(f"done: {total_hits} occurrence(s) across {total_files} file(s); {len(secrets)} known secret value(s) loaded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
