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
TARGET = r"D:\.ai-harness\rulefile\check_bloat.py"
TESTS = r"D:\.ai-harness\tests\test_check_bloat.py"


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
        '        entries.append({\n            "key": key,',
        '        if kind == "index" and vis and True:\n            continue\n'
        '        entries.append({\n            "key": key,',
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
        # 退回舊行為的「後果」那一半：key 不再唯一 ⇒ 同檔內第 2 條被第 1 條蓋掉，
        # 它的成長從此永遠報不出來。⚠ 舊實作在 `gather_current()` 會 exit 2 擋下來，
        # 所以這個變異不只是「少一條」——它同時把該專案的 `--write-snapshot`
        # 修復路徑一起關掉（AI-Projects 的基準就是這樣卡在 56 條而現況 112 條）。
        "拿掉撞號去重（同檔內第 2 條沿用同一把 key → 兩條互相遮蔽，成長永遠報不出來）",
        '        if nth > 1:\n            key = f"{key}\\u0002{nth}"',
        '        if False:\n            key = f"{key}\\u0002{nth}"',
    ),
    (
        # 守的是**零位移**那半邊：去重仍然成立（key 照樣唯一），但第 1 條也帶尾碼
        # ⇒ 全部既有 key 一起位移 ⇒ 下一輪每一條都被報成「新增超標」，
        # 那正是「一次全面基準重建、噪音蓋過訊號」的形狀。
        # ⚠ **只驗「兩把 key 不同」的斷言對這個變異是綠的** —— 所以零位移必須有
        #   自己的斷言（`de[0]["key"] == raw[0]`），不能靠唯一性順帶保證。
        #   這也是這條變異存在的全部理由：它證明那個斷言不是多餘的。
        "第 1 條也加尾碼（唯一性仍成立，但所有既有 key 一起位移＝全面基準重建）",
        "        if nth > 1:",
        "        if nth > 0:",
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
]

# 語意等價的改動：**不該**讓測試變紅（防「測試綁死實作細節」）
EQUIVALENT = [
    (
        "REBOUND_PCT 從 5 改成 5.0（數值相同，型別不同）",
        "REBOUND_PCT = 5 ",
        "REBOUND_PCT = 5.0 ",
    ),
]


def run_tests() -> int:
    r = subprocess.run([sys.executable, "-X", "utf8", TESTS],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode


print("=" * 66)
print("check_bloat 變異測試")
print("=" * 66)

base = run_tests()
if base != 0:
    print(f"⚠ 未變異時測試就是紅的（exit={base}）—— 先修好再跑變異，否則結果無意義。")
    sys.exit(2)
print("基準：未變異時測試全綠 ✔\n")

fail = 0
for i, (name, old, new) in enumerate(MUTATIONS, 1):
    if old not in original:
        print(f"變異 {i}：{name}\n   ✘ **錨點已漂掉**，在 check_bloat.py 裡找不到 —— 這個變異等於沒在測")
        fail += 1
        continue
    write(original.replace(old, new, 1))
    rc = run_tests()
    write(original)
    if rc != 0:
        print(f"變異 {i}：{name}\n   → 測試 紅了 ✔ (exit {rc})")
    else:
        print(f"變異 {i}：{name}\n   ✘ **測試沒紅** —— 回歸網對這條修法沒有保護")
        fail += 1

for i, (name, old, new) in enumerate(EQUIVALENT, 1):
    if old not in original:
        print(f"等價 {i}：{name}\n   ✘ 錨點漂掉")
        fail += 1
        continue
    write(original.replace(old, new, 1))
    rc = run_tests()
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
