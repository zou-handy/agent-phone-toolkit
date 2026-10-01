# Agent Phone Toolkit (跨设备剪贴板双向同步与管理套件)

适用于 Windows 与 Android（ColorOS 16 / Android 16 实测验证）的高性能、免投屏、零发热**真正双向剪贴板同步与设备工具套件**。

---

## 🌟 核心特性

1. **真正的双向无感同步**：
   - **电脑 -> 手机**：在电脑任意软件（微信、浏览器、Word、记事本等）按 `Ctrl+C` 复制，手机剪贴板（搜狗输入法/系统剪贴板）毫秒级自动接收！
   - **手机 -> 电脑**：在手机上长按复制任意文字，电脑剪贴板立刻自动同步，直接 `Ctrl+V` 粘贴！
2. **轻量与零发热**：
   - 基于 `scrcpy-server` 底层 Binder 协议通信，完全禁用视频流与音频流（`video=false, audio=false`）。
   - 不调用硬件视频编码器，彻底解决“OPPO 互联 + 热点”导致的手机发烫发热、耗电快痛点。
3. **独立运行与自愈机制**：
   - 独立于任何 AI 客户端或终端窗口，打包为独立单文件 `clipboard_sync.exe`。
   - 自动检测热点网段（如 `172.31.39.190`）与局域网 IP（`10.87.12.135`）。
   - 手机热点断开、电脑睡眠唤醒后，自动无限重连恢复同步。
4. **开箱即用，无需手机端安装额外应用**：
   - 依赖无线调试与 `scrcpy-server.jar` 注入，无需在手机上额外安装第三方剪贴板 APK。

---

## 🚀 快速使用

### 方式 1：双击静默后台启动（推荐，完全独立运行）
双击运行目录下的 **`start_clipboard_sync.vbs`**：
- 没有黑框，完全在后台静默运行。
- 即使关闭 Antigravity、VS Code 或所有终端，剪贴板同步依然在后台默默工作。

### 方式 2：控制台可视化查看日志
双击运行 **`clipboard_sync.exe`**：
- 可以实时看到手机与电脑每次复制的字符数和时间戳。

### 方式 3：停止后台同步
双击运行 **`stop_clipboard_sync.bat`** 即可一键结束进程。

---

## ⏰ 开机自启（实现媲美系统级互联体验）

1. 按下快捷键 `Win + R`，输入：
   ```text
   shell:startup
   ```
   回车打开 Windows 开机启动文件夹。
2. 将 `start_clipboard_sync.vbs` 的**快捷方式**复制到该文件夹中。
3. 以后电脑开机或重连手机热点时，剪贴板双向同步将全天候自动工作！

---

## 🛠️ 技术实现原理

```
[Windows PC]                                      [Android Device]
  │                                                      │
  ├─ Windows 剪贴板监听 (Win32 API)                        │
  │     └─ 检测到复制 -> 发送 SET_CLIPBOARD (0x09) ──────>│ scrcpy-server (Shell UID 2000)
  │                                                      │    └─ 调用系统 IClipboard
  │                                                      │
  │<─ 接收 DEVICE_MSG_TYPE_CLIPBOARD (0x00) ─────────────┼─ 手机复制触发 OnPrimaryClipChanged
  └─ 写入 Windows 剪贴板 (OpenClipboard / Unicode)
```

- **协议报文**：
  - **PC -> 手机**：`0x09` (Type) + `0x00...00` (8B Sequence) + `0x00` (Paste Flag) + `Length` (4B Big-Endian) + `UTF-8 Data`
  - **手机 -> PC**：`0x00` (Type) + `Length` (4B Big-Endian) + `UTF-8 Data`
- **防环路回音抑制**：内置最后同步文本状态比对锁，避免 A->B 后 B 误以为是用户复制又发回给 A。

---

## 📂 文件清单

- `clipboard_sync.exe`: 编译好的 Windows 独立可执行程序（8.4MB 单文件）
- `clipboard_sync.py`: Python 完整源码（免第三方 C 库，纯 ctypes Win32 实现）
- `scrcpy-server.jar`: 配套的 Android 服务端字节码
- `start_clipboard_sync.vbs`: 静默无黑框后台启动脚本
- `stop_clipboard_sync.bat`: 一键终止脚本
- `session_fts5.py`: 跨会话 SQLite FTS5 倒排索引全文检索引擎
- `wireless_phone_bridge.ps1`: 无线 ADB 与多工具桥接脚本
