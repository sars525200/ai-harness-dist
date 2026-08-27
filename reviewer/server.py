# -*- coding: utf-8 -*-
r"""對抗式覆核審查者設定頁 —— 本機小服務（零外部依賴）。

    py -3 D:\.ai-harness\reviewer\server.py          # 啟動並自動開瀏覽器
    py -3 D:\.ai-harness\reviewer\server.py --check  # 只印目前設定與可用性，不起服務

## 這是什麼

`/adversarial-review` 要找一個「不共用推理脈絡」的獨立審查者來挑錯。原本審查者是寫死的
（Codex 優先、Claude subagent 兜底），2026-07-31 改成**可選**：這頁改設定，skill 每次執行時讀。

## 為什麼不做進看板、也不做進 IT 資產平台

- **看板是 artifact**：它讀不到本機檔（可用 runtime capability 只有 downloads／mcp），
  改了寫不回來。這條路先前已評估排除，別再走一次。
- **IT 資產平台是給 IT 同仁用的業務系統**：對抗式覆核是開發工具，混進去只會讓看到的人困惑，
  而且那台 VM 跟本機開發環境是兩回事。

## 安全

只綁 `127.0.0.1`（不是 `0.0.0.0`）—— 這台機器以外連不進來。沒有認證是刻意的：
它讀寫的只有一個本機設定檔，且監聽範圍就在本機。

【核心層】對抗式覆核的審查者設定，跟業務無關。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "reviewer_config.json")
HTML_PATH = os.path.join(HERE, "index.html")
HOST, PORT = "127.0.0.1", 8899

# Cursor CLI 的 Windows 原生安裝落點（官方安裝腳本 `irm 'https://cursor.com/install?win32=true' | iex`
# 會把 agent.cmd／agent.ps1／cursor-agent.* 複製到這裡並寫進 User PATH）。
# ⚠ 只靠 `shutil.which("agent")` 會漏判：安裝時寫的是 **User PATH**，
# 已經開著的行程（含這支服務、含 Claude Code）不會拿到更新後的 PATH，
# which 回 None 但東西其實裝好了 —— 那會讓選單顯示「未安裝」而誘導人改選別的審查者。
CURSOR_AGENT_CMD = os.path.join(os.environ.get("LOCALAPPDATA", ""), "cursor-agent", "agent.cmd")


def detect_host_platform() -> str:
    """執行 `--check`／skill 的這一則是哪個平台（不是審查者行程）。

    最內層贏：`CURSOR_AGENT` 有值就判 Cursor，即使同時有 `CLAUDECODE`。
    從 Claude 拉起 `agent.cmd` 時父行程環境會整包遺傳，兩邊旗標會同時在；
    若先看 `CLAUDECODE` 會把審查者行程誤判成作者。
    """
    if os.environ.get("CURSOR_AGENT"):
        return "cursor"
    agent = str(os.environ.get("AI_AGENT") or "")
    if os.environ.get("CLAUDECODE") or agent.startswith("claude-code"):
        return "claude"
    return "unknown"


def required_reviewer_tool(host: str):
    """作者平台決定審查者必須在對側。設定檔與這條衝突時本輪覆寫，不要改檔。"""
    return {"cursor": "claude-code", "claude": "cursor-cli"}.get(host)

# 審查者工具。`probe` 是「這台機器上裝了沒」的偵測方式 —— 選單要照實顯示可用性，
# 讓人選之前就知道結果，而不是選了之後 skill 才回「沒裝，我用別的」。
TOOLS = [
    {
        "id": "claude-code",
        "name": "Claude Code",
        "desc": "作者在 Cursor 時的對側審查者：本機 `claude -p --safe-mode`（MAX OAuth）。"
                "作者在 Claude 時不要選它——那是自己審自己。"
                "有 Read/Grep/Bash 可查證、沒有 Edit/Write。",
        "probe": None,  # 作者在 Claude 裡一定可用；Cursor 側 skill 另查 claude.cmd
        "supports_model": True,
    },
    {
        "id": "codex",
        "name": "Codex CLI",
        "desc": "外部 CLI，與 Claude 完全不同的模型族。跨模型族的異質性是它唯一的優勢——同族審同族容易共享盲點。",
        "probe": "codex",
        "supports_model": False,
    },
    # ── cursor-cli 的操作細節（2026-08-25/26 SG-084 四輪實測）──────────────────
    # 放在這裡而不是 skill 檔：skill 有一次「不再寫死會過期的值」的精簡，把這些一起帶走了。
    # 下面每一條都是實跑撞出來的、不是推論，重跑一次的成本遠高於留著。
    #
    #   1. **一律背景執行**。一輪 10 分鐘以上（Grok xhigh），前景會撞工具逾時被砍，
    #      而且 PowerShell 的 `Out-File` **一個 byte 都不會 flush** ⇒ 只留下一個
    #      0 byte 的假 reply 檔，交換守門會把它誤判成「有回覆」。
    #   2. **`Out-File -Encoding utf8` 會加 BOM**，`ask-sha256` 那行會被守門認不出 ⇒
    #      落檔時用 `utf-8-sig` 讀、`utf-8` 寫。
    #   3. **唯讀靠 `--mode ask` 且不給 `--force`**。給了 `--force` 它就能改任何檔，
    #      而沙箱的 junction 指向的是真的程式碼目錄。
    #      （`--force` 那條路 2026-08-26 被 auto mode classifier 擋下，不要繞。）
    #   4. **審查者不一定照格式輸出 hash 行**：Grok 連兩輪都寫成 ``ask-sha256=`<hash>` ``
    #      （markdown code 標記），即使 prompt 明寫「不要用反引號包起來」。
    #      守門的正則已放寬到容許標記字元，**值本身仍逐字比對**。
    #   5. **沙箱的父目錄也要乾淨**：`D:\AI-Projects` 與 `D:\.ai-harness` 底下都有
    #      `CLAUDE.md`，把沙箱開在它們底下等於白做。實際落點 `D:\reviewer-sandbox`。
    #   6. **沙箱不是存取邊界，只是「不主動餵脈絡」**（2026-08-27 三組實測推翻舊敘述）：
    #      `--workspace` 官方語意就只是工作目錄、`--trust` 只是跳過確認提示。審查者
    #      **讀得到整台機器**——絕對路徑讀得到、沙箱內 junction 指向外部也讀得到、
    #      `--sandbox enabled` 在 Windows 直接 exit 1（原生沙箱限 macOS/Linux，且管的是
    #      command execution 不是 Read 工具）。要真的擋，在沙箱放 `.cursor/cli.json`
    #      的 `permissions.deny`（見 skill 步驟 3.1）。⚠ **deny 路徑在 Windows 必須用
    #      反斜線**：實測 `Read(D:/...)` 照樣讀得到且不報錯、`Read(D:\...)` 才擋得住，
    #      而官方範例寫的正是正斜線。⇒ 黑名單列不完，敏感題目仍然不要派。
    {
        "id": "cursor-cli",
        "name": "Cursor CLI（全自動）",
        "desc": "Cursor 官方 CLI（命令名 `agent`，Windows 原生、不需 WSL）。"
                "**跟 `cursor` 的差別是它不需要人**：skill 直接跑 "
                "`agent -p --mode ask --trust --workspace <沙箱> --model <slug>`，"
                "收 stdout 落檔，一輪從頭到尾沒有人工步驟。"
                "⚠ **一定要 `--workspace` 指到隔離沙箱**：CLI 會讀專案根的 `CLAUDE.md`、"
                "並從 `.claude/skills` 發現 skills（官方文件明載），直接在本 repo 跑等於"
                "讓審查者載入跟作者同一套脈絡，**「不共用推理脈絡」當場失效**。"
                "沙箱作法＝乾淨目錄 + junction 連要查證的程式碼目錄，不連 `CLAUDE.md`／`.claude`。"
                "⚠ **但沙箱不是存取邊界**（2026-08-27 實測）：它只保證 CLI 不會自動載入你的 "
                "`CLAUDE.md` 與 skills，**擋不住它主動去讀機器上任何檔案**。敏感題目不要派給它。"
                "⚠ 唯讀靠 `--mode ask` 且**不給 `--force`**；給了 `--force` 它就能改任何檔。",
        "probe": "agent",
        "probe_paths": [CURSOR_AGENT_CMD],
        "supports_model": True,
        "models_key": "cursor_cli",
    },
]

# claude-code 用的抽象模型檔位（由 Agent tool 的 model 參數承載）。
MODELS = [
    {"id": "inherit", "name": "跟隨主線", "desc": "不覆寫，用當前 session 的模型。"},
    {"id": "opus", "name": "Opus 5", "desc": "最強推理。對抗式覆核屬 CLAUDE.md §7 明列該切 Opus 的情境（架構規劃／硬規則區）。"},
    {"id": "sonnet", "name": "Sonnet 5", "desc": "省。適合覆核範圍小、爭點單純的計畫。"},
    {"id": "fable", "name": "Fable 5", "desc": "最硬的 audit 才用。§7 訂 <5% 且燒獨立額度，日常勿選。"},
]

# cursor-cli 吃的是 Cursor 自己的 model slug（`agent --list-models` 可列出當前帳號可用的）。
# **`family` 欄位是這張表存在的理由**：對抗式覆核的價值來自「不共用推理脈絡」，
# 而那件事由模型族決定，不是由「強不強」決定。選單要讓人一眼看到自己選的是不是同族。
# ⚠ slug 會隨 Cursor 改版增減。這張表是「推薦清單」不是白名單——
# 設定檔填了不在表上的 slug 時只警告、不判失敗（見 config_warnings），
# 因為擋下一個其實可用的新 slug，比放行一個打錯的字串傷害更大：
# 前者讓覆核跑不動（而人會改用預設＝自己審自己），後者 CLI 自己會報錯。
CURSOR_CLI_MODELS = [
    {"id": "cursor-grok-4.6-xhigh", "name": "Grok 4.6 Extra High", "family": "xAI",
     "desc": "跨模型族。2026-08-25 首次實跑（SG-084 四輪）：R2／R3／R4 各抓出 5／4／4 個新發現，"
             "且**沒有一輪重炒**——每一輪都打在作者上一輪剛寫下的處置上。"},
    {"id": "cursor-grok-4.6-high", "name": "Grok 4.6 High", "family": "xAI",
     "desc": "跨模型族、與 Extra High 同一顆模型，思考強度低一檔。爭點單純或想省成本時選它。"
             "⚠ `effort` 欄位對 cursor-cli **不生效**——強度只由 slug 尾巴承載（high／xhigh）。"},
    {"id": "gpt-5.3-codex-xhigh", "name": "Codex 5.3 Extra High", "family": "OpenAI",
     "desc": "跨模型族、專攻程式碼。計畫的爭點在「這段程式會不會這樣壞」時選它。"},
    {"id": "gpt-5.6-sol-xhigh", "name": "GPT-5.6 Sol Extra High", "family": "OpenAI",
     "desc": "跨模型族、通用推理強。爭點在「這個方案本身對不對」而非程式碼細節時選它。"},
    {"id": "gemini-3.1-pro", "name": "Gemini 3.1 Pro", "family": "Google",
     "desc": "跨模型族。前兩個審查者意見打架時，可當獨立的第三票。"},
    {"id": "claude-opus-5-thinking-high", "name": "Claude Opus 5 Thinking", "family": "Anthropic ⚠ 同族",
     "desc": "⚠ **與主 session 同模型族，共享盲點**。除非你要的是「同族但不同 context」的第二意見，"
             "否則選它等於削掉這支 skill 存在的理由。"},
]

MODEL_SETS = {"default": MODELS, "cursor_cli": CURSOR_CLI_MODELS}

# 每個 tool 的預設模型。**不能共用一個全域預設**（2026-08-25 矩陣測試抓到）：
# `DEFAULTS["model"]` 是 `opus`，那是 claude-code 的抽象檔位、對 cursor-cli 是不存在的 slug。
# 有人把 tool 改成 cursor-cli 卻忘了改 model 時，skill 會拿 `opus` 去餵 CLI，
# 錯誤會發生在第一輪覆核的中途、訊息還很難懂（模型不存在）。
# 這裡選 grok 當預設是因為它跨模型族——預設值該落在「這支 skill 存在的理由」那一側。
TOOL_DEFAULT_MODEL = {"cursor-cli": "cursor-grok-4.6-xhigh"}


def default_model_for(tool_id: str) -> str:
    return TOOL_DEFAULT_MODEL.get(tool_id, DEFAULTS["model"])


def models_for(tool_id: str) -> list:
    """哪個工具吃哪一組模型清單。

    不能只有一組 `MODELS`（2026-08-25）：`cursor-cli` 吃的是 Cursor 的 slug
    （`cursor-grok-4.6-xhigh`），`claude-code` 吃的是抽象檔位（`opus`）。
    共用一組的話，兩邊必有一邊的合法值被判成「未知值」而讓 `--check` exit 2。
    """
    tool = next((t for t in TOOLS if t["id"] == tool_id), None)
    if not tool or not tool.get("supports_model"):
        return MODELS
    return MODEL_SETS.get(tool.get("models_key", "default"), MODELS)

EFFORTS = [
    {"id": "high", "name": "high", "desc": "預設。挑錯要夠深才有價值。"},
    {"id": "medium", "name": "medium", "desc": "範圍小的計畫可降。"},
    {"id": "max", "name": "max", "desc": "最貴。真的卡住、前幾輪都沒挑出東西時才用。"},
]

DEFAULTS = {"tool": "claude-code", "model": "opus", "effort": "high"}


def load_config() -> dict:
    """讀設定；缺欄位用預設補齊。讀不到就回全預設 —— 這個檔壞掉不該讓覆核跑不動。"""
    cfg = dict(DEFAULTS)
    given = set()
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        for k in DEFAULTS:
            if data.get(k):
                cfg[k] = data[k]
                given.add(k)
    except Exception:
        pass
    # model 沒填時要依 **tool** 補預設，不能一律落回 DEFAULTS["model"]（＝opus）：
    # 那對 cursor-cli 是不存在的 slug。見 TOOL_DEFAULT_MODEL。
    if "model" not in given:
        cfg["model"] = default_model_for(cfg["tool"])
    return cfg


def config_load_issues() -> list:
    """設定**沒讀到**的時候要出聲（2026-08-25 覆核 R1-1）。

    `config_warnings()` 只在「值有填但不是已知值」時出聲。檔案不存在、JSON 壞掉、
    欄位缺、值是空字串——這四種都會安靜地落回 `DEFAULTS`，也就是 `claude-code`。
    畫面印「審查者：claude-code（可用）」、warnings 空、exit 0，
    **看起來完全就像「本來就選了 Claude」**。

    後果正是這支 skill 存在的理由的反面：設定原本是 cursor，檔一壞就退回自己審自己，
    而且沒有任何一個訊號會讓人或模型發現曾經是 cursor。

    所以這四種一律出聲並讓 `--check` 非零。這不是「設定檔壞掉就不讓覆核跑」——
    非零的意思是「停下來問人」，不是崩潰。
    """
    issues = []
    if not os.path.exists(CONFIG_PATH):
        return [f"設定檔不存在：{CONFIG_PATH} —— 現在用的是預設值 "
                f"{DEFAULTS['tool']}，那是 Claude 審 Claude。先建檔或跑設定頁。"]
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except Exception as exc:
        return [f"設定檔讀不了（{type(exc).__name__}）—— 現在用的是預設值 "
                f"{DEFAULTS['tool']}，那是 Claude 審 Claude。修好它，不要就這樣跑下去。"]
    if not isinstance(data, dict):
        return ["設定檔最外層不是物件 —— 全部欄位都會落回預設。"]
    for k in DEFAULTS:
        if k not in data:
            issues.append(f"缺欄位 {k} —— 已落回預設「{DEFAULTS[k]}」")
        elif not data[k]:
            issues.append(f"欄位 {k} 是空的 —— 已落回預設「{DEFAULTS[k]}」")
    return issues


def config_warnings(cfg: dict) -> list:
    """未知設定值不得靜默吞掉（2026-08-25 對抗式覆核 R1-3）。

    原本 `load_config()` 只補缺欄位、**不驗值**，而 `save_config()` 驗不過就塞回預設。
    兩者合起來的效果是：**手改成未知值活得下來**（`--check` 只印裸 id，看起來一切正常），
    **經設定頁存一次就被靜默改寫成 claude-code**（畫面上看起來像選了別的）。
    兩條路徑都不出聲，而它們的後果是「以為找了外部審查者、其實在自己審自己」。

    這支只回警告不改值——設定檔壞掉不該讓覆核跑不動，但也不該安靜。
    """
    valid = {
        "tool": {t["id"] for t in TOOLS},
        # 模型的合法集合**依 tool 而定**（2026-08-25 加 cursor-cli 時發現）：
        # claude-code 吃抽象檔位（opus），cursor-cli 吃 Cursor 的 slug（cursor-grok-4.6-xhigh）。
        "model": {m["id"] for m in models_for(cfg.get("tool"))},
        "effort": {e["id"] for e in EFFORTS},
    }
    out = []
    for key, allowed in valid.items():
        val = cfg.get(key)
        if val in allowed:
            continue
        # cursor-cli 的 model 是「推薦清單」不是白名單：slug 會隨 Cursor 改版增減，
        # 擋下一個其實可用的新 slug ⇒ 覆核跑不動 ⇒ 人改用預設（claude-code）＝自己審自己，
        # 那比放行一個打錯的字串更糟（打錯的話 CLI 自己會報錯，而且是當場報）。
        # 所以這一格只提醒、不列入 --check 的失敗條件。
        if key == "model" and cfg.get("tool") == "cursor-cli":
            out.append(f"ℹ 設定檔的 model=「{val}」不在推薦清單內。"
                       f"這不算錯（Cursor 的 slug 會改版），但**沒人替你驗過它存在**——"
                       f"跑 `agent --list-models` 確認，打錯的話 CLI 會在第一輪就失敗。")
            continue
        out.append(f"設定檔的 {key}=「{val}」不是已知值"
                   f"（已知：{'／'.join(sorted(allowed))}）"
                   f"——skill 必須拒跑並說出來，不得挑一個分支兜底。")
    return out


def blocking_warnings(cfg: dict) -> list:
    """`--check` 的**失敗**條件（把提醒排除在外）。

    `config_warnings()` 現在同時裝「錯誤」與「提醒」（cursor-cli 的未知 slug 屬後者）。
    exit code 只能由前者決定 —— 否則換一個新 slug 就讓 `--check` 紅掉，
    而 skill 的規則是「看到非零就停下來問人」，等於每次改 slug 都要人介入一次。
    """
    return [w for w in config_warnings(cfg) if not w.startswith("ℹ")]


def save_config(cfg: dict) -> list:
    """寫設定，並**回報哪些欄位被正規化掉了**（2026-08-25 覆核 R1-2）。

    正規化本身是對的（不該把垃圾寫進檔案），錯的是**不出聲**：
    未知值進來時 `--check` 本來會 exit 2，存一次之後值變合法、警告消失、exit 0
    —— 證據被自己抹掉了。回傳的清單讓呼叫端能把「我改了你的輸入」講出來。
    """
    valid_tools = {t["id"] for t in TOOLS}
    # 模型清單依 tool 決定（見 models_for）。先把 tool 正規化，再據以取模型集合——
    # 否則「送了 cursor-cli + 它的 slug」會被舊的單一 MODELS 判成未知值而洗成 opus。
    _tool = cfg.get("tool") if cfg.get("tool") in valid_tools else DEFAULTS["tool"]
    valid_models = {m["id"] for m in models_for(_tool)}
    # cursor-cli 的 slug 是開放集合（Cursor 改版會增減），存檔時不得因為「不在推薦清單」
    # 就洗成預設 —— 那會把使用者剛選好的跨族審查者，靜靜換成同族的 opus。
    _model_open = (_tool == "cursor-cli")
    valid_efforts = {e["id"] for e in EFFORTS}

    def _dflt(k: str) -> str:
        """訊息裡要報的「預設值」——model 那格依 tool 而定（見 TOOL_DEFAULT_MODEL）。

        不能直接寫 `DEFAULTS[k]`：tool=cursor-cli 時它會說「已寫成預設 opus」，
        但實際寫進去的是 grok 的 slug —— 訊息與行為不符比沒有訊息更糟。
        """
        return default_model_for(_tool) if k == "model" else DEFAULTS[k]
    # ⚠ 條件不能寫成 `cfg.get(k) is not None and ...`（2026-08-25 覆核 R2-4）：
    # 那樣「欄位根本沒送來」就不進 rejected，但下面照樣寫成 DEFAULTS。
    # 效果是 POST `{}` 或只送 model／effort，會把磁碟上的 cursor 洗成 claude-code
    # 而 API 回「rejected: []、ok: true」—— 修 R1-2 時把「未知值靜默」換成了
    # 「缺欄位靜默」，同一個洞換個入口。
    rejected = []
    for k, allowed in (("tool", valid_tools), ("model", valid_models),
                       ("effort", valid_efforts)):
        if k not in cfg:
            rejected.append(f"沒有送 {k}，已寫成預設「{_dflt(k)}」"
                            f"（原本的值會被覆蓋掉）")
        elif cfg[k] not in allowed:
            if k == "model" and _model_open and str(cfg[k]).strip():
                # 開放集合：照收，但要出聲說「沒人替你驗過」。
                rejected.append(f"model=「{cfg[k]}」不在 cursor-cli 的推薦清單內，已照原樣寫入"
                                f"——請用 `agent --list-models` 確認它存在。")
                continue
            rejected.append(f"{k}=「{cfg[k]}」不是已知值，已寫成預設「{_dflt(k)}」")

    def _model_out():
        v = cfg.get("model")
        if v in valid_models:
            return v
        if _model_open and str(v or "").strip():
            return v
        return default_model_for(_tool)

    out = {
        "tool": cfg.get("tool") if cfg.get("tool") in valid_tools else DEFAULTS["tool"],
        "model": _model_out(),
        "effort": cfg.get("effort") if cfg.get("effort") in valid_efforts else DEFAULTS["effort"],
        "note": ("由 D:\\.ai-harness\\reviewer\\Launch-Reviewer.bat 開啟網頁修改；"
                 "/adversarial-review 每次執行時讀這個檔。手改也可以，改完存檔即生效"
                 "（skill 是每次重讀，不快取）。"),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    for r in rejected:
        print(f"  ✘ 存檔時正規化：{r}")
    return rejected


def tool_available(tool: dict) -> bool:
    if not tool.get("probe"):
        return True
    if shutil.which(tool["probe"]) is not None:
        return True
    # PATH 沒有不代表沒裝（見 CURSOR_AGENT_CMD 的註解：安裝寫的是 User PATH，
    # 已開著的行程拿不到）。再看一次固定安裝落點才算數。
    return any(p and os.path.exists(p) for p in tool.get("probe_paths", []))


def state() -> dict:
    cfg = load_config()
    tools = []
    for t in TOOLS:
        tools.append({**{k: v for k, v in t.items() if k != "probe"},
                      "available": tool_available(t)})
    # `issues` 是給設定頁看的（2026-08-25 覆核 R2-5）：警告原本只掛在 `--check`，
    # 走瀏覽器那條路的人看到的是「沒有 radio 被勾」而已，不像壞掉。
    # 按下儲存就落進正規化，cursor 被洗成 claude-code 而畫面全程沒說。
    return {"config": cfg, "tools": tools,
            # `models` 是「當前 tool 對應的那組」，`model_sets` 讓設定頁在使用者切換
            # 審查者時，不必重新請求就能換掉模型 radio —— 兩個工具的模型清單不同，
            # 沿用上一個工具的清單會讓人選到一個對新工具無效的值。
            "models": models_for(cfg.get("tool")), "model_sets": MODEL_SETS,
            "efforts": EFFORTS,
            "config_path": CONFIG_PATH,
            "issues": config_load_issues() + config_warnings(cfg)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(HTML_PATH, encoding="utf-8") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            except Exception as exc:
                return self._send(500, f"讀不到 index.html：{exc}", "text/plain; charset=utf-8")
        if self.path == "/api/state":
            return self._send(200, json.dumps(state(), ensure_ascii=False))
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/config":
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            n = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            rejected = save_config(payload)
            return self._send(200, json.dumps({"ok": True, "config": load_config(),
                                               "rejected": rejected},
                                              ensure_ascii=False))
        except Exception as exc:
            return self._send(400, json.dumps({"error": str(exc)}, ensure_ascii=False))

    def log_message(self, *args):
        pass  # 不要每個請求都印一行洗掉真正要看的訊息


def print_state() -> None:
    st = state()
    cfg = st["config"]
    host = detect_host_platform()
    need = required_reviewer_tool(host)
    tool = next((t for t in st["tools"] if t["id"] == cfg["tool"]), None)
    print(f"設定檔：{CONFIG_PATH}")
    print(f"  作者平台：{host}")
    print(f"  審查者：{cfg['tool']}" + ("" if not tool else
          f"（{tool['name']}·{'可用' if tool['available'] else '⚠ 這台機器上找不到'}）"))
    print(f"  模型　：{cfg['model']}")
    print(f"  effort：{cfg['effort']}")
    if host == "unknown":
        print("  ⚠ 認不出作者平台（沒有 CURSOR_AGENT / CLAUDECODE）——停下來問人，不准猜。")
    elif need and cfg["tool"] != need and cfg["tool"] != "codex":
        print(f"  ⚠ 設定是 {cfg['tool']}，作者平台要求對側 {need}。"
              f"本輪改走 {need}，不要改設定檔（下一則可能在另一平台）。")
    for w in config_load_issues() + config_warnings(cfg):
        print(f"  ✘ {w}")
    if cfg["tool"] == "cursor-cli":
        _m = next((m for m in CURSOR_CLI_MODELS if m["id"] == cfg["model"]), None)
        _fam = _m["family"] if _m else "未知（不在推薦清單）"
        print(f"  ℹ Cursor CLI 全自動，模型族＝{_fam}")
        if _m and "同族" in _m["family"]:
            print("    ⚠ **這個模型跟主 session 同族，共享盲點**——"
                  "除非刻意要同族第二意見，否則換一個跨族的 slug。")
        print("    ⚠ 跑的時候一定要 `--workspace` 指到隔離沙箱："
              "CLI 會讀專案根 CLAUDE.md 與 .claude/skills，"
              "在本 repo 直接跑＝審查者載入跟作者同一套脈絡。")
    for t in st["tools"]:
        if not t["available"]:
            print(f"  ⚠ {t['name']} 未安裝——選了它，skill 會回報找不到並改用可用的審查者"
                  "（此規則不適用 Cursor，見上）")


def main() -> int:
    if "--check" in sys.argv:
        print_state()
        # 設定值不合法時要**非零退出**，不只是印一行（2026-08-25 覆核 R1-3／V1）：
        # 「明講」是散文、擋不住抄近路；exit code 才是別的腳本與 skill 步驟能檢查的東西。
        # 讀不到／欄位空掉也算（R1-1）——那會安靜地退回 claude-code，也就是自己審自己。
        # 用 blocking_warnings 而不是 config_warnings：後者現在也裝「提醒」
        # （cursor-cli 的未知 slug），那不該讓 --check 紅掉 —— skill 的規則是
        # 「非零就停下來問人」，每換一次 slug 就要人介入一次會逼人繞過這道檢查。
        return 2 if (config_load_issues() or blocking_warnings(load_config())) else 0
    print_state()
    url = f"http://{HOST}:{PORT}/"
    print(f"\n設定頁：{url}　（Ctrl+C 結束）")
    try:
        httpd = HTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"\n起不了服務（{exc}）——多半是 {PORT} 埠已被占用，可能你已經開過一個。"
              f"\n先開 {url} 看看是不是已經在跑了。")
        return 1
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已結束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
