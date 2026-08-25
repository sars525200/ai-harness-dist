#!/usr/bin/env python3
"""落檔交換守門：`/adversarial-review` 用 `tool: cursor` 時，蓋章前必須跑這支。

## 為什麼需要它

Cursor 是這台機器上唯一真正跨模型族的審查者，但程式叫不到它（`ListAgents` 看不見
Cursor），所以走落檔交換：skill 寫 `round-N-ask.md`、人貼進 Cursor、Cursor 把發現寫回
`round-N-reply.md`。

問題是**這條路徑的每一步都能被跳過而不出聲**：不貼給任何人、reply 空白、reply 是上一輪
的複製、派出後偷改題目——外形都一樣。PR-1 幫不上忙，它只認 `.scratch/**/map.md`
（`hooks/rules/pr1_plan_review_marker.py`），**看不見 ask 與 reply**。

所以這支的職責只有一個：**讓「沒有真的交換過」變成一個 exit code**。

## 誠實界線

它**防遺忘、不防作弊**。有 shell 的人可以自己寫一份 reply、自己 stamp 一個 hash。
檔案系統上「Claude 自己 Write 的 reply」與「Cursor 真的寫回的 reply」完全同形，
沒有機器能分辨。唯一的真防線是「**人親手貼過一次**」。

寫下這條不是免責，是因為**假的安全感比沒有守門更危險**——這正是 skill 正文
「以為找了外部 AI 覆核、其實是自己審自己」那句話警告的東西。

## 用法

    py -3 tools/adversarial_exchange_gate.py --stamp-ask <round-N-ask.md>
    py -3 tools/adversarial_exchange_gate.py --check <effort 目錄>

`--check` 掃目錄裡**每一個** `round-N-ask.md`（不只最新那輪），任何一輪不合格就 exit 2。
掃全部是刻意的：只驗最新輪的話，「跳過中間某一輪」會靜默通過。
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

# 這支印 ✔／✘，在 Windows 預設 cp950 終端會 UnicodeEncodeError → **exit 1 而不是 2**
# （2026-08-25 覆核 R1-11 實測）。那是假紅：守門明明有結論，卻以 traceback 收場，
# 而「工具壞了」很容易被讀成「這關可以跳過」。`reviewer/server.py` 頂端早就這樣做了。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ASK_NAME = re.compile(r"^round-(\d+)-ask\.md$")
REPLY_NAME = re.compile(r"^round-(\d+)-reply\.md$")
SHA_LINE = re.compile(r"^\s*ask-sha256\s*=\s*([0-9a-f]{64})\s*$")

# 發現區的下限。判準是「這份 reply 有沒有實質內容」，不是「寫得好不好」——
# 後者機器判不了，前者判得了，而空白 reply 正是最容易發生的那種假綠。
MIN_LINES = 3
MIN_CHARS = 120


def _strip_sha_lines(text: str) -> str:
    """算雜湊前扣掉**最後一行** `ask-sha256=`（那一行才是 stamp）。

    不扣的話它自我指涉：寫進去就改變了自己的雜湊，重算幾次都不會相符。
    這與 `ADVERSARIAL_REVIEW_PASSED` marker 不進 content_hash 是同一個道理
    （見 docs/agents/issue-tracker.md「marker 沒有獨佔一行」那節）。

    ⚠ **只扣最後一行，不是扣掉全部**（2026-08-25 覆核 R1-10）：原本無差別扣，
    於是題目正文裡任何一行長得像 `ask-sha256=<64 hex>` 的內容——例如題目在示範
    「請把這一行抄回去」——都會被 `--stamp-ask` **從檔案裡刪掉**，而且不留痕跡。
    協議說明被工具吃掉，審查者少看到一條指令。正文裡的那種行是**內容**，該進雜湊。
    """
    return _split_stamp(text)[0]


def _split_stamp(text: str):
    """切成 (body, stamp)。**stamp＝檔案最後一個非空行**，而且它要長得像 sha 行。

    判準釘死在「最後一個非空行」而不是「最後一個 sha 行」：
    第一次 stamp 時檔案裡還沒有 stamp，若用後者，正文的示範行就會被當成 stamp 剝掉
    ——那正是 R1-10 的成因，而且第一版的修法（改成只剝最後一個 sha 行）**沒修到**，
    是這支的回歸測試把它揪出來的。
    """
    lines = text.splitlines()
    i = len(lines) - 1
    while i >= 0 and not lines[i].strip():
        i -= 1
    if i >= 0 and SHA_LINE.match(lines[i]):
        return "\n".join(lines[:i]), SHA_LINE.match(lines[i]).group(1)
    return "\n".join(lines), None


def has_sha_line(text: str) -> bool:
    """回覆檔裡**任何一行**長得像 sha 行就算「有帶」——它寫在檔頭或檔尾都合理。"""
    return any(SHA_LINE.match(ln) for ln in text.splitlines())


def ask_hash(text: str) -> str:
    """扣掉 sha 行之後，**尾端空白一律正規化**再算。

    不 rstrip 的話 stamp 自己就會把 hash 打壞：`stamp_ask` 在題目與 sha 行之間插一個
    空行，重讀時那個空行留在 body 尾端 ⇒ 算出來的值與 stamp 當下不同 ⇒ 每一份剛
    stamp 完的 ask 都會被判成「派出後被改過」。守門會永遠紅（fail-closed，不會誤放行，
    但等於沒有守門）。2026-08-25 由反證測試⑧抓到。
    """
    return hashlib.sha256(_strip_sha_lines(text).rstrip().encode("utf-8")).hexdigest()


def stamped_sha(text: str):
    """題目檔的 stamp（沒有就 None）——口徑見 `_split_stamp`。"""
    return _split_stamp(text)[1]


def reply_carries(text: str, expected: str) -> bool:
    """回覆檔**任何一行**帶回相符的 hash 就算數。

    不釘死在檔頭：審查者把它寫在檔頭、檔尾或引用區塊都是合理的，
    而「有沒有回對題」這件事與它寫在第幾行無關。
    """
    return any((m := SHA_LINE.match(ln)) and m.group(1) == expected
               for ln in text.splitlines())


def read_text_or_none(path: Path):
    """讀不成 UTF-8 就回 None——交給呼叫端印 ✘ 並 exit 2。

    2026-08-25 覆核 R1-12：原本讓 `UnicodeDecodeError` 直接拋出，CLI 變成 **exit 1**
    而不是 2，訊息也不是守門那套。skill 寫的是「非零就不准蓋章」所以還擋得住，
    但任何把 2 當「不合格」、把 1 當「工具壞了」的呼叫端都會誤判成可跳過。
    """
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def findings_size(text: str):
    """數 reply 裡的實質內容行：跳過標題、空行、HTML 註解、表格分隔列、sha 行。"""
    lines = chars = 0
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if SHA_LINE.match(ln):
            continue
        if set(s) <= set("|-: "):      # markdown 表格分隔列
            continue
        lines += 1
        chars += len(s)
    return lines, chars


def stamp_ask(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    digest = ask_hash(text)
    body = _strip_sha_lines(text).rstrip("\n")
    path.write_text(f"{body}\n\nask-sha256={digest}\n", encoding="utf-8", newline="\n")
    print(f"已 stamp：{path.name}")
    print(f"  ask-sha256={digest}")
    print("  ⚠ 這份題目檔從現在起**凍結**。要改題目請開下一輪的 ask，不要改它。")
    return 0


def check_dir(effort: Path) -> int:
    if not effort.is_dir():
        print(f"✘ 找不到 effort 目錄：{effort}")
        return 2

    asks = sorted((p for p in effort.iterdir() if ASK_NAME.match(p.name)),
                  key=lambda p: int(ASK_NAME.match(p.name).group(1)))
    if not asks:
        print(f"✘ {effort} 底下沒有任何 round-N-ask.md —— 沒有派出過題目，談不上覆核。")
        return 2

    bad = 0

    # ── 輪號必須是連續的 1..N（2026-08-25 覆核 R1-6）─────────────────
    # 原本只迭代「目錄裡找得到的 ask」，於是**刪掉中間那輪的 ask** 或根本不寫它，
    # 那一輪就不存在於迴圈 ⇒ 印「✔ 第 1 輪／✔ 第 3 輪／2 輪都齊全」然後 exit 0。
    # docstring 與 SKILL.md 都宣稱「掃每一輪，否則跳過中間某一輪會靜默通過」——
    # 那句話當時是假的。孤兒 reply（有 reply 沒有對應 ask）同樣是這個形狀。
    nums = [int(ASK_NAME.match(p.name).group(1)) for p in asks]
    expected = list(range(1, len(nums) + 1))
    if nums != expected:
        missing = sorted(set(expected) - set(nums))
        print(f"  ✘ 輪號不連續：找到 {nums}，缺 {missing} 的 ask"
              " —— 中間輪的題目被刪掉或從未建立，那一輪等於沒被檢查過")
        bad += 1
    orphans = sorted(int(REPLY_NAME.match(p.name).group(1))
                     for p in effort.iterdir()
                     if REPLY_NAME.match(p.name)
                     and int(REPLY_NAME.match(p.name).group(1)) not in nums)
    if orphans:
        print(f"  ✘ 有 reply 卻沒有對應的 ask：第 {orphans} 輪"
              " —— 題目檔不見了，這份回覆對的是什麼題目已經無法查證")
        bad += 1

    for ask in asks:
        n = ASK_NAME.match(ask.name).group(1)
        reply = effort / f"round-{n}-reply.md"

        def fail(msg: str):
            nonlocal bad
            bad += 1
            print(f"  ✘ 第 {n} 輪：{msg}")

        at = read_text_or_none(ask)
        if at is None:
            fail(f"{ask.name} 不是合法的 UTF-8 —— 讀不了就無法查證，不當成通過")
            continue
        stamped = stamped_sha(at)
        actual = ask_hash(at)

        if stamped is None:
            fail(f"{ask.name} 沒有 ask-sha256= —— 先跑 --stamp-ask 凍結它")
            continue
        if stamped != actual:
            fail(f"{ask.name} 派出後被改過（stamp {stamped[:12]}… ≠ 現況 {actual[:12]}…）"
                 " —— 審查者看到的題目與現在這份不是同一題")
            continue
        if not reply.exists():
            fail(f"缺 {reply.name} —— 沒有收到回覆。"
                 "把 ask 貼進 Cursor、讓它寫回這個檔，不要自己代筆")
            continue

        rt = read_text_or_none(reply)
        if rt is None:
            fail(f"{reply.name} 不是合法的 UTF-8 —— 讀不了就無法查證，不當成通過")
            continue
        if not has_sha_line(rt):
            fail(f"{reply.name} 沒有帶回 ask-sha256= —— 認不出它回的是哪一題")
            continue
        if not reply_carries(rt, stamped):
            fail(f"{reply.name} 帶回的 ask-sha256 對不上本輪的 {stamped[:12]}…"
                 " —— 這份回覆不是針對本輪的題目（常見成因：複製了上一輪的 reply）")
            continue

        ln, ch = findings_size(rt)
        if ln < MIN_LINES or ch < MIN_CHARS:
            fail(f"{reply.name} 的發現區太空（{ln} 行／{ch} 字，下限 {MIN_LINES} 行／{MIN_CHARS} 字）"
                 " —— 「沒有發現」也要明寫那句話並說明查了哪些地方")
            continue

        print(f"  ✔ 第 {n} 輪：ask 已凍結、reply 對得上、發現區 {ln} 行／{ch} 字")

    if bad:
        print(f"\n✘ 落檔交換不合格（{bad} 輪有問題）——**不得蓋 ADVERSARIAL_REVIEW_PASSED**。")
        print("  ⚠ 提醒：這支防遺忘、不防作弊。它綠了只代表檔案齊全，"
              "不代表真的有人把題目貼進 Cursor。")
        return 2

    print(f"\n✔ {len(asks)} 輪落檔交換都齊全。")
    print("  ⚠ 但這**不是**「Cursor 真的看過」的證明——檔案系統上自己代筆與真的回覆同形。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="對抗式覆核落檔交換守門")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", metavar="EFFORT_DIR", help="檢查 effort 目錄裡每一輪的交換是否齊全")
    g.add_argument("--stamp-ask", metavar="ASK_MD", help="替題目檔算並寫入 ask-sha256（派出前跑）")
    a = ap.parse_args()
    if a.stamp_ask:
        return stamp_ask(Path(a.stamp_ask))
    return check_dir(Path(a.check))


if __name__ == "__main__":
    raise SystemExit(main())
