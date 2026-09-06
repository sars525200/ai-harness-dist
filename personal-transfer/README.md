# 換機搬檔用的臨時容器

這個資料夾只是把 `<USER>-settings.json`（舊機 live `~\.claude\settings.json` 的複本）搬到異地機器的臨時管道，用完即刪。

- 內容含這台機器的絕對路徑與個人 hook 設定，**不是** repo 正式範本（`global/settings.json`），異地機器不要拿它當範本用，只當 `tools/wire_machine.py --source` 的輸入。
- 異地機器完成 `wire_machine.py --apply` 之後，回頭把這個資料夾整個刪掉並 commit，不要長期留著。
- 見 `UNIVERSAL_HARNESS_PLAN.md` B3：live settings.json 混進版控會造成「clone 後被誤當範本」的坑，此資料夾是刻意例外，且是暫時的。
