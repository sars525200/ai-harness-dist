"""R1 —— push 邊界觀察：DEFAULT_* 常數值變動，提醒可能需要一併遷移 saved。

CLAUDE.md §8：「改 code 的 DEFAULT_* 預設值＝沒改：getter
Object.assign({},預設,saved)→saved 蓋過·必一併遷移 saved（已咬三次，
2026-07-28 §2.5 反向對帳裡犯最多次的一條）；反向只補 saved→新環境重建又空白」

為什麼掛 push 邊界，不掛 Post(Edit/Write)：
    跟 DB-1 掛 push 邊界同一個理由（D5）——若掛在每次 Edit/Write，草稿階段
    反覆調整同一個常數會反覆 WARN，跟「Stop 每回合觸發」是同一種疲勞。
    push 邊界只在「這次真的要推的內容」裡看變更，同一個常數改 5 次、
    diff 到 push 時只會顯示最終那一次，天然免疫這個問題。

偵測範圍是有意的簡化，不是疏漏——只比對「整行文字」是否不同，
不解析完整的物件字面值：
    `const DEFAULT_FOO = 5;` 這種單行純量賦值抓得到；
    `const DEFAULT_CONFIG = {\n  foo: 1,\n};` 這種多行物件字面值，
    只有宣告那行本身不變的話，抓不到內部欄位被改。真要做到那個程度
    需要 AST 級解析，超出這條規則的成本效益——這是 WARN 不是 BLOCK，
    漏抓的代價遠低於「完全沒有這道防線」（後者已經咬過 3 次）。

同理，不是每個 DEFAULT_* 常數都走 Object.assign({},預設,saved) 這種
會被蓋過的 getter 模式——這條規則沒辦法分辨「這個常數有沒有對應的
saved 覆寫邏輯」，抓到就一律提醒，可能有無關的 false positive。
WARN 級可以接受這個代價換覆蓋率。
"""
from __future__ import annotations

import posixpath
import re

from contract import allow, is_push_to_remote, warn

RULE_ID = "R1"

_SCAN_EXTS = (".js", ".py")
_DEFAULT_ASSIGN = re.compile(r"^.*\bDEFAULT_(\w+)\s*=.*$", re.MULTILINE)


def applies(ctx) -> bool:
    return is_push_to_remote(ctx.command, "vm")


def _extract_default_lines(text: str) -> dict:
    """{常數名: 那一行文字（去頭尾空白）}。同名常數在檔案裡出現多次時，
    後面覆蓋前面——這是刻意的簡化，接受這個邊角情境不精確。"""
    out = {}
    for m in _DEFAULT_ASSIGN.finditer(text):
        out[m.group(1)] = m.group(0).strip()
    return out


def check(ctx):
    if not applies(ctx):
        return allow()

    ref = ctx.git.resolve_remote_ref("vm", "master")
    if not ref:
        return allow()  # fail-open，同 DB-1 理由（ref 解不出來就不硬猜）

    changed_files = [
        f for f in ctx.git.diff_names(f"{ref}..HEAD")
        if posixpath.splitext(f)[1] in _SCAN_EXTS
    ]

    findings = []
    for path in sorted(changed_files):
        old_defaults = _extract_default_lines(ctx.git.show(f"{ref}:{path}"))
        new_defaults = _extract_default_lines(ctx.git.show(f"HEAD:{path}"))
        for name, new_line in new_defaults.items():
            old_line = old_defaults.get(name)
            if old_line is not None and old_line != new_line:
                findings.append(f"{path}：DEFAULT_{name}")

    if not findings:
        return allow()

    listing = "、".join(findings[:3])
    more = f"（另有 {len(findings) - 3} 項）" if len(findings) > 3 else ""
    return warn(
        f"CLAUDE.md §8：偵測到 DEFAULT_* 常數值變動——{listing}{more}。"
        "已咬過 3 次的模式：getter 若用 Object.assign({},預設,saved) 之類寫法，"
        "saved 會蓋過新預設值，改常數等於沒改，必須一併遷移 saved；反向只補 saved"
        "會讓新環境重建又空白。若這個常數沒有對應的 saved 覆寫邏輯，這則提醒可以忽略。"
    )
