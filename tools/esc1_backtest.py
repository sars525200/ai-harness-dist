# -*- coding: utf-8 -*-
"""ESC-1 v4 判準的歷史回測（§9.6 動工第三步）。

母體＝`esc1_corpus.py` 萃取出的 51 份（36 真需求／10 無／5 提及），
ground truth 以 subagent transcript 的最終回報為準。

測的是 **v4 §9.3-A 的判準**：
  ① 資料源＝主 transcript 的兩個位置（sync `toolUseResult.content`／
     async `<task-notification>` 的 `<result>`）
  ② 比對法＝剝掉行首 `#`／`*`／空白後必須以標記開頭（排除敘述句提及）
  ③ 排除「無」

同時對照三個較差的判準，證明每一條設計決策各買到多少：
  A 子字串（v3 用的）  B lstrip+startswith（v3 §9.5 指定的）  C v4 完整

唯讀。用法：py -3 -X utf8 esc1_backtest.py
"""
import json
import pathlib
import re
import sys

# U-1：不寫死使用者路徑 —— 從 home 推導，換機器／換人照樣成立。
# （`test_harness_config` 的 F-4 閘門掃到 harness 底下的新檔就會擋，而它 2026-08-22 確實擋下了這兩支的第一版。）
PROJ = pathlib.Path.home() / ".claude" / "projects"
MARK = "【需要但沒有】"
NEG = re.compile(r"^[\s：:＝=—\-*_）)】]*(無|沒有|不適用|N/?A|none)", re.I)
WRAP = " \t#*_>-"


# ── ground truth（與 esc1_corpus.py 同一套判定） ───────────────────────
def last_assistant_text(path):
    last = ""
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"assistant"' not in ln:
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("type") != "assistant":
                continue
            c = (d.get("message") or {}).get("content")
            if not isinstance(c, list):
                continue
            t = "\n".join(b.get("text", "") for b in c
                          if isinstance(b, dict) and b.get("type") == "text")
            if t.strip():
                last = t
    except OSError:
        pass
    return last


def truth_of(text):
    """回傳 '真需求' / '無' / '提及'（檔案層：任一行真需求即真需求）。"""
    seen = set()
    for ln in text.splitlines():
        if MARK not in ln:
            continue
        s = ln.lstrip(WRAP)
        if not s.startswith(MARK):
            seen.add("提及")
        elif NEG.match(s[len(MARK):]):
            seen.add("無")
        else:
            seen.add("真需求")
    if "真需求" in seen:
        return "真需求"
    return "無" if "無" in seen else "提及"


# ── 三種判準 ──────────────────────────────────────────────────────────
def crit_A(text):                       # v3：純子字串
    return MARK in text


def crit_B(text):                       # v3 §9.5 指定：lstrip + startswith
    return any(ln.lstrip().startswith(MARK) for ln in text.splitlines())


def crit_C(text):                       # v4：剝 markdown 包裹 ＋ 排除「無」
    for ln in text.splitlines():
        s = ln.lstrip(WRAP)
        if s.startswith(MARK) and not NEG.match(s[len(MARK):]):
            return True
    return False


# ── 主 transcript 側：v4 §9.3-A① 的兩個位置 ──────────────────────────
def _walk_strings(obj):
    """遞迴吐出物件裡所有字串值（已解析＝未跳脫）。"""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def main_transcript_report(main_path, agent_id):
    """回傳主 transcript 裡看得到的該 agent 回報文字（兩個位置都找）。"""
    found = []
    try:
        raw = main_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if agent_id not in raw:
        return ""
    for ln in raw.splitlines():
        if agent_id not in ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        # 位置 1：sync 的 toolUseResult.content
        r = d.get("toolUseResult")
        if isinstance(r, dict) and r.get("agentId") == agent_id:
            c = r.get("content")
            if isinstance(c, list):
                found += [b.get("text", "") for b in c
                          if isinstance(b, dict) and b.get("type") == "text"]
        # 位置 2：async 的 <task-notification> 的 <result>
        # ⚠ 不可以走 json.dumps 再 regex —— 那樣取到的是**跳脫過**的字串
        #   （換行是字面的 \n），splitlines() 切不開，所有行首比對會靜默失效。
        #   回測第一版就是這樣把召回從 36 壓到 6 的。要走**已解析**的物件。
        for s in _walk_strings(d):
            if "task-notification" not in s or agent_id not in s:
                continue
            for m in re.findall(r"<result>(.*?)</result>", s, re.S):
                found.append(m)
    return "\n".join(found)


def main():
    # 1) 建 ground truth
    corpus = []
    for p in PROJ.rglob("agent-*.jsonl"):
        txt = last_assistant_text(p)
        if MARK not in txt:
            continue
        agent_id = p.stem.replace("agent-", "")
        main_path = p.parent.parent.parent / f"{p.parent.parent.name}.jsonl"
        corpus.append((agent_id, truth_of(txt), main_path))

    print(f"母體 {len(corpus)} 份")
    gt = {}
    for _, k, _ in corpus:
        gt[k] = gt.get(k, 0) + 1
    print("ground truth：", "　".join(f"{k} {v}" for k, v in sorted(gt.items())))
    print()

    # 2) 可達性：主 transcript 看不看得到
    reach = {"看得到": 0, "看不到": 0}
    for aid, _, mp in corpus:
        reach["看得到" if main_transcript_report(mp, aid).strip() else "看不到"] += 1
    print(f"主 transcript 可達性：看得到 {reach['看得到']} ／ 看不到 {reach['看不到']}")
    print()

    # 3) 三種判準的混淆矩陣
    print(f"{'判準':34s} {'召回(真需求)':>14s} {'誤報(無)':>10s} {'誤報(提及)':>11s}")
    print("-" * 74)
    for name, fn in (("A 純子字串（v3 實作）", crit_A),
                     ("B lstrip+startswith（v3 §9.5）", crit_B),
                     ("C v4：剝包裹＋排除「無」", crit_C)):
        hit = fp_none = fp_mention = 0
        total_real = sum(1 for _, k, _ in corpus if k == "真需求")
        for aid, truth, mp in corpus:
            rep = main_transcript_report(mp, aid)
            if not rep.strip():
                continue                    # 看不到 ⇒ 不可能命中，算漏
            fired = fn(rep)
            if truth == "真需求" and fired:
                hit += 1
            elif truth == "無" and fired:
                fp_none += 1
            elif truth == "提及" and fired:
                fp_mention += 1
        print(f"{name:34s} {hit:>8d}/{total_real:<5d} {fp_none:>10d} {fp_mention:>11d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
