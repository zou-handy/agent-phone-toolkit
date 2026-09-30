---
name: agent-phone-toolkit
description: Wireless ADB bridge, zero-heat bidirectional clipboard sync, and session SQLite FTS5 search engine for AI Agents.
---

# Agent Phone & Session Toolkit

This toolkit equips AI coding agents (Antigravity, Codex, Workbuddy, Claude Code) with:
1. **Wireless Phone Bridge**: Auto-connect to Android phones via ADB port 5555 without cables.
2. **Zero-Heat Clipboard Sync**: Runs `scrcpy` in `--no-video --no-audio` mode for instantaneous bidirectional copy-paste without GPU encoding or phone overheating.
3. **Session FTS5 Search**: Indexes conversation transcripts (`transcript.jsonl`) into an SQLite FTS5 virtual table for 2ms full-text retrieval with text snippets.
4. **Shizuku Revival**: Verifies and revives `/data/local/tmp/shizuku` over wireless ADB.

## Quick Usage

### 1. Clipboard Sync Daemon
```powershell
powershell -ExecutionPolicy Bypass -File wireless_phone_bridge.ps1 clipboard_daemon
```

### 2. Index & Search Chat Sessions
```bash
python session_fts5.py --index path/to/transcript.jsonl --db chat_fts5.db
python session_fts5.py --search "keyword" --db chat_fts5.db
```
