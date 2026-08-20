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

【專案層】ops timer 腳本跑在 /srv/it-asset-backup 副本，綁本平台的 VM 佈署。
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
    # 2026-08-20 補這兩支（原本漏）。證據：`ops/backup_db.sh:58` 每天做
    #   cp -p "$BACKUP_ROOT/restore_from_gpg.sh" "$BACKUP_ROOT/RESTORE_RUNBOOK.md" "$dest/"
    # 而 `$BACKUP_ROOT` 就是 /srv/it-asset-backup（同檔 L10）⇒ 它們與上面四支
    # 走**完全一樣**的部署路徑。漏掉的後果特別難發現：復原包裡會裝進一份**過期的
    # 還原腳本與 RUNBOOK**，而那份東西**只有在真的要災難復原時才會被執行**
    # —— 平時零症狀，需要它的那一天才發現它是舊的。
    "SOP_PROD/05_UI_Demo/ops/restore_from_gpg.sh",
    "SOP_PROD/05_UI_Demo/ops/RESTORE_RUNBOOK.md",
})

# ── 第三條部署路徑：/etc（2026-08-20 補·原本完全沒有守門）────────────────────
#
# systemd unit 與 fail2ban 設定的實際落點是 `/etc/systemd/system` 與 `/etc/fail2ban`，
# 而**現有兩條部署路徑都到不了那裡**：
#   · `git push vm master` 的 post-receive 只做 `git checkout -f --work-tree=/srv/it-asset`
#     ＋ `systemctl restart it-asset` —— 不碰 /etc。
#   · scp 到 /srv/it-asset-backup/ 也不碰 /etc。
# ⇒ 改了 `ops/*.service`／`*.timer`／`fail2ban-*` 再 push，**live 設定一個字都沒變，
#   而且不會報錯**。這是 R3 原本三條路徑裡唯一沒人守的那條。
#
# 證據（逐處查過，不是憑記憶）：`ops/backup_db.sh:49` 是從 `/etc/systemd/system/`
# **備份出來**、`ops/restore_from_gpg.sh:153` 是**還原回去**、
# `docs/UBUNTU_MIGRATION_PLAN.md:247` 寫「建立 /etc/systemd/system/it-asset.service」。
#
# ⚠ **判準綁副檔名而非目錄**：systemd unit 一律住 /etc/systemd/system，不管它在 repo
#   裡放哪個資料夾（實際就有兩處：`05_UI_Demo/ops/` 與 `SOP_PROD/ops/systemd/`）。
#   綁目錄的話搬一次資料夾就靜默失效，那是 F5（手抄清單漂移）同款。
# ⚠ **沒有例外**：`it-asset-monitor.service` 的 ExecStart 指向 repo 路徑（那是 R3 上半段
#   那個例外的由來），但 **unit 檔本身仍然住在 /etc**，所以它一樣要手動裝。
#   兩個「例外」講的不是同一件事，別把上面那段的例外套到這裡來。
# 校準：2026-06-01 起 3,886 個 commit 裡只有 10 個動過這三類檔（0.26%）⇒ 不會疲勞。
_ETC_SUFFIXES = (".service", ".timer")
_ETC_PREFIXES = ("fail2ban-",)


def _needs_etc_install(path: str) -> bool:
    base = posixpath.basename(path)
    return base.endswith(_ETC_SUFFIXES) or base.startswith(_ETC_PREFIXES)


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
    etc_hit = sorted(p for p in changed if _needs_etc_install(p))
    if not hit and not etc_hit:
        return allow()

    # 兩類**分開講**：補救動作不同（一個是 scp 到備份副本，一個是 sudo cp 到 /etc
    # 再 daemon-reload）。混成一段的話，人只會做他先看到的那一個。
    parts = []
    if hit:
        names = "、".join(posixpath.basename(p) for p in hit)
        parts.append(
            f"①**要 scp 到 /srv/it-asset-backup/**：{names}。"
            "這幾支的實際執行路徑是 /srv/it-asset-backup/ 的獨立副本，"
            "git push vm 不會更新它（已咬過 2 次）。推完後 scp 過去並手動驗證一次"
            "（例如 python3 /srv/it-asset-backup/health_check.py）。"
        )
    if etc_hit:
        names = "、".join(posixpath.basename(p) for p in etc_hit)
        parts.append(
            f"②**要 sudo cp 到 /etc 並 daemon-reload**：{names}。"
            "systemd unit 與 fail2ban 設定的落點是 /etc/systemd/system 與 /etc/fail2ban，"
            "而 **push 與 scp 兩條路都到不了那裡**——post-receive 只 checkout 到 "
            "/srv/it-asset 再 restart it-asset。改了不裝的話 live 設定一個字都沒變，"
            "**而且不會報錯**。裝完記得 `sudo systemctl daemon-reload`；"
            "改的是 .timer 還要 `sudo systemctl restart <名稱>.timer`，"
            "fail2ban 則是 `sudo systemctl reload fail2ban`。"
        )

    return warn("CLAUDE.md §9：這次要推的內容有 push 到不了的部分——" + "　".join(parts))
