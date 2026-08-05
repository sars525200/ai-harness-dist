"""Step 0 schema spike —— 唯讀，只記錄不干預。

目的：確認 Claude Code hook 的真實契約，不靠記憶寫 schema。
   1. stdin JSON 的實際欄位名（tool_name / tool_input / session_id / cwd …）
   2. 各 hook 事件的實際觸發時機 —— 特別是 Stop 是每回合還是收工（D5 的前提）
   3. exit code 語意

安全設計（會與並行 session 共存，必須絕對無害）：
   * **stdout 保持全空** —— hook 的 stdout 可能被解析成控制指令或注入模型 context，
     這裡只寫檔案，不輸出任何東西。
   * **一律 exit 0** —— 任何例外都吞掉（fail-open，§6）。
   * 只寫入 D:\\.ai-harness\\state\\spike\\，不碰任何專案檔。

【核心層】探測平台的 hook 契約，跟被服務的是哪個專案無關。
"""
import sys, json, os, time

SPIKE_DIR = r"D:\.ai-harness\state\spike"


def main() -> None:
    # 用 utf-8-sig 讀 binary：容忍 UTF-8 BOM。
    # 實測（2026-07-28）：PowerShell 管線寫入 native command 的 stdin 時會加 BOM，
    # 純 json.loads 會直接失敗 → 落進解析失敗分支 → 配上 fail-open 就是「規則靜默死亡」（D7）。
    # 未來所有 hook 都必須這樣讀 stdin。
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    os.makedirs(SPIKE_DIR, exist_ok=True)

    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"_unparsed_raw": raw}

    event = payload.get("hook_event_name", "UNKNOWN")
    # 單調遞增檔名：同一秒內多次觸發也不覆蓋，並保留順序
    stamp = f"{time.time():.6f}".replace(".", "_")

    record = {
        "_captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "_event": event,
        "_argv": sys.argv[1:],
        "_top_level_keys": sorted(payload.keys()) if isinstance(payload, dict) else None,
        "payload": payload,
    }

    with open(os.path.join(SPIKE_DIR, f"{stamp}_{event}.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # fail-open：spike 絕不能影響任何 session
        try:
            os.makedirs(SPIKE_DIR, exist_ok=True)
            with open(os.path.join(SPIKE_DIR, "_spike_errors.log"), "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\t{type(exc).__name__}: {exc}\n")
        except Exception:
            pass
    sys.exit(0)
