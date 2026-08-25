#!/usr/bin/env python3
"""落檔交換守門：`/adversarial-review` **走落檔交換時**，蓋章前必須跑這支。

⚠ **適用範圍跟設定的是哪個審查者無關。** 這一行原本寫「用 `tool: cursor` 時」，
而那個審查者已在 `f2d9a5f`（2026-08-26）移除 ⇒ 照字面讀會推出「這支沒人用了」。
實際上落檔交換已升為通用做法，`cursor-cli` 一樣要走，PR-1 也一樣會呼叫這支
（`pr1_plan_review_marker._exchange_gate_verdict`，判準是同目錄有沒有 `round-N-ask.md`）。

## 為什麼需要它

跨模型族的審查者，其發現要進到蓋章流程只能靠落檔：skill 寫 `round-N-ask.md`、
審查者把發現寫回 `round-N-reply.md`。

問題是**這條路徑的每一步都能被跳過而不出聲**：不貼給任何人、reply 空白、reply 是上一輪
的複製、派出後偷改題目——外形都一樣。marker 的 hash 只證明「文件沒被改過」，
證明不了「有人真的看過」。

所以這支的職責只有一個：**讓「沒有真的交換過」變成一個 exit code**。

⚠ **它已經被 PR-1 接走了**（2026-08-25 `dc3000d`，覆核 R1-3）：
`hooks/rules/pr1_plan_review_marker.py` 的 `_exchange_gate_verdict()` 會在
「這輪動過 `.scratch/**/map.md` 且同目錄有 `round-N-ask.md`」時呼叫 `--check`，
非零就 BLOCK。所以**這不是一支只靠人記得跑的輔助工具**——改它的行為會直接改變
Stop 的判定。（本檔早期版本寫著「PR-1 看不見 ask／reply」，那句話在 `dc3000d` 之後
就是假的；覆核 R3-5 指出留著它會讓下一個人把接線當死碼刪掉。）

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
# 大小寫變體要**認得但拒絕**，不是視而不見（2026-08-25 覆核 R3-2）。
# PR-1 的開火條件用 re.I：那邊若也改成區分大小寫，`Round-1-ask.md` 就會變成
# 兩邊都看不見的檔 —— 等於完全沒有守門，而且是靜默的。所以這裡認得它，並明講
# 「檔名不是正規形式」，把「靜默沒有守門」換成「一句看得懂的話」。
ASK_LOOSE = re.compile(r"^round-\d+-ask\.md$", re.I)
REPLY_LOOSE = re.compile(r"^round-\d+-reply\.md$", re.I)
# ⚠ 容許 markdown 標記把值包起來（2026-08-25 實測）：Cursor CLI 上的 Grok
# **連續兩輪**都輸出 ``ask-sha256=`<hash>` ``——它在 markdown 語境會自動把 hash
# 當成 code 標記，即使 prompt 明寫「不要用反引號包起來」也照包。
# 原本的正則要求整行只有 `ask-sha256=<hash>` ⇒ 那兩輪都被判成「沒有帶回 hash」，
# 而**整輪內容其實完全有效**（值一字不差）。
# 判準的本意是「這份回覆認不認得出是回哪一題」，那由 **hash 值**決定，不是由排版決定。
# 值仍然必須是 64 hex 且逐字相符，防護一點沒少；放寬的只是它兩側的裝飾字元。
SHA_LINE = re.compile(r"^\s*[`*_~\"']*\s*ask-sha256\s*=\s*[`*_~\"']*\s*([0-9a-f]{64})\s*[`*_~\"']*\s*$")

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


def findings_head(text: str, k: int = 3):
    """回傳發現區的前 k 行實質內容。

    2026-08-25 覆核 R1-8 的收束：門檻（3 行／120 字）量的是**長度**不是「有沒有發現」，
    `n/a` 加 120 個 `x` 就過得了。把門檻改成語意判斷會變成軍備競賽，所以不改門檻——
    改成**綠的時候把前三行印出來**。skill 已經要求把 `--check` 的輸出貼進回報，
    於是填充物會跟著 exit 0 一起出現在人眼前。這是防遺忘的可視性，不是防作弊。
    """
    return [ln for ln in _content_lines(text)][:k]


def _content_lines(text: str):
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("<!--"):
            continue
        if SHA_LINE.match(ln):
            continue
        if set(s) <= set("|-: "):      # markdown 表格分隔列
            continue
        yield s


def findings_size(text: str):
    """數 reply 裡的實質內容行：跳過標題、空行、HTML 註解、表格分隔列、sha 行。

    ⚠ 這量的是**長度**，不是「有沒有發現」——後者機器判不了（覆核 R1-8）。
    可視性補在 `findings_head()`：綠的時候把前三行印出來給人看。
    """
    lines = chars = 0
    for s in _content_lines(text):
        lines += 1
        chars += len(s)
    return lines, chars


def stamp_ask(path: Path) -> int:
    text = read_text_or_none(path)          # R2-9：非 UTF-8 不該以 traceback 收場
    if text is None:
        print(f"✘ {path.name} 不是合法的 UTF-8 —— 讀不了就不 stamp")
        return 2

    body, existing = _split_stamp(text)
    if existing is not None and existing != hashlib.sha256(
            body.rstrip().encode("utf-8")).hexdigest():
        # R2-1：檔尾那行 sha 對不上本文 —— 它可能是「舊 stamp（題目被改過）」，
        # 也可能是「題目正文最後一行剛好在示範這個格式」。**機器分不出來**，
        # 而兩種的正確處置相反（前者該重 stamp、後者絕不能刪）。
        # 原本無條件把它當 stamp 剝掉：示範行被靜默刪除、協議說明從檔案消失。
        # 分不出來的時候就不要猜——出聲讓人決定。
        print(f"✘ {path.name} 檔尾已經有一行 ask-sha256，但它對不上本文的雜湊。")
        print("  兩種可能，機器分不出來：")
        print("    ① 這是舊 stamp，而題目在 stamp 之後被改過 → 請開下一輪的 ask，不要重 stamp")
        print("    ② 這是正文在示範這個格式 → 請把它移到不是最後一行的位置，或加一行本文在後面")
        print("  沒有 --force：靜默猜錯的兩種後果都是「審查者看到的題目不是你以為的那份」。")
        return 2

    digest = ask_hash(text)
    path.write_text(f"{body.rstrip()}\n\nask-sha256={digest}\n",
                    encoding="utf-8", newline="\n")
    print(f"已 stamp：{path.name}")
    print(f"  ask-sha256={digest}")
    print("  ⚠ 這份題目檔從現在起**凍結**。要改題目請開下一輪的 ask，不要改它。")
    return 0


def check_dir(effort: Path) -> int:
    if not effort.is_dir():
        print(f"✘ 找不到 effort 目錄：{effort}")
        return 2

    entries = list(effort.iterdir())

    # 大小寫變體：認得、但拒絕（R3-2）。放在最前面，因為它會讓下面每一條的
    # 檔名配對都不可靠——先講清楚檔名不對，比讓人去讀一堆對不上的訊息好。
    odd = sorted(p.name for p in entries
                 if (ASK_LOOSE.match(p.name) and not ASK_NAME.match(p.name))
                 or (REPLY_LOOSE.match(p.name) and not REPLY_NAME.match(p.name)))
    if odd:
        print(f"✘ 檔名不是正規形式（大小寫不符）：{odd}")
        print("  請改成全小寫的 round-N-ask.md／round-N-reply.md。")
        print("  ⚠ 這不是吹毛求疵：PR-1 的開火條件不分大小寫、這支的配對分，"
              "留著會讓「檔在那裡」與「訊息說沒有」同時成立。")
        return 2

    asks = sorted((p for p in entries if ASK_NAME.match(p.name)),
                  key=lambda p: int(ASK_NAME.match(p.name).group(1)))
    if not asks:
        print(f"✘ {effort} 底下沒有任何 round-N-ask.md —— 沒有派出過題目，談不上覆核。")
        return 2

    bad = 0

    # 檔名別名：`round-01-ask.md` 的 `01` 會被 int() 讀成 1，單獨存在時當合法的
    # 第 1 輪放行（2026-08-25 覆核 R2-7）。實務上幾乎等價，但「同一輪有兩種寫法」
    # 遲早會變成「兩個檔各自被當成一輪」。輪號只准正規十進位。
    aliased = [p.name for p in asks
               if ASK_NAME.match(p.name).group(1) != str(int(ASK_NAME.match(p.name).group(1)))]
    if aliased:
        print(f"  ✘ 輪號有前導零：{aliased} —— 請寫成 round-1-ask.md 這種正規形式")
        bad += 1

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
                     for p in entries
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
        # 綠的時候也把前三行印出來（覆核 R1-8）：門檻只量長度，`n/a` 加一堆填充
        # 也過得了。skill 要求把這段輸出貼進回報 ⇒ 填充物會跟著 exit 0 一起被看見。
        for head in findings_head(rt):
            print(f"       │ {head[:78]}")

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
