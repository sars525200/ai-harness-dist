"""Stop hook exit-2 語意隔離探針（STOP_HOOK_MARKER_PLAN.md §3.2-A → A1）。

要驗兩件事，這兩件是 marker 機制的地基（HARNESS_PLAN.md §-0.5「未驗項」）：
  1. Stop hook 回 exit 2 是否**真的擋得住** Stop（模型會不會被逼著再產出一輪）
  2. stderr 的訊息是否**真的餵回模型**（模型看不看得到擋阻理由）

驗法：第一次 Stop 回 exit 2，stderr 塞一句「請原樣輸出 ACK-7F3A-CONFIRMED」的暗號指令。
      若最終輸出含該暗號 → 兩件事同時成立（擋住了，且模型讀到了訊息）。
      若被擋但輸出不含暗號 → 擋得住、但訊息沒餵回（或模型沒遵守）。
      若完全沒被擋（只有 seq=1 且直接結束）→ exit 2 對 Stop 無效。

安全設計：只擋第一次（seq==1 且 stop_hook_active 為假），之後一律放行 → 不可能無限迴圈。
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "probe_log.ndjson"
TOKEN = "ACK-7F3A-CONFIRMED"

# BOM-safe 讀取（§-0.5 發現 4：stdin 可能帶 UTF-8 BOM，sys.stdin.read() 會炸）
raw = sys.stdin.buffer.read().decode("utf-8-sig")
try:
    payload = json.loads(raw)
except Exception as exc:  # 探針不 fail-open 成靜默，記下來
    payload = {"_parse_error": repr(exc), "_raw_head": raw[:400]}

prev = 0
if LOG.exists():
    prev = sum(1 for ln in LOG.read_text(encoding="utf-8").splitlines() if ln.strip())
seq = prev + 1

entry = {
    "seq": seq,
    "hook_event_name": payload.get("hook_event_name"),
    "stop_hook_active": payload.get("stop_hook_active"),
    "session_id": payload.get("session_id"),
    "cwd": payload.get("cwd"),
    "last_assistant_message": (payload.get("last_assistant_message") or "")[:400],
    "payload_keys": sorted(payload.keys()),
}

will_block = seq == 1 and not payload.get("stop_hook_active")
entry["action"] = "BLOCK(exit2)" if will_block else "ALLOW(exit0)"

with LOG.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

if will_block:
    sys.stderr.write(
        "PROBE-BLOCK-7F3A: 這是一個 hook 攔截測試，不是真的錯誤。"
        f"請在你的下一則回覆中原樣輸出這串暗號：{TOKEN}，然後就結束，不要做別的事。"
    )
    sys.exit(2)

sys.exit(0)
