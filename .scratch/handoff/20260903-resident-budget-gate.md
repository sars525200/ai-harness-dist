---
status: open
---

# 交接：常駐層瘦身 → 產生器預算閘門（2026-09-03）

## 目標

起點是續辦「Skill 索引體檢」的待辦（前一份交接檔
`20260903-skill-index-audit.md`，仍 `open`）。做著做著轉向兩次：

1. 先量常駐層實際成本 → 發現 Memory files 18.9k tokens 是 Skills 5.7k 的 3.3 倍
2. 瘦了三塊之後發現 **省的追不上長的** → 轉向補「產生器那條路徑沒有閘門」的洞

最後定案的任務名是「常駐層預算閘門」。

## 已完成

### harness repo（`D:\Patrick-AI\.ai-harness`，main）

| commit | 內容 |
|---|---|
| `63c358b` | 回收兩列已完成的過期待辦；CTX-1 那列改為「已轉正」（實查 `hooks/dispatch_config.json` 的 `rules.CTX-1.shadow` 為 false） |
| `6e1a45e` | 描述預算那列填入實測：Skills 5.7k tokens／1M 視窗 ⇒ 未溢出；自訂 30 支 description ＝ 4,357 字元／8,960 bytes |
| `daf094e` | `global/hub/21-title-claude.md` 對話名稱 8 條合併成 6 條，理由移進不進常駐的 frontmatter 註解 |
| `5412ff7` | 執行 `WORKFLOW_5STAGE_PLAN.md` §15.2 殘餘三小段搬移，並修正 §15 過期的狀態欄 |
| `318a709` | **主成果**：`rulefile/resident_budget.py` ＋ `tools/gen_rule_hub.py` 預算檢查 ＋ `tests/test_resident_budget.py`（18 項，已掛進 `tests/run_hook_tests.py`） |

`2a7081e` 不是這則的，是別的 session 開的票（MIS-install 守門靜默無效）。

### IT-department repo（`D:\Patrick-AI\IT-department`）

| commit | 內容 |
|---|---|
| `91569302` | `CLAUDE.md` §7 skill 覆寫現況「2 筆」→「5 筆」並列出鎖手動的 4 支 |
| `0a2078aa` | `CLAUDE.md` §8 三條超標條目壓掉重複細節，省 265 bytes |

### 量測前後（`rulefile/check_bloat.py`）

| 檔 | 前 | 後 |
|---|---|---|
| 全域 `CLAUDE.md` | 14,626 | 13,813 |
| IT `CLAUDE.md` | 14,008 | 13,743 |
| 每則都付合計 | 65,638 | 64,560 |

全域已 `--restore` 到 `C:\Users\<USER>\.claude\CLAUDE.md`，live 與 repo 逐位元組相同。
這一輪的量測已 `--append-history` 入列（人點頭過）。

### 閘門做了什麼

CTX-1 只掛改檔工具（PostToolUse × Write/Edit/MultiEdit/NotebookEdit），
而全域 `CLAUDE.md` 是 `tools/gen_rule_hub.py` 寫的、走 Bash ⇒ **從頭到尾不會被叫到**。
實測：8/28 是 12,138 bytes、9/03 動工前 14,626 —— 五天長 2,488 沒有任何東西叫過。

新閘門在產生器寫完之後量產出檔，超標印訊息並 `exit 1`，**但檔照寫**
（擋掉會逼人改用手動寫檔繞過去，那條路更沒人看得到）。`--allow-growth` 只關掉 exit code。
棘輪狀態在 `rulefile/state/genhub_budget_state.json`（gitignored），同一個大小只叫一次。

驗過會紅：清掉棘輪跑產生器 → exit 1；三個變異（底線→0、比例→1.00、拿掉棘輪）
分別讓測試轉紅 1／3／2 項，還原後 18/18 綠；`run_hook_tests.py` 全綠。

## 未完成／等人點頭

| 項目 | 狀況與下一步 |
|---|---|
| ~~**係數有三份副本**~~ **↻ 2026-09-03 已改寫，見下** | ⚠ **這一列原本寫錯，照著做會改壞東西。** 實查：係數 `1.10`／`800` 只在**兩處**（`rulefile/resident_budget.py:32-33`、`hooks/rules/ctx1_resident_budget.py:86-87`）；`eval/check_structure.py` 抄的是**棘輪的形狀**，係數是它自己的、**沒有下限那一邊**，量的是 skill token 突增不是常駐層 bytes ⇒ 照原文「三處一起改係數」會改壞它的門檻語意。正確說法是**係數 2 份、棘輪形狀 3 份**。<br>**偵測已補**（commit `e9c9d47`）：兩處的係數或門檻公式形狀漂開時，`tests/test_resident_budget.py` 的「跨副本一致性」那一段會紅（4 個變異已證會紅）。`TODOS.md` 那一列也已由另一條線提交並訂正。<br>**仍未做**：把兩處真的合併成單一來源。要動 CTX-1 這個活閘門，需人點頭 |
| **Cursor 端未驗** | 搬進 `skills/session-workflow/SKILL.md` 的兩句（「不要邊做邊問」的理由、「已修且已生效」）在 Cursor 端載不載得到，**沒有實跑**。依據只有 `WORKFLOW_5STAGE_PLAN.md` §15.7 的「可共用」結論。要驗得在 Cursor 開一則 |
| **IT `CLAUDE.md` 趨勢缺前一筆** | `check_bloat.py --history` 那列仍標「沒動」，因為歷史裡沒有我動手前的量測。下次再跑一次 `--append-history` 就比得出來 |
| **基準刻意沒重建** | 快照仍是 11,752、現況 13,813（高 18%）。user 2026-09-03 決定**不重建**，理由是留著才看得出那 2,061 bytes 還欠著。棘輪已止住噪音，所以不會每次跑都叫 |

## 硬限制

- **`TODOS.md` 正在被別的 session 大幅改寫**。本輪對帳時我的 hunk 與它的刪除混在同一塊、
  對帳非 0，所以「係數三份副本」那一列**只寫進磁碟、沒有提交**。
  下次要提交它：先 `py -3 tools/check_before_start.py TODOS.md`，
  再 `py -3 tools/filter_hunks.py --keep <只有我那列才有的字串>`，**對帳要 0 才 commit**。
- **不要重建 `rulefile/bloat_snapshot.json`**（user 2026-09-03 明確決定）。
  跑 `--write-snapshot` 會把那 2,061 bytes 的債洗掉。
- **不要在同一輪重構 CTX-1**。它是活的閘門、有自己的回歸網；在剛補完洞的同一輪動它，
  「洞到底補好了沒」會變得無法歸因。
- **改 `global/CLAUDE.md` 要改 `global/hub/` 模組再跑 `tools/gen_rule_hub.py`**，
  產出檔禁止手改。改完要 `py -3 tools/backup_global_config.py --restore --only CLAUDE.md`
  才會生效（live 與 repo 是兩個實體檔，跨磁碟做不了符號連結）。
  縮減時它會擋一次要 `--force`，**那個守門是對的**，加旗標前要先看過 diff。
- **`§8`／`MEMORY.md` 的索引句不可當肥肉刪**：那些指向記憶檔、規則檔、計畫書的句子
  是它們**唯一的常駐入口**（那些檔沒有常駐 description），刪掉是斷線不是搬家。
  `CONTEXT_HEALTH_PLAN.md` §R4-E 已經否決過「description 已經有了所以可以刪」這個判準。

## 這則踩過的坑（別重踩）

- **Bash `-c "..."` 裡的反引號會被當命令替換吃掉**。我在 python 字串的中文註解裡寫
  `` `tests/run_hook_tests.py` ``，寫進檔案後那段直接消失、程式照樣編譯過。
  **中文含反引號的內容一律用 Write 工具落成 `.py` 再 `py -3` 跑**，不要走 `-c`。
- **字元 vs bytes 今天出事三次**（兩次是我自己）。中文 UTF-8 約 2.6 bytes/字元，
  ASCII 檔名是 1:1，混在一起估會差一倍。報數字時兩個單位都寫。
- **新寫的檢查預設它自己有問題**：我把「判不出來」也回 exit 1，
  在沒有 harness 的沙箱裡會無條件失敗，把既有的產生器測試從 21/21 打成 19/21。
  是 `run_hook_tests.py` 咬出來的，不是我自己想到的。
- **沒被 runner 叫到的測試等於沒有測試**：`tests/` 底下的檔不會被自動掃，
  要在 `run_hook_tests.py` 裡 `import` 並呼叫 `run()`（回 `(passed, failed_list)`）。
- **「做完了沒回頭改狀態欄」今天抓到三筆**：待辦簿的 CTX-1、計畫書 §15、
  IT 常駐層的覆寫筆數。三筆都各害人抄錯過一次。做完就回頭改那一欄。

## 新對話建議第一句

```
接續 2026-09-03 的常駐層預算閘門。交接檔在 D:\Patrick-AI\.ai-harness\.scratch\handoff\20260903-resident-budget-gate.md，先讀它。閘門已上線並驗過會紅（commit 318a709）。現在要處理「係數三份副本」那一列——它寫在 TODOS.md 磁碟上但沒提交，因為別的 session 正在大改該檔，提交前要用 filter_hunks 對帳到 0。
```
