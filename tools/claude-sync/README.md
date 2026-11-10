# claude-sync：会話を消さない・全タスクを自動でオンラインに残す

## なぜ必要か
2026-11-05、ディスク容量を減らす目的で Mac の Claude Code に次の設定が入った。

- `CLAUDE_CODE_SKIP_PROMPT_HISTORY`：会話本文を保存しない
- `cleanupPeriodDays: 1` / `desktopSessionCleanupPeriodDays: 1`：会話記録を1日で消す

この設定のせいで、再起動したりタスクを再開したりすると、どのタスクでも履歴が読み込めなくなっていた（「No conversation found」「以前のメッセージを保持しなくなりました」）。

## install.sh がすること（Mac で1回実行）
1. 上の3つの設定を外す（保存期間は365日にする）。`settings.json` とシェル設定は、変更前の控え（`.bak-日時`）を残す。
2. **全プロジェクト・全タスク共通のフック**を `~/.claude/settings.json` に入れる。
   - 返答のたび（Stop）・要約の前（PreCompact）・終了時（SessionEnd）：会話記録をGoogle Drive（無ければiCloud Drive）の `claude-sync/` にコピーする。同時に、読める形の `.md` と、最新状況の一覧 `STATUS.md` を更新する。
   - 開始時（SessionStart）：同じフォルダの直近3タスクについて、最近の指示と最後の報告を新しいセッションに自動で読み込ませる。履歴が消えても、同じ説明をやり直さずに済む。
3. 手元に残っている会話記録を全部同期し、設定に問題が残っていないかを確認する。

## 実行
```bash
bash tools/claude-sync/install.sh
```
終わったら Claude アプリを一度終了して開き直す。

## 確認
```bash
python3 ~/.claude/towa-sync/sync.py check
```
「問題: なし」と出て、同期先の `STATUS.md` が更新されていれば動いている。
