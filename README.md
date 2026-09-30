# Agent Phone & Session Toolkit

🚀 A private & lightweight toolkit for AI Agents to interact with Android devices and index conversation memory.

## Features

- ⚡ **Zero-Heat Clipboard Sync**: Bidirectional PC <-> Android clipboard synchronization using `scrcpy` in `--no-video --no-audio` mode. Zero thermal load on mobile SoC.
- 📱 **Wireless ADB Bridge**: Connect over Wi-Fi / Hotspot on port 5555. Auto-reconnection daemon included.
- 🔍 **Session SQLite FTS5 Full-Text Indexing**: Blazing fast full-text inverted index for long LLM conversation transcripts (`transcript.jsonl`). Sub-5ms retrieval.
- 🛡️ **Privacy-First**: No data leaves the local network. No external cloud dependencies.

## Installation & Prerequisites

1. Install `adb` (Android Platform Tools) and `scrcpy` (e.g. `winget install Genymobile.scrcpy`).
2. Pair your phone once via USB (`adb tcpip 5555`), then disconnect the cable.
3. Run the clipboard daemon:
   ```powershell
   powershell -ExecutionPolicy Bypass -File wireless_phone_bridge.ps1 clipboard_daemon
   ```

## License

MIT License
