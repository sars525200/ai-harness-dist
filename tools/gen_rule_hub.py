# -*- coding: utf-8 -*-
r"""從 `global/hub/` 模組產出 `global/CLAUDE.md` 與 `global/CURSOR_USER_RULES.md`。

    py -3 D:\Patrick-AI\.ai-harness\tools\gen_rule_hub.py            # 寫兩份產出
    py -3 D:\Patrick-AI\.ai-harness\tools\gen_rule_hub.py --check    # 不寫；不一致 exit 1

契約：票 03／04。產生器不准寫 mcp／skills／hooks／雲端 User Rules。
無時間戳。檔頭原文鎖在 GENERATED_HEADER。

【核心層】與被服務的專案無關。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HARNESS = Path(os.environ.get("GEN_RULE_HUB_ROOT") or Path(__file__).resolve().parent.parent)
HUB = HARNESS / "global" / "hub"
OUT_CLAUDE = HARNESS / "global" / "CLAUDE.md"
OUT_CURSOR = HARNESS / "global" / "CURSOR_USER_RULES.md"
LAYERS_PY = HARNESS / "dashboard" / "gen_layers.py"

GENERATED_HEADER = (
    "<!-- GENERATED FILE. Do not edit. -->\n"
    "<!-- Edit global/hub/ then: py -3 <harness>\\tools\\gen_rule_hub.py -->\n"
)

AUDIENCES = frozenset({"all", "claude", "cursor"})
CLAUDE_KEEP = frozenset({"all", "claude"})
CURSOR_KEEP = frozenset({"all", "cursor"})

UNAUTH_FILES = ("mcp.json", ".mcp.json")
UNAUTH_DIRS_REPO = ("skills", "hooks", os.path.join(".cursor", "skills"))
UNAUTH_DIRS_LIVE = ("skills", "hooks")


def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        blank = ln == ""
        if blank and prev_blank:
            continue
        out.append(ln)
        prev_blank = blank
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return ("\n".join(out) + "\n") if out else "\n"


def strip_generated_header(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if s == "":
            i += 1
            continue
        if s.startswith("<!--") and "-->" in s:
            i += 1
            continue
        if s.startswith("<!--"):
            i += 1
            while i < n and "-->" not in lines[i]:
                i += 1
            if i < n:
                i += 1
            continue
        break
    return "\n".join(lines[i:])


def parse_module(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        print(f"exit 2：{path} 缺 frontmatter", file=sys.stderr)
        sys.exit(2)
    rest = raw[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end < 0:
        print(f"exit 2：{path} frontmatter 沒有結尾 ---", file=sys.stderr)
        sys.exit(2)
    fm = rest[:end]
    body = rest[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    audience = None
    for ln in fm.split("\n"):
        if ln.strip().startswith("audience:"):
            audience = ln.split(":", 1)[1].strip()
    if audience not in AUDIENCES:
        print(
            f"exit 2：{path} audience 必須是 all／claude／cursor（小寫），得到 {audience!r}",
            file=sys.stderr,
        )
        sys.exit(2)
    return audience, body.rstrip() + "\n"


def load_modules() -> list[tuple[Path, str, str]]:
    if not HUB.is_dir():
        print(f"exit 2：找不到模組目錄 {HUB}", file=sys.stderr)
        sys.exit(2)
    paths = sorted(p for p in HUB.rglob("*.md") if p.is_file())
    if not paths:
        print(f"exit 2：{HUB} 沒有 .md 模組", file=sys.stderr)
        sys.exit(2)
    return [(p, *parse_module(p)) for p in paths]


def render(keep: frozenset[str], modules: list[tuple[Path, str, str]]) -> str:
    chunks = [body for _p, aud, body in modules if aud in keep]
    body = "\n".join(chunks)
    return GENERATED_HEADER + "\n" + body


def sha256_norm(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def git_head(rel: str) -> str | None:
    posix = rel.replace("\\", "/")
    r = subprocess.run(
        ["git", "show", f"HEAD:{posix}"],
        cwd=str(HARNESS),
        capture_output=True,
    )
    if r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", errors="replace")


def _walk_files(root: Path) -> set[Path]:
    out: set[Path] = set()
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            out.add(p.resolve())
    return out


def collect_unauth() -> set[Path]:
    found: set[Path] = set()
    live = Path.home() / ".claude"
    for name in UNAUTH_FILES:
        for root in (HARNESS, live):
            p = root / name
            if p.exists():
                found.add(p.resolve())
    for name in UNAUTH_DIRS_REPO:
        found |= _walk_files(HARNESS / name)
    for name in UNAUTH_DIRS_LIVE:
        found |= _walk_files(live / name)
    return found


def load_needles() -> list[str]:
    if os.environ.get("GEN_RULE_HUB_NEEDLES"):
        return [s for s in os.environ["GEN_RULE_HUB_NEEDLES"].split("|") if s]
    if not LAYERS_PY.exists():
        print(f"exit 2：找不到 {LAYERS_PY}，專案針標無從取得", file=sys.stderr)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("_gl_hub", LAYERS_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    harness = HARNESS.resolve()
    needles: list[str] = []
    for row in mod.survey_projects():
        raw = row.get("path") or ""
        name = row.get("name") or ""
        try:
            p = Path(raw).resolve()
        except OSError:
            p = Path(raw)
        if p == harness or name.casefold() == harness.name.casefold():
            continue
        if raw:
            needles.append(str(p))
            needles.append(str(p).replace("\\", "/"))
        if name:
            needles.append(name)
    return needles


def scan_needles(label: str, text: str, needles: list[str]) -> list[str]:
    hits = []
    for n in needles:
        if n and n in text:
            hits.append(f"{label} 含針標 {n!r}")
    return hits


def _classify_mismatch(rel: str, expected: str, wt: str | None) -> list[str]:
    if wt is None:
        return [f"{rel}：產出不存在"]
    exp_n, wt_n = normalize(expected), normalize(wt)
    if exp_n == wt_n:
        return []
    head = git_head(rel)
    if head is None:
        return [f"{rel}：模組與產出不一致"]
    head_n = normalize(head)
    msgs = []
    if wt_n == head_n and exp_n != head_n:
        msgs.append(f"{rel}：模組改了還沒重產")
    elif exp_n == head_n and wt_n != head_n:
        msgs.append(f"{rel}：有人手改產出檔")
    else:
        msgs.append(f"{rel}：模組改了還沒重產")
        msgs.append(f"{rel}：有人手改產出檔")
    return msgs


def cmd_check() -> int:
    modules = load_modules()
    exp_c = render(CLAUDE_KEEP, modules)
    exp_u = render(CURSOR_KEEP, modules)
    wt_c = OUT_CLAUDE.read_text(encoding="utf-8") if OUT_CLAUDE.exists() else None
    wt_u = OUT_CURSOR.read_text(encoding="utf-8") if OUT_CURSOR.exists() else None
    msgs: list[str] = []
    msgs += _classify_mismatch("global/CLAUDE.md", exp_c, wt_c)
    msgs += _classify_mismatch("global/CURSOR_USER_RULES.md", exp_u, wt_u)
    needles = load_needles()
    for label, text in (
        ("global/CLAUDE.md", exp_c),
        ("global/CURSOR_USER_RULES.md", exp_u),
    ):
        msgs += scan_needles(label, strip_generated_header(text), needles)
    if msgs:
        for m in msgs:
            print(m)
        return 1
    print("產出與模組一致，針標未命中。")
    return 0


BUDGET_PY = HARNESS / "rulefile" / "resident_budget.py"
BUDGET_STATE = HARNESS / "rulefile" / "state" / "genhub_budget_state.json"


def _load_budget():
    """載入常駐層預算判準。用檔案位置載入、不進 `sys.path`（同本檔載 gen_layers 的做法）。"""
    if not BUDGET_PY.exists():
        return None
    spec = importlib.util.spec_from_file_location("_resident_budget", str(BUDGET_PY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _budget_state() -> dict:
    try:
        return json.loads(BUDGET_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember_budget(key: str, size: int) -> None:
    """棘輪：記下叫過的大小，同一個大小不會叫第二次。寫失敗就算了——
    最壞情況是下次再叫一次，不是漏叫。"""
    st = _budget_state()
    st[key] = size
    try:
        BUDGET_STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = BUDGET_STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, BUDGET_STATE)
    except OSError:
        pass


def check_budget(out_c: str) -> tuple[list[str], bool]:
    """回 (訊息 list, 是否超標)。

    **「判不出來」要出聲但不算超標** —— 兩者分開回，是因為把它們混在一起會
    同時犯兩個錯：靜默通過（不知道當成沒事），或在沒有 harness 的沙箱裡
    無條件失敗（`tests/run_hook_tests.py` 的產生器測試就是這樣被咬的）。
    """
    rb = _load_budget()
    if rb is None:
        return (["⚠ 常駐層預算：找不到 rulefile/resident_budget.py，這次沒有量到。"], False)
    size = len(out_c.encode("utf-8"))
    v = rb.assess(size, rb.baseline_bytes(), _budget_state().get(rb.GLOBAL_KEY, 0))
    if not v["known"]:
        return (["⚠ 常駐層預算：快照裡沒有全域 CLAUDE.md 那一筆，這次判不出來。"], False)
    if not v["over"]:
        return ([], False)
    _remember_budget(rb.GLOBAL_KEY, size)
    return ([rb.message(v, "global/CLAUDE.md")], True)


def cmd_generate(allow_growth: bool = False) -> int:
    before = collect_unauth()
    modules = load_modules()
    out_c = render(CLAUDE_KEEP, modules)
    out_u = render(CURSOR_KEEP, modules)
    needles = load_needles()
    hits = scan_needles("global/CLAUDE.md", strip_generated_header(out_c), needles)
    hits += scan_needles("global/CURSOR_USER_RULES.md", strip_generated_header(out_u), needles)
    if hits:
        for m in hits:
            print(m)
        print("拒絕寫出：產出含專案針標。")
        return 1
    OUT_CLAUDE.parent.mkdir(parents=True, exist_ok=True)
    OUT_CLAUDE.write_text(out_c, encoding="utf-8", newline="\n")
    OUT_CURSOR.write_text(out_u, encoding="utf-8", newline="\n")
    after = collect_unauth()
    new = after - before
    if new:
        print("不越權：相對跑前基準新寫出了禁止路徑：")
        for p in sorted(new):
            print(f"  {p}")
        return 1
    print(f"已寫 {OUT_CLAUDE}")
    print(f"已寫 {OUT_CURSOR}")
    print(f"正規化雜湊 CLAUDE {sha256_norm(out_c)[:12]} CURSOR {sha256_norm(out_u)[:12]}")
    budget, over = check_budget(out_c)
    for m in budget:
        print(m)
    if over:
        if not allow_growth:
            # 大聲失敗但**檔已經寫了**：擋掉會逼人改用手動寫檔繞過去，那條路更沒人看得到。
            print("（這次成長是必要的就加 --allow-growth；理由要寫進 commit 訊息。）")
            return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="規則中繼產生器")
    ap.add_argument("--check", action="store_true", help="只比對不寫")
    ap.add_argument("--allow-growth", action="store_true",
                    help="常駐層超出預算時仍回 0（檔本來就會寫；這個旗標只關掉 exit 1）")
    a = ap.parse_args()
    if a.check:
        return cmd_check()
    return cmd_generate(allow_growth=a.allow_growth)


if __name__ == "__main__":
    sys.exit(main())
