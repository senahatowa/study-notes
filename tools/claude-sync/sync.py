#!/usr/bin/env python3
"""Claude Code の会話を、全タスク共通でオンライン（Google Drive / iCloud）へ自動同期する。

フックから呼ばれる:
  sync.py save   … Stop / PreCompact / SessionEnd。会話記録をコピーし、読める形の .md と最新状況の一覧を更新
  sync.py start  … SessionStart。最新状況を新しいセッションの文脈に読み込ませる
  sync.py backfill … 手元に残っている会話記録を全部同期（初回用）
  sync.py check  … 設定と同期先の状態を表示
"""
import datetime as dt
import glob
import json
import os
import shutil
import sys

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".claude", "towa-sync", "config.json")
MAX_TEXT = 1500


def sync_root():
    try:
        with open(CONF) as f:
            return json.load(f)["sync_dir"]
    except Exception:
        return None


def read_jsonl(path):
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def text_of(content):
    if isinstance(content, str):
        return content
    parts = []
    for c in content or []:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
        elif c.get("type") == "image":
            parts.append("[画像]")
    return "\n".join(p for p in parts if p)


def messages(records):
    """(時刻, 'USER'|'AI', 本文) の列。ツール結果は除く。"""
    out = []
    for r in records:
        t = r.get("type")
        msg = r.get("message") or {}
        ts = (r.get("timestamp") or "")[:19]
        if t == "user":
            c = msg.get("content")
            if isinstance(c, list) and any(isinstance(x, dict) and x.get("type") == "tool_result" for x in c):
                continue
            s = text_of(c).strip()
            if s and not r.get("isMeta"):
                out.append((ts, "USER", s))
        elif t == "assistant":
            s = text_of(msg.get("content")).strip()
            if s:
                out.append((ts, "AI", s))
    return out


def title_of(records, msgs):
    for r in records:
        if r.get("type") == "summary" and r.get("summary"):
            return r["summary"]
    for _, who, s in msgs:
        if who == "USER":
            return s.splitlines()[0][:60]
    return "(無題)"


def slug(path):
    return path.strip("/").replace("/", "-") or "root"


def save(session_id, transcript, cwd):
    root = sync_root()
    if not root or not transcript or not os.path.exists(transcript):
        return
    records = read_jsonl(transcript)
    msgs = messages(records)
    if not msgs:
        return
    proj = slug(cwd or "unknown")
    tdir = os.path.join(root, "transcripts", proj)
    os.makedirs(tdir, exist_ok=True)
    shutil.copy2(transcript, os.path.join(tdir, session_id + ".jsonl"))

    title = title_of(records, msgs)
    lines = [f"# {title}", "", f"- セッション: {session_id}", f"- 作業フォルダ: {cwd}",
             f"- 最終更新: {msgs[-1][0]} (UTC)", ""]
    for ts, who, s in msgs:
        lines += [f"## {ts} {'ユーザー' if who == 'USER' else 'Claude'}", "", s, ""]
    with open(os.path.join(tdir, session_id + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    last_ai = next((s for _, w, s in reversed(msgs) if w == "AI"), "")
    users = [s for _, w, s in msgs if w == "USER"]
    idx_path = os.path.join(root, "index.json")
    try:
        with open(idx_path) as f:
            idx = json.load(f)
    except Exception:
        idx = {}
    idx[session_id] = {
        "title": title, "cwd": cwd, "updated": msgs[-1][0],
        "last_report": last_ai[:MAX_TEXT],
        "recent_user": [u[:MAX_TEXT] for u in users[-8:]],
        "md": os.path.join("transcripts", proj, session_id + ".md"),
    }
    tmp = idx_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    os.replace(tmp, idx_path)
    write_status(root, idx)


def write_status(root, idx):
    items = sorted(idx.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True)
    out = ["# 最新状況（自動更新）", "", "新しい順。各セッションの全文は transcripts/ にあります。", ""]
    for sid, v in items[:40]:
        out += [f"## {v['title']}", f"- 更新: {v['updated']} (UTC) / フォルダ: {v['cwd']}",
                f"- 全文: {v['md']}", "", "最後の報告:", "", v["last_report"][:600], ""]
    with open(os.path.join(root, "STATUS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def start(session_id, cwd):
    root = sync_root()
    if not root:
        return
    try:
        with open(os.path.join(root, "index.json")) as f:
            idx = json.load(f)
    except Exception:
        return
    items = sorted(idx.items(), key=lambda kv: kv[1].get("updated", ""), reverse=True)
    items = [kv for kv in items if kv[0] != session_id]
    same = [kv for kv in items if kv[1].get("cwd") == cwd][:3]
    others = [kv for kv in items if kv[1].get("cwd") != cwd][:5]
    if not same and not others:
        return
    out = ["【自動同期された直近の作業状況】会話履歴が読み込めない場合も、ここと同期フォルダ"
           f"（{root}）の全文から続きを把握すること。ユーザーに同じ説明を求めない。", ""]
    for sid, v in same:
        out += [f"■ {v['title']}（{v['updated']} UTC, 全文: {os.path.join(root, v['md'])}）",
                "最近のユーザー指示:"] + [f"- {u[:500]}" for u in v["recent_user"][-5:]] + \
               ["最後の報告:", v["last_report"][:1200], ""]
    if others:
        out.append("ほかのフォルダの直近タスク:")
        out += [f"- {v['title']}（{v['updated']} UTC, {v['cwd']}）" for _, v in others]
    print("\n".join(out))


def backfill():
    n = 0
    for p in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        recs = read_jsonl(p)
        cwd = next((r.get("cwd") for r in recs if r.get("cwd")), "unknown")
        save(os.path.splitext(os.path.basename(p))[0], p, cwd)
        n += 1
    print(f"同期した会話記録: {n} 件 → {sync_root()}")


def check():
    s = json.load(open(os.path.join(HOME, ".claude", "settings.json")))
    bad = []
    if os.environ.get("CLAUDE_CODE_SKIP_PROMPT_HISTORY") or "CLAUDE_CODE_SKIP_PROMPT_HISTORY" in s.get("env", {}):
        bad.append("CLAUDE_CODE_SKIP_PROMPT_HISTORY が残っている（会話が保存されない）")
    for k in ("cleanupPeriodDays", "desktopSessionCleanupPeriodDays"):
        if k in s and s[k] < 30:
            bad.append(f"{k}={s[k]}（短すぎる）")
    print("同期先:", sync_root())
    n = len(glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")))
    print("手元の会話記録:", n, "件")
    print("問題:", "なし" if not bad else " / ".join(bad))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    if mode in ("save", "start"):
        try:
            data = json.load(sys.stdin)
        except Exception:
            data = {}
        sid = data.get("session_id", "unknown")
        cwd = data.get("cwd") or os.getcwd()
        try:
            if mode == "save":
                save(sid, data.get("transcript_path"), cwd)
            else:
                start(sid, cwd)
        except Exception as e:  # フックの失敗で作業を止めない
            log = os.path.join(HOME, ".claude", "towa-sync", "error.log")
            with open(log, "a") as f:
                f.write(f"{dt.datetime.now().isoformat()} {mode} {e!r}\n")
    elif mode == "backfill":
        backfill()
    else:
        check()


if __name__ == "__main__":
    main()
