#!/bin/bash
# Claude Code の会話を消さない設定に戻し、全タスクの会話をオンラインへ自動同期する。
# Mac のターミナルで1回だけ実行:  bash install.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/towa-sync"
SETTINGS="$HOME/.claude/settings.json"
STAMP="$(date +%Y%m%d-%H%M%S)"

# 1. 同期先（Google Drive があれば優先、なければ iCloud Drive）
SYNC=""
for d in "$HOME"/Library/CloudStorage/GoogleDrive-*/"マイドライブ" "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive"; do
  [ -d "$d" ] && SYNC="$d/claude-sync" && break
done
if [ -z "$SYNC" ] && [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs" ]; then
  SYNC="$HOME/Library/Mobile Documents/com~apple~CloudDocs/claude-sync"
fi
if [ -z "${SYNC}" ]; then
  [ -n "${CLAUDE_SYNC_DIR:-}" ] && SYNC="$CLAUDE_SYNC_DIR"
fi
if [ -z "$SYNC" ]; then
  echo "Google Drive（パソコン版）も iCloud Drive も見つかりません。どちらかを入れてから再実行してください。" >&2
  exit 1
fi
mkdir -p "$SYNC" "$DEST"
cp "$HERE/sync.py" "$DEST/sync.py"
python3 -c 'import json,sys; json.dump({"sync_dir": sys.argv[1]}, open(sys.argv[2], "w"), ensure_ascii=False)' "$SYNC" "$DEST/config.json"

# 2. settings.json：会話を保存しない設定を外し、フックを追加（控えを残す）
mkdir -p "$HOME/.claude"
[ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
cp "$SETTINGS" "$SETTINGS.bak-$STAMP"
python3 - "$SETTINGS" "$DEST/sync.py" <<'EOF'
import json, sys
path, script = sys.argv[1], sys.argv[2]
s = json.load(open(path))
env = s.get("env", {})
env.pop("CLAUDE_CODE_SKIP_PROMPT_HISTORY", None)
if env: s["env"] = env
else: s.pop("env", None)
s["cleanupPeriodDays"] = 365
s["desktopSessionCleanupPeriodDays"] = 365
hooks = s.setdefault("hooks", {})
def add(event, mode):
    cmd = f'python3 "{script}" {mode}'
    groups = hooks.setdefault(event, [])
    if any(h.get("command") == cmd for g in groups for h in g.get("hooks", [])):
        return
    groups.append({"hooks": [{"type": "command", "command": cmd, "timeout": 30}]})
for ev in ("Stop", "PreCompact", "SessionEnd"):
    add(ev, "save")
add("SessionStart", "start")
json.dump(s, open(path, "w"), ensure_ascii=False, indent=2)
EOF

# 3. シェル設定に残っている CLAUDE_CODE_SKIP_PROMPT_HISTORY を無効化（控えを残す）
for rc in "$HOME/.zshrc" "$HOME/.zprofile" "$HOME/.zshenv" "$HOME/.bash_profile" "$HOME/.bashrc"; do
  if [ -f "$rc" ] && grep -q '^[^#]*CLAUDE_CODE_SKIP_PROMPT_HISTORY' "$rc"; then
    cp "$rc" "$rc.bak-$STAMP"
    sed -i '' -e '/^[^#]*CLAUDE_CODE_SKIP_PROMPT_HISTORY/s/^/# towa-sync で無効化: /' "$rc" 2>/dev/null \
      || sed -i -e '/^[^#]*CLAUDE_CODE_SKIP_PROMPT_HISTORY/s/^/# towa-sync で無効化: /' "$rc"
    echo "無効化: $rc"
  fi
done
launchctl unsetenv CLAUDE_CODE_SKIP_PROMPT_HISTORY 2>/dev/null || true
unset CLAUDE_CODE_SKIP_PROMPT_HISTORY

# 4. 手元に残っている会話を全部同期して確認
python3 "$DEST/sync.py" backfill
python3 "$DEST/sync.py" check
echo
echo "完了。Claude アプリを一度終了して開き直してください。同期先: $SYNC"
