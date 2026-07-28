"""R3 —— push 邊界觀察：ops timer 腳本改了但只 git push 沒 scp（會漏更新）。

CLAUDE.md §9：「ops timer 腳本跑 /srv/it-asset-backup/ 副本→git push 不更新·
必 scp（已咬兩次）」。2026-07-28 讀 systemd .service 檔的 ExecStart 逐支
查證（非只信記憶檔字面）確認範圍：

    it-asset-backup.service       → /srv/it-asset-backup/backup_db.sh
    it-asset-health.service       → /srv/it-asset-backup/health_check.py
    it-asset-daily-report.service → /srv/it-asset-backup/daily_report.py
    it-asset-backup-mail.service  → /srv/it-asset-backup/offsite_backup_mail.py

    例外：it-asset-monitor.service 的 ExecStart 是
    /srv/it-asset/SOP_PROD/05_UI_Demo/ops/attack_monitor.py（repo 路徑），
    git push vm 就會更新它，attack_monitor.py 不在下面這份清單裡。
    這個例外是 R3 存在的理由——如果所有 ops/ 腳本都走同一條部署路徑，
    這條規則就沒有必要（單純提醒「改了 ops/ 就 scp」還比較簡單，
    但那樣會對 attack_monitor.py 產生錯誤的提醒）。

跟 R1 同一套設計：掛 git push vm 這個 push 邊界，不是攔截 scp 指令本身
——在忘記 scp 之前、push 當下就提醒，比事後驗證 scp 有沒有做對更早也更有用。
理由同 D5：掛在別的時機容易變成疲勞或抓不到重點。
"""
from __future__ import annotations

import posixpath

from contract import allow, is_push_to_remote, warn

RULE_ID = "R3"

# 相對 repo root 的路徑。2026-07-28 逐支讀 SOP_PROD/05_UI_Demo/ops/*.service
# 的 ExecStart 驗證過，非只信記憶檔——之後任何新增/移除這類 timer，
# 這份清單要跟著 .service 檔同步更新，否則會跟 F5（手抄文件漂移）同款失效。
_BACKUP_COPY_SCRIPTS = frozenset({
    "SOP_PROD/05_UI_Demo/ops/backup_db.sh",
    "SOP_PROD/05_UI_Demo/ops/health_check.py",
    "SOP_PROD/05_UI_Demo/ops/daily_report.py",
    "SOP_PROD/05_UI_Demo/ops/offsite_backup_mail.py",
})


def applies(ctx) -> bool:
    return is_push_to_remote(ctx.command, "vm")


def check(ctx):
    if not applies(ctx):
        return allow()

    ref = ctx.git.resolve_remote_ref("vm", "master")
    if not ref:
        return allow()  # fail-open，同 DB-1/R1：地基算不出來就不硬猜

    changed = set(ctx.git.diff_names(f"{ref}..HEAD"))
    hit = sorted(changed & _BACKUP_COPY_SCRIPTS)
    if not hit:
        return allow()

    names = "、".join(posixpath.basename(p) for p in hit)
    return warn(
        f"CLAUDE.md §9：這次要推的內容含 {names}——這幾支 ops timer 腳本"
        "實際執行路徑是 /srv/it-asset-backup/ 的獨立副本，git push vm 不會更新它，"
        "已咬過 2 次。推完後記得 scp 到 /srv/it-asset-backup/ 並手動驗證一次"
        "（例如 python3 /srv/it-asset-backup/health_check.py）。"
    )
