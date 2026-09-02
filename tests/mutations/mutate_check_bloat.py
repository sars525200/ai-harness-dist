# -*- coding: utf-8 -*-
"""`check_bloat.py` 的變異測試：逐一把修好的東西弄回壞掉，確認回歸網真的會紅。

    py -3 -X utf8 D:\\.ai-harness\\tests\\mutations\\mutate_check_bloat.py

**為什麼需要這支**：`tests/test_check_bloat.py` 全綠只證明「現在的實作通過了斷言」，
不證明「斷言真的在測那件事」。每一條修法都要有一個變異守著，否則下次有人「順手簡化」
就會靜默漂回去（2026-08-12 改 FILES 正則時，兩個舊變異的錨點當場漂掉，就是這樣抓到的）。

⚠ **不用「複製腳本到別的目錄再跑」**：模組層的路徑是相對 `__file__` 算的，複製過去
會讓所有相對路徑一起失效 → 每個 case 都「拒跑」但理由全錯，那是**假綠燈**。
改成原地改檔、跑完還原，並比對雜湊確認還原乾淨。
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

# ⚠ `TARGET` 必須是**字串常數**，不能寫成 `ROOT / "..."`：
# `tests/test_mutation_anchors.py` 用 AST 找 `ast.Constant` 型的賦值來認出被測檔，
# 寫成 Path 運算它就看不到 → 這支變異腳本不會被納入錨點檢查，
# 於是「錨點漂掉」這件事再也沒人守（第一版就是這樣寫的，主套件當場擋下）。
TARGET = r"D:\Patrick-AI\.ai-harness\rulefile\check_bloat.py"
TESTS = r"D:\Patrick-AI\.ai-harness\tests\test_check_bloat.py"


def read() -> str:
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write(text: str) -> None:
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(text)


original = read()
digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

MUTATIONS = [
    (
        "trend 只有一筆時回「壓下去了」（假趨勢：最低＝起點＝現在）",
        '    if len(rows) < 2:',
        '    if False:',
    ),
    (
        # ⚠ 第一版的變異寫成 `lo = rows[-1]["visible"]`，**沒被抓到**——因為在
        # `[1000,600,600]` 這個 case 裡 rows[-1] 剛好等於 min，變異後仍然判對。
        # 變異要打在**真正的判準**上：「曾經降過」是用歷史最低點認的，不是相鄰兩筆。
        "「曾經降過」改回看相鄰兩筆（漏掉 降→沒動→回升 這個最常見的形狀）",
        "    if over_pct >= REBOUND_PCT and lo < first:",
        "    if over_pct >= REBOUND_PCT and rows[-1][\"visible\"] < rows[-2][\"visible\"]:",
    ),
    (
        "bytes 改回 text mode（CRLF 專案系統性少算，直接餵進反彈判定）",
        '        "bytes": os.path.getsize(p),',
        '        "bytes": len(md_text.encode("utf-8")),',
    ),
    (
        # 2026-08-15 v14 **重新指錨**：R8-2 把範圍判定從行 regex 改成 AST，舊錨點
        # `    if _RULES_ANCHOR_ALL.search(md_text):` 已不存在（`test_mutation_anchors`
        # 當場抓到漂掉）。⚠ **不可以回填一行假的 `search(md_text)` 把它救綠**——
        # 那行不再決定任何事，後面仍由 AST 走，做出來會是一個**等價變異**
        # （測試不會紅），而「變異沒紅」與「回歸網沒保護」印出來一模一樣。
        # 新錨點打在真正的閘門上：每個錨都被當成 `: all` ⇒ 範圍永遠是整份檔。
        "任何錨都當成 `: all`（範圍永遠整份檔→「哪一節」的判定整個失效）",
        '            if all_form:',
        '            if True:',
    ),
    (
        "沒有錨時改成掃全檔（首次跑噴一整批假警報＝D5 的 WARN 疲勞）",
        '    if kind == "index":\n        # 索引檔不必放錨',
        '    if True:\n        # 索引檔不必放錨',
    ),
    (
        # 錨點 2026-08-15 v15 更新：R8-4 的撞號去重把 `"key": vis[:KEY_CHARS],`
        # 改成 `"key": key,`（身分在 append 之前就算好），舊錨點從此對不到。
        "索引檔排除在 120 字判準外（覆核時的錯誤主張，MEMORY.md 檔頭寫著 ≤120）",
        '        entries.append({',
        '        if kind == "index" and vis and True:\n            continue\n'
        '        entries.append({',
    ),
    (
        "快照 key 退回扁平（跨檔同開頭條目互相遮蔽，成長永遠報不出來）",
        'return f"{project}\\u0001{label}\\u0001{entry_key}"',
        'return entry_key',
    ),
    (
        "schema 檢查拿掉（舊格式是合法 JSON，會把既有條目全報成新增）",
        "    if got != SCHEMA:\n        # ⚠ 舊版快照是**合法 JSON**",
        "    if False:\n        # ⚠ 舊版快照是**合法 JSON**",
    ),
    (
        "索引列長度改回算整行（檔名佔 63%，長檔名的條目永遠假超標）",
        # 錨點 2026-08-14 v12 更新：`vis_body` 那個中間變數隨「條目改成 lead＋懸掛續行」
        # 的重構 inline 進了 `entries.append`，舊錨點從此對不到 —— 而那個變異等於沒在測。
        '            "chars": len(_visible(body_txt) or vis),',
        '            "chars": len(vis),',
    ),
    (
        "去重退回「同一天只留最新」（壓縮前的基準會被當天第二筆吃掉）",
        '        prev = seen.get((today, t["project"], t["label"]))\n'
        '        if prev and prev.get("visible") == m["visible"] and prev.get("bytes") == m["bytes"]:',
        '        prev = seen.get((today, t["project"], t["label"]))\n'
        '        if prev:',
    ),
    (
        # ── 以下兩條打在**條目單位契約所依賴的既有常數**上 ──────────────
        # 條目層的「一條有多長」與「一條是誰」兩個判準各由一個模組常數承載，
        # 把它們調鬆／調碎是最省事也最容易被當成「調參數」放過去的退法。
        #
        # ⚠ **「單位邊界怎麼決定」那一類的變異已於 2026-08-15 補上**（見最下面那組
        # `parse_blocks()`）。這裡原本寫著「實作還沒落地、待補」——**實作早就落地了，
        # 註解沒更新**，而這正是同一輪剛在 `check_bloat.py` 因此刪掉整組死碼的形狀
        # （零呼叫端 ＋ 零測試 ＋ 一句註解替它解釋為什麼留著）在變異檔裡復發。
        # 補的時候仍守原則：**錨點字串必須真的存在於被測檔裡**，猜一個塞進來的話
        # `tests/test_mutation_anchors.py` 會紅在**錯的理由**上——「錨點漂掉」與
        # 「錨點從來沒對過」印出來一模一樣，但前者要更新錨點、後者要刪掉整條。
        "120 字上限放寬十倍（條目超標判定整個失效，含七種寫法的單位契約）",
        "LIMIT = 120 ",
        "LIMIT = 1200 ",
    ),
    (
        "條目身分只取前 4 字（跨版本對不上同一條→既有條目全被報成新增）",
        "KEY_CHARS = 24 ",
        "KEY_CHARS = 4 ",
    ),
    (
        "把專案路徑寫死回模組層（U-1 倒退）",
        "PROJECTS_ROOT = Path.home() / \".claude\" / \"projects\"",
        "PROJECTS_ROOT = Path.home() / \".claude\" / \"projects\"\n"
        "CLAUDE_MD = Path(r\"D:\\IT-department\\CLAUDE.md\")",
    ),

    # ── `parse_blocks()`：量測單位的單一真相（2026-08-15 補）──────────────────
    #
    # 覆核實測：上面 13 條錨點**沒有一條**打在 `parse_blocks()` 上，而 2026-08-15
    # 起兩支工具「怎麼切一條」全部問它。下面五條各守一個「改了不會有任何斷言紅」的
    # 決定 —— 補之前實測這五個變異在 153 條斷言下**全綠**（＝零保護），
    # 守門斷言同批補在 `tests/test_check_bloat.py` 的 `[R8-M]` 段。
    (
        # 原始碼註解自己寫著「縮排四格就從兩支報告裡一起消失會是下一條現成的
        # 繞過路徑」，而在補這條之前，那個決定**一條測試都沒有**。
        "縮排四格的碼塊改判 exempt（走 else 分支＝從兩支報告裡一起消失）",
        '            elif t == "code_block":',
        '            elif t == "code_block" and False:',
    ),
    (
        # 判成 prose 的話，`<!-- rules-section -->` 那行錨自己會被報成散文塊
        # ——報告會叫人去瘦一個「刪掉就整節退出監控」的東西。
        "html_block 改判 prose（錨與 HTML 註解會被當成散文報出來）",
        '            else:\n                take(ch, "exempt")',
        '            elif t == "html_block":\n                take(ch, "prose")\n'
        '            else:\n                take(ch, "exempt")',
    ),
    (
        # markdown-it 對表格分隔列與 link reference 定義**不產 token**。不回填的話
        # 那幾行誰都不認領 ——「有可見字卻不在任何一支的帳上」，而兩份報告都是綠的。
        "拿掉缺口回填（不產 token 的行從帳面上消失，兩支都看不到）",
        '            kept.append((i, j, "exempt"))\n            i = j',
        '            i = j',
    ),
    (
        # ⚠ 真實 markdown 造不出重疊區間（CommonMark 的兄弟節點不重疊），
        # 所以守門斷言用**假樹**直接餵 `_MD_CACHE`。「造不出來」正是它零保護的原因：
        # 拿掉整段偵測，跑真檔一切正常。
        "拿掉重疊偵測（同一行被兩個單位認領時雙算，某條的字數憑空變大）",
        "        if hit is not None:\n            clash = hit if clash is None else clash\n"
        "            continue",
        "        if False:\n            clash = hit if clash is None else clash\n"
        "            continue",
    ),
    (
        # `max_line` 是報告裡讓人分辨「一段折行的長散文」與「幾條各自合法的短規則」
        # 的唯一依據（R4-A）。改回整段長度 ⇒ 每一塊都變成「單行超標」，形狀資訊全失真，
        # 而**判不判仍然一樣**，所以只看 blocks 數的斷言全部照樣綠。
        "max_line 改回整段長度（形狀資訊失真，人分不出多條還是一段）",
        '            "max_line": max(len(_visible(p)) for p in parts),',
        '            "max_line": len(_visible(text)),',
    ),

    # ── 條目身分的撞號去重（R8-4）與寫入端的失明守門（R8-9）·2026-08-15 補 ──────
    (
        # 關掉前綴延長 ⇒ 退回**序位尾碼**（2026-08-15 第一批的做法，Round 9 F-1 推翻）。
        # key 仍然唯一，所以只驗唯一性的斷言對它是綠的 —— 壞的是**身分綁在序位上**：
        # 刪掉撞號組第 1 條，第 2 條遞補、拿到前者的 key、**繼承前者的基準值** ⇒
        # 過期的高基準＝靜默成長額度，正是 R8-4 本來要消滅的那個病。
        # 守住它的是 `[R8-4]` 段的**跨版本往返**斷言（寫基準→編輯→再 diff），
        # 不是任何一條單一版本的靜態斷言。
        "退回序位尾碼（身分綁序位 → 刪掉撞號組第 1 條，第 2 條繼承它的基準＝靜默成長額度）",
        "        if pick is not None:",
        "        if False:",
    ),
    (
        # 兩段式指派的**接線**：`key` 在 append 時是空字串，全靠掃完之後這一句
        # 補上。漏掉它 ⇒ 全檔條目共用同一把空 key ⇒ 互相遮蔽。
        # ⚠ 這條在補「測試炸掉 ≠ 斷言抓到」的判準之前，是被記成「紅了 ✔」的假通過：
        #   它讓 `gather_current()` 走 `sys.exit(2)`，SystemExit 直接中斷整支測試 ⇒
        #   後面所有斷言一條都沒跑。修法不是放寬判準，是**讓回歸網不會被一處壞掉打斷**
        #   （那兩處已補上守門，見 test_check_bloat.py 的兩段 Round 9 F-6 註解）。
        "不呼叫 _assign_keys（key 全是空字串 → 全檔條目互相遮蔽成同一把 key）",
        "    _assign_keys(entries)",
        "    pass  # _assign_keys(entries)",
    ),
    (
        # R8-9。⚠ 錨點必須帶下一行的 `# ── R8-9`：`if m["blind"]:` 在 `diff()` 與
        # 報告端也各有一處，只寫那一行會打在**別的函式**上 —— 變異照樣紅，
        # 但紅的是別的守門，這條就變成一個測不到自己目標的假保護。
        "拿掉寫入端的失明守門（把「沒看到」封存成「沒有」，下一輪 diff 拿它當基準）",
        '        if m["blind"]:\n            # ── R8-9',
        '        if False:\n            # ── R8-9',
    ),

    # ── exit code 的誠實性（R8-7）與 cwd 專案判定（R8-8）·2026-08-15 補 ──────────
    (
        # 這條與下一條是**同一個洞的兩半**：exit 1 的語意被檔頭契約釘死成
        # 「有新增膨脹」，而 Python 對未捕捉的例外用的也是 exit 1。
        "run_guarded 改成 exit 1（工具自己炸掉會被收工腳本讀成「量過了、去壓」）",
        '        print("  所以 exit 2（說不出答案）而不是 exit 1（有膨脹）：先修工具再談結論。")\n'
        "        sys.exit(2)",
        '        print("  所以 exit 2（說不出答案）而不是 exit 1（有膨脹）：先修工具再談結論。")\n'
        "        sys.exit(1)",
    ),
    (
        # 反方向：守門攔太寬。SystemExit 繼承 BaseException，攔它等於把唯一合法的
        # exit 1（真的有膨脹）也改判成 2 ⇒「有膨脹」從此永遠報不出來。
        # ⚠ 這條證明「例外要 exit 2」與「SystemExit 要穿透」**必須各有各的斷言**：
        #   只驗前者的話，一個 except BaseException 的實作照樣全綠。
        "run_guarded 改攔 BaseException（連 sys.exit(1) 都被改判成 2）",
        "    except Exception:                                      # noqa: BLE001",
        "    except BaseException:                                  # noqa: BLE001",
    ),
    (
        # ModuleNotFoundError 是 ImportError 的**子**類別 —— 只接子類別接不到
        # 「名字被搬走」這種升版最可能的形狀，例外外拋 ⇒ CLI exit 1。
        "_markdown 退回只接 ModuleNotFoundError（升版把名字搬走拋的是父類別 ImportError）",
        "        except Exception as exc:                           # noqa: BLE001",
        "        except ModuleNotFoundError as exc:                 # noqa: BLE001",
    ),
    (
        # 字串前綴沒有路徑邊界概念：D:\AI-Projects-old 會被判成在 D:\AI-Projects 底下。
        # 現形方式是**綁到錯的專案** —— 那個專案的膨脹算進 exit code、
        # 真正所在的專案反而沒算，兩邊都錯。
        "_under 退回字串 startswith（同前綴的姊妹目錄被判成在專案底下）",
        "    return len(c) >= len(p) and c[:len(p)] == p",
        "    return str(child).casefold().startswith(str(parent).casefold())",
    ),
    (
        # 舊版 break 在第一個命中 ⇒ 巢狀專案綁到哪一個取決於 discover_targets 的順序。
        "resolve_cwd_project 取第一個命中而非最深（巢狀專案綁到外層）",
        "        if _under(cwd, root) and len(root.parts) > best_depth:",
        "        if _under(cwd, root) and best_depth < 0:",
    ),
    (
        # diff() 的 `if only_project and ...` 讓 None 的意思變成**不過濾**
        # ⇒ 從不屬於任何專案的目錄跑，反而是管得最寬的一次。
        "cwd 不在任何專案時保底改回 None（所有專案都算進 exit code，與設計意圖相反）",
        "    best_name, best_depth = GLOBAL_PROJECT, -1",
        "    best_name, best_depth = None, -1",
    ),

    # ── Round 9 的三個發現：輸出編碼、接線、失明過濾 ·2026-08-15 補 ──────────────
    (
        # F-2。守門自己在印訊息時 UnicodeEncodeError ⇒ 例外從例外處理器裡拋出
        # ⇒ 沒有人接 ⇒ **exit 1**，正是 run_guarded 存在要防止的那個假結論。
        # 只在「stdout 是 pipe ＋ 無 -X utf8 ＋ 沒設 PYTHONIOENCODING」時現形。
        "拿掉輸出編碼重設（fail-closed 守門印不出 ⚠ 而炸掉 ⇒ exit 2 變 exit 1）",
        '        _stream.reconfigure(encoding="utf-8", errors="replace")',
        "        pass",
    ),
    (
        # F-3。`spec_from_file_location` 載入時 __name__ 不是 __main__，所以任何
        # 單元測試都碰不到這一行 —— 補之前實測：改掉它，101 條斷言全綠。
        "拆掉 run_guarded 接線（根層守門整個下線，任何例外恢復成 exit 1）",
        "    run_guarded(_cli)",
        "    _cli()",
    ),
    (
        # F-3 的另一半。同樣是接線，同樣一行，同樣過去零覆蓋。
        "拆掉 resolve_cwd_project 接線（cwd 專案判定整組回退成不過濾）",
        "    only = resolve_cwd_project(targets)",
        "    only = None",
    ),
    (
        # F-4。把過濾移回 measure() 之前 ⇒ 被過濾掉的檔連量都不量 ⇒ 它的失明
        # 不會進 blind ⇒ exit 2 靜默變 exit 0。這是這支工具最貴的一種錯。
        "失明也被專案過濾吃掉（別的專案量不到時 exit 2 變 exit 0）",
        "            blind.append(f\"{t['project']}/{t['label']}：{m['blind_why']}\")\n"
        "            continue\n"
        "        # ── `only_project` **只收斂膨脹判定",
        "            if not (only_project and t[\"project\"] not in (only_project, GLOBAL_PROJECT)):\n"
        "                blind.append(f\"{t['project']}/{t['label']}：{m['blind_why']}\")\n"
        "            continue\n"
        "        # ── `only_project` **只收斂膨脹判定",
    ),
]

# 語意等價的改動：**不該**讓測試變紅（防「測試綁死實作細節」）
EQUIVALENT = [
    (
        # L == KEY_CHARS 時組內必然逐字相同（那正是「同組」的定義），
        # set 大小恆為 1、永遠不等於 len(grp) ⇒ 一定會往下找。起點差 1 是等價的。
        "_assign_keys 的前綴搜尋起點從 KEY_CHARS+1 改成 KEY_CHARS（同組在該長度必然全同）",
        "        pick = next((L for L in range(KEY_CHARS + 1, longest + 1)",
        "        pick = next((L for L in range(KEY_CHARS, longest + 1)",
    ),
    (
        "REBOUND_PCT 從 5 改成 5.0（數值相同，型別不同）",
        "REBOUND_PCT = 5 ",
        "REBOUND_PCT = 5.0 ",
    ),
]


def run_tests() -> "tuple[int, str]":
    r = subprocess.run([sys.executable, "-X", "utf8", TESTS],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def verdict(rc: int, out: str) -> "tuple[bool, str]":
    """把「測試紅了」拆成兩種：**斷言抓到**，還是**測試自己炸了**（Round 9 F-6）。

    ⚠ 只看 `rc != 0` 分不出這兩件事。實測：變異 6 讓 `test_check_bloat.py` 在中途
    拋 `IndexError`（`e[0]["key"]`，list 空了）⇒ 它**後面約 70 條斷言一條都沒執行**，
    包含這幾輪新增的全部斷言。那次剛好前段先打紅了正確的 3 條，所以沒有假陽性 ——
    **但那是運氣**：一個「只破壞後段斷言」的變異會被記成「紅了 ✔」，而它該守的那條
    從頭到尾沒跑過。回歸網於是被讀得比實際強，而這正是變異測試存在要防的事。

    判準是測試腳本的收尾摘要行在不在：`run()` 正常回來才印得出「通過 N / M」。
    """
    if rc == 0:
        return False, "測試沒紅"
    if "通過 " not in out:
        return False, "測試**中途炸掉**（沒有收尾摘要行）—— 紅燈原因不明，不算抓到"
    return True, f"斷言抓到 (exit {rc})"


print("=" * 66)
print("check_bloat 變異測試")
print("=" * 66)

base, base_out = run_tests()
if base != 0:
    print(f"⚠ 未變異時測試就是紅的（exit={base}）—— 先修好再跑變異，否則結果無意義。")
    sys.exit(2)
if "通過 " not in base_out:
    print("⚠ 未變異時測試 exit 0 但**印不出收尾摘要行** —— 下面的 verdict() 判準"
          "整組失效（它靠那一行分辨「斷言抓到」與「測試炸掉」）。先查測試腳本。")
    sys.exit(2)
print("基準：未變異時測試全綠 ✔\n")

fail = 0
for i, (name, old, new) in enumerate(MUTATIONS, 1):
    if old not in original:
        print(f"變異 {i}：{name}\n   ✘ **錨點已漂掉**，在 check_bloat.py 裡找不到 —— 這個變異等於沒在測")
        fail += 1
        continue
    write(original.replace(old, new, 1))
    rc, out = run_tests()
    write(original)
    ok, why = verdict(rc, out)
    if ok:
        print(f"變異 {i}：{name}\n   → 測試 紅了 ✔ （{why}）")
    else:
        print(f"變異 {i}：{name}\n   ✘ **{why}** —— 這條變異沒有被有效守住")
        fail += 1

for i, (name, old, new) in enumerate(EQUIVALENT, 1):
    if old not in original:
        print(f"等價 {i}：{name}\n   ✘ 錨點漂掉")
        fail += 1
        continue
    write(original.replace(old, new, 1))
    rc, out = run_tests()
    write(original)
    if rc == 0:
        print(f"等價 {i}：{name}\n   → 測試 仍綠 ✔（沒有綁死實作細節）")
    else:
        print(f"等價 {i}：{name}\n   ✘ **語意等價的改動讓測試紅了** —— 斷言綁太死")
        fail += 1

restored = hashlib.sha256(read().encode("utf-8")).hexdigest()
print()
print("=" * 66)
print(f"檔案還原：{'✔ 雜湊一致' if restored == digest else '✘ 沒還原乾淨！'}")
if fail:
    print(f"✘ {fail} 個變異沒被抓到 —— 回歸網有洞")
    sys.exit(1)
print(f"{len(MUTATIONS)} 個變異全部被抓到 + {len(EQUIVALENT)} 個等價改動沒誤判，回歸網可信")
