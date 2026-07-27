"""閘門規則集。

每條規則一個模組，對外只暴露 `check(ctx) -> Verdict`。
啟用與否由 `_enabled.json` 控制（誤判太吵時改一個 bool，不必動 settings.json）。
"""
