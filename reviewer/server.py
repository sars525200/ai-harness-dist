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

# 審查者工具。`probe` 是「這台機器上裝了沒」的偵測方式 —— 選單要照實顯示可用性，
# 讓人選之前就知道結果，而不是選了之後 skill 才回「沒裝，我用別的」。
TOOLS = [
    {
        "id": "claude-code",
        "name": "Claude Code",
        "desc": "開一個獨立 subagent（不共用推理脈絡）。有 Read/Grep/Bash 可查證、沒有 Edit/Write——符合「審查者只能挑錯、不能動手」的邊界。",
        "probe": None,  # 就是當前執行環境，一定可用
        "supports_model": True,
    },
    {
        "id": "cursor",
        "name": "Cursor（落檔交換）",
        "desc": "另一個 IDE 上的另一個模型——這台機器上唯一真正不共用推理脈絡的審查者。"
                "程式叫不到它（ListAgents 看不見 Cursor），所以走落檔交換："
                "skill 寫題目檔、人貼進 Cursor、Cursor 把發現寫回檔、skill 讀回來逐項處置。"
                "⚠ 它需要人動手貼一次，不是全自動。**它沒有「不可用」這個狀態，只有「還沒回」**"
                "——還沒回就是等，不是改派別人。",
        # probe 刻意留 None：cursor 的「可用」**不是**「這台機器裝了沒」。
        # 2026-08-25 實測 `shutil.which("cursor")` 在 Cursor 自己的 process 有值、
        # 在 Claude 這側是 None —— 同一個判準對不同的提問者給不同答案，
        # 拿它當可用性會製造假訊號（一側顯示可用、另一側靜默退回自己審自己）。
        # 真正的可用性判準是「這一輪有沒有合格的回覆檔」，那由 skill 步驟驗，不在這裡。
        "probe": None,
        "supports_model": False,
    },
    {
        "id": "codex",
        "name": "Codex CLI",
        "desc": "外部 CLI，與 Claude 完全不同的模型族。跨模型族的異質性是它唯一的優勢——同族審同族容易共享盲點。",
        "probe": "codex",
        "supports_model": False,
    },
]

MODELS = [
    {"id": "inherit", "name": "跟隨主線", "desc": "不覆寫，用當前 session 的模型。"},
    {"id": "opus", "name": "Opus 5", "desc": "最強推理。對抗式覆核屬 CLAUDE.md §7 明列該切 Opus 的情境（架構規劃／硬規則區）。"},
    {"id": "sonnet", "name": "Sonnet 5", "desc": "省。適合覆核範圍小、爭點單純的計畫。"},
    {"id": "fable", "name": "Fable 5", "desc": "最硬的 audit 才用。§7 訂 <5% 且燒獨立額度，日常勿選。"},
]

EFFORTS = [
    {"id": "high", "name": "high", "desc": "預設。挑錯要夠深才有價值。"},
    {"id": "medium", "name": "medium", "desc": "範圍小的計畫可降。"},
    {"id": "max", "name": "max", "desc": "最貴。真的卡住、前幾輪都沒挑出東西時才用。"},
]

DEFAULTS = {"tool": "claude-code", "model": "opus", "effort": "high"}


def load_config() -> dict:
    """讀設定；缺欄位用預設補齊。讀不到就回全預設 —— 這個檔壞掉不該讓覆核跑不動。"""
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        for k in DEFAULTS:
            if data.get(k):
                cfg[k] = data[k]
    except Exception:
        pass
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
        "model": {m["id"] for m in MODELS},
        "effort": {e["id"] for e in EFFORTS},
    }
    out = []
    for key, allowed in valid.items():
        val = cfg.get(key)
        if val not in allowed:
            out.append(f"設定檔的 {key}=「{val}」不是已知值"
                       f"（已知：{'／'.join(sorted(allowed))}）"
                       f"——skill 必須拒跑並說出來，不得挑一個分支兜底。")
    return out


def save_config(cfg: dict) -> list:
    """寫設定，並**回報哪些欄位被正規化掉了**（2026-08-25 覆核 R1-2）。

    正規化本身是對的（不該把垃圾寫進檔案），錯的是**不出聲**：
    未知值進來時 `--check` 本來會 exit 2，存一次之後值變合法、警告消失、exit 0
    —— 證據被自己抹掉了。回傳的清單讓呼叫端能把「我改了你的輸入」講出來。
    """
    valid_tools = {t["id"] for t in TOOLS}
    valid_models = {m["id"] for m in MODELS}
    valid_efforts = {e["id"] for e in EFFORTS}
    # ⚠ 條件不能寫成 `cfg.get(k) is not None and ...`（2026-08-25 覆核 R2-4）：
    # 那樣「欄位根本沒送來」就不進 rejected，但下面照樣寫成 DEFAULTS。
    # 效果是 POST `{}` 或只送 model／effort，會把磁碟上的 cursor 洗成 claude-code
    # 而 API 回「rejected: []、ok: true」—— 修 R1-2 時把「未知值靜默」換成了
    # 「缺欄位靜默」，同一個洞換個入口。
    rejected = []
    for k, allowed in (("tool", valid_tools), ("model", valid_models),
                       ("effort", valid_efforts)):
        if k not in cfg:
            rejected.append(f"沒有送 {k}，已寫成預設「{DEFAULTS[k]}」"
                            f"（原本的值會被覆蓋掉）")
        elif cfg[k] not in allowed:
            rejected.append(f"{k}=「{cfg[k]}」不是已知值，已寫成預設「{DEFAULTS[k]}」")
    out = {
        "tool": cfg.get("tool") if cfg.get("tool") in valid_tools else DEFAULTS["tool"],
        "model": cfg.get("model") if cfg.get("model") in valid_models else DEFAULTS["model"],
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
    if not tool["probe"]:
        return True
    return shutil.which(tool["probe"]) is not None


def state() -> dict:
    cfg = load_config()
    tools = []
    for t in TOOLS:
        tools.append({**{k: v for k, v in t.items() if k != "probe"},
                      "available": tool_available(t)})
    # `issues` 是給設定頁看的（2026-08-25 覆核 R2-5）：警告原本只掛在 `--check`，
    # 走瀏覽器那條路的人看到的是「沒有 radio 被勾」而已，不像壞掉。
    # 按下儲存就落進正規化，cursor 被洗成 claude-code 而畫面全程沒說。
    return {"config": cfg, "tools": tools, "models": MODELS, "efforts": EFFORTS,
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
    tool = next((t for t in st["tools"] if t["id"] == cfg["tool"]), None)
    print(f"設定檔：{CONFIG_PATH}")
    print(f"  審查者：{cfg['tool']}" + ("" if not tool else
          f"（{tool['name']}·{'可用' if tool['available'] else '⚠ 這台機器上找不到'}）"))
    print(f"  模型　：{cfg['model']}")
    print(f"  effort：{cfg['effort']}")
    for w in config_load_issues() + config_warnings(cfg):
        print(f"  ✘ {w}")
    if cfg["tool"] == "cursor":
        # ⚠ 這段措辭刻意不寫「可用＝有沒有回覆檔」（2026-08-25 覆核 R2-6）：
        # 那個講法會把「還沒貼」讀成「不可用」，而下一行 Codex 的說明正好在教
        # 「不可用就改用可用的審查者」。兩句合起來就是一張換人許可證。
        print("  ℹ Cursor 是**人工通道**，永遠算可用。它沒有「不可用」這個狀態，只有「還沒回」。")
        print("    skill 會寫題目檔然後**停下來等人貼**。等不到不是換人的理由——換人必須是人下的指令。")
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
        return 2 if (config_load_issues() or config_warnings(load_config())) else 0
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
