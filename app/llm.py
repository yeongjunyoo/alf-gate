"""LLM adapter: shells out to the local `claude` CLI (already authenticated).

No API keys in code or logs. Runs with cwd=/tmp so project hooks don't fire
for internal product calls. Supports parallel calls via ThreadPoolExecutor.
"""
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 120

# 백엔드 체인: 한도 초과나 장애 시 다음으로 넘어간다. 성공한 백엔드를 기억한다.
BACKENDS = [
    ("claude", ["--model", "sonnet"]),
    ("claude", ["--model", "haiku"]),
    ("claude-kimi", []),
]



def ask(prompt: str, system: str = "", retries: int = 1) -> str:
    """Single LLM call -> plain text. Falls through backend chain on failure."""
    last = None
    for bi in range(len(BACKENDS)):
        binary, extra = BACKENDS[bi]
        for attempt in range(retries + 1):
            cmd = [binary, "-p", "--max-turns", "1"] + extra
            if system:
                cmd += ["--append-system-prompt", system]
            try:
                proc = subprocess.run(
                    cmd, input=prompt, capture_output=True, text=True,
                    timeout=TIMEOUT, cwd="/tmp"
                )
            except subprocess.TimeoutExpired:
                last = f"{binary} timeout"
                continue
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
            last = f"{binary} rc={proc.returncode}: {(proc.stderr or proc.stdout)[:200]}"
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"llm call failed {last}")


def ask_json(prompt: str, system: str = ""):
    """LLM call that must return JSON. Extracts the first JSON object/array."""
    out = ask(prompt + "\n\nJSON만 출력하라. 마크다운 코드펜스 금지.", system)
    m = re.search(r"[\[{].*[\]}]", out, re.S)
    if not m:
        raise RuntimeError(f"no JSON in LLM output: {out[:200]}")
    return json.loads(m.group(0))


def ask_many(prompts, system: str = "", workers: int = 8):
    """Parallel ask(); returns list aligned with prompts. Exceptions -> None."""
    def _safe(p):
        try:
            return ask(p, system)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(_safe, prompts))
