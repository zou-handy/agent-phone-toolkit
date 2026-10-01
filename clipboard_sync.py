#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Phone Toolkit - Real-Time Bidirectional Clipboard Synchronizer
-------------------------------------------------------------------
Synchronizes clipboard seamlessly between Windows PC and Android Phone
over Wireless ADB / Hotspot using lightweight scrcpy-server binary protocol.

Key features:
- TRUE Bidirectional sync: PC <-> Phone
- Zero-overhead: No video/audio streaming, no battery heat
- Independent daemon: Runs as a standalone background process
- Auto-reconnect: Seamless recovery from Wi-Fi / Hotspot disconnects & PC sleep
- Auto-start on boot: Native Windows Registry Run key + Startup folder integration
"""

import sys
import os
import time
import socket
import struct
import threading
import subprocess
import ctypes
from ctypes import wintypes
import winreg
import shutil
import hashlib
import io
import tempfile

try:
    from PIL import Image, ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# Win32 Clipboard implementation via ctypes (100% self-contained, no external pip dll dependencies)
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
CF_DIB = 8
GMEM_MOVEABLE = 0x0002

SW_HIDE = 0
SW_SHOW = 5

CREATE_NO_WINDOW = 0x08000000

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "AgentPhoneClipboardSync"
INSTALL_DIR = os.path.expandvars(r"%LOCALAPPDATA%\Programs\AgentPhoneToolkit")
STARTUP_DIR = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")

def hide_console():
    """Hide the console window when running in silent/background mode."""
    try:
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass

def enable_autostart(target_exe=None):
    """Register application in Windows HKCU Run registry key and Startup folder."""
    if not target_exe:
        target_exe = os.path.abspath(sys.argv[0])
    
    # 1. Registry HKCU Run
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            cmd = f'"{target_exe}" --silent'
            winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, cmd)
    except Exception as ex:
        log(f"[Autostart] Registry registration error: {ex}")

    # 2. Startup folder shortcut (.lnk)
    try:
        lnk_path = os.path.join(STARTUP_DIR, "AgentPhoneClipboardSync.lnk")
        ico_path = os.path.join(os.path.dirname(target_exe), "app.ico")
        icon_cmd = f'$sc.IconLocation = "{ico_path},0"; ' if os.path.exists(ico_path) else ''
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$sc = $ws.CreateShortcut("{lnk_path}"); '
            f'$sc.TargetPath = "{target_exe}"; '
            f'$sc.Arguments = "--silent"; '
            f'$sc.WorkingDirectory = "{os.path.dirname(target_exe)}"; '
            f'{icon_cmd}'
            f'$sc.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    except Exception as ex:
        log(f"[Autostart] Startup shortcut error: {ex}")
    
    # 3. Desktop shortcut (.lnk)
    try:
        desktop_dir = os.path.expandvars(r"%USERPROFILE%\Desktop")
        desk_lnk = os.path.join(desktop_dir, "Agent Phone 剪切板同步.lnk")
        ico_path = os.path.join(os.path.dirname(target_exe), "app.ico")
        icon_cmd = f'$sc.IconLocation = "{ico_path},0"; ' if os.path.exists(ico_path) else ''
        ps_cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$sc = $ws.CreateShortcut("{desk_lnk}"); '
            f'$sc.TargetPath = "{target_exe}"; '
            f'$sc.Arguments = "--silent"; '
            f'$sc.WorkingDirectory = "{os.path.dirname(target_exe)}"; '
            f'$sc.Description = "Agent Phone 双向剪切板同步守护进程"; '
            f'{icon_cmd}'
            f'$sc.Save()'
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
    except Exception as ex:
        log(f"[Autostart] Desktop shortcut error: {ex}")
    
    log(f"[Autostart] Successfully enabled autostart on boot for: {target_exe}")

def disable_autostart():
    """Unregister application from Windows autostart."""
    # 1. Remove registry key
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, REG_VALUE_NAME)
    except Exception:
        pass
    
    # 2. Remove startup shortcut
    try:
        lnk_path = os.path.join(STARTUP_DIR, "AgentPhoneClipboardSync.lnk")
        if os.path.exists(lnk_path):
            os.remove(lnk_path)
    except Exception:
        pass
    
    log("[Autostart] Successfully removed autostart configuration.")

def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, REG_VALUE_NAME)
            return True
    except Exception:
        pass
    lnk_path = os.path.join(STARTUP_DIR, "AgentPhoneClipboardSync.lnk")
    return os.path.exists(lnk_path)

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL

def get_windows_clipboard() -> str:
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    h_global = user32.GetClipboardData(CF_UNICODETEXT)
                    if h_global:
                        p_str = kernel32.GlobalLock(h_global)
                        if p_str:
                            text = ctypes.wstring_at(p_str)
                            kernel32.GlobalUnlock(h_global)
                            return text
                return ""
            finally:
                user32.CloseClipboard()
        time.sleep(0.05)
    return ""

def set_windows_clipboard(text: str) -> bool:
    if not isinstance(text, str):
        return False
    text_data = (text + '\0').encode('utf-16le')
    size = len(text_data)
    
    for _ in range(5):
        if user32.OpenClipboard(None):
            try:
                user32.EmptyClipboard()
                h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                if not h_global:
                    return False
                p_str = kernel32.GlobalLock(h_global)
                if not p_str:
                    return False
                ctypes.memmove(p_str, text_data, size)
                kernel32.GlobalUnlock(h_global)
                user32.SetClipboardData(CF_UNICODETEXT, h_global)
                return True
            finally:
                user32.CloseClipboard()
        time.sleep(0.05)
    return False

kernel32.GlobalSize.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalSize.restype = ctypes.c_size_t

def get_windows_clipboard_image():
    """Returns (md5_hash, pil_image) if an image is on clipboard, else (None, None)."""
    if not HAS_PIL:
        return None, None
    try:
        if user32.OpenClipboard(None):
            try:
                if user32.IsClipboardFormatAvailable(CF_DIB):
                    h_global = user32.GetClipboardData(CF_DIB)
                    if h_global:
                        p_data = kernel32.GlobalLock(h_global)
                        if p_data:
                            size = kernel32.GlobalSize(h_global)
                            raw_bytes = ctypes.string_at(p_data, size)
                            kernel32.GlobalUnlock(h_global)
                            img_hash = hashlib.md5(raw_bytes).hexdigest()
                            img = ImageGrab.grabclipboard()
                            if isinstance(img, Image.Image):
                                return img_hash, img
            finally:
                user32.CloseClipboard()
    except Exception:
        pass
    return None, None

def set_windows_clipboard_image(image) -> str:
    """Sets a PIL Image to Windows Clipboard as CF_DIB. Returns its MD5 hash."""
    if not HAS_PIL or image is None:
        return ""
    try:
        output = io.BytesIO()
        image.convert('RGB').save(output, 'BMP')
        dib_data = output.getvalue()[14:]  # Strip 14-byte BITMAPFILEHEADER
        img_hash = hashlib.md5(dib_data).hexdigest()
        size = len(dib_data)
        
        for _ in range(5):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
                    if not h_global:
                        return ""
                    p_str = kernel32.GlobalLock(h_global)
                    if not p_str:
                        return ""
                    ctypes.memmove(p_str, dib_data, size)
                    kernel32.GlobalUnlock(h_global)
                    user32.SetClipboardData(CF_DIB, h_global)
                    return img_hash
                finally:
                    user32.CloseClipboard()
            time.sleep(0.05)
    except Exception as ex:
        log(f"[Clipboard Image] Error setting clipboard image: {ex}")
    return ""


# Paths for ADB and scrcpy-server
DEFAULT_ADB_PATHS = [
    os.path.join(os.path.dirname(__file__), "adb.exe"),
    os.path.join(INSTALL_DIR, "adb.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
    r"C:\platform-tools\adb.exe",
    r"C:\Users\Lenovo\Downloads\platform-tools-latest-windows (1)\platform-tools\adb.exe",
    "adb.exe"
]

def find_adb():
    # 1. Check system PATH first
    which_adb = shutil.which("adb") or shutil.which("adb.exe")
    if which_adb and os.path.exists(which_adb):
        return which_adb
    # 2. Check predefined and local directory paths
    for p in DEFAULT_ADB_PATHS:
        if os.path.isabs(p) and os.path.exists(p):
            return p
    return "adb"

SCRCPY_SERVER_PATHS = [
    os.path.join(INSTALL_DIR, "scrcpy-server.jar"),
    r"C:\Users\Lenovo\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v4.1\scrcpy-server",
    os.path.join(os.path.dirname(__file__), "scrcpy-server.jar"),
    os.path.join(os.path.dirname(__file__), "scrcpy-server")
]

def find_scrcpy_server():
    for p in SCRCPY_SERVER_PATHS:
        if os.path.exists(p):
            return p
    return None

def run_cmd(args, timeout=10):
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout, shell=False, creationflags=CREATE_NO_WINDOW)
        return res.stdout.strip()
    except Exception:
        return ""

def detect_phone_ip():
    """Detect current phone IP from WLAN default route or known candidates."""
    candidates = []
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -ExpandProperty NextHop"]
        out = run_cmd(cmd, timeout=3)
        for line in out.splitlines():
            ip = line.strip()
            if ip and not ip.startswith("192.168.") and not ip.startswith("127."):
                candidates.append(ip)
    except Exception:
        pass
    
    candidates.extend(["172.31.39.190", "172.31.39.190:5556", "10.87.12.135"])
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result

def recv_exact(sock, n):
    data = b''
    while len(data) < n:
        try:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None
            data += chunk
        except Exception:
            return None
    return data

def install_to_system():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    target_exe = os.path.join(INSTALL_DIR, "clipboard_sync.exe")
    target_jar = os.path.join(INSTALL_DIR, "scrcpy-server.jar")
    
    # Locate the actual compiled .exe file
    if getattr(sys, 'frozen', False):
        src_exe = sys.executable
    else:
        src_exe = os.path.join(os.path.dirname(__file__), "clipboard_sync.exe")
        if not os.path.exists(src_exe):
            src_exe = os.path.join(os.path.dirname(__file__), "dist", "clipboard_sync.exe")
    
    log(f"[Install] Target installation directory: {INSTALL_DIR}")
    
    # Terminate other running instances before overwrite (excluding self!)
    my_pid = os.getpid()
    try:
        res = subprocess.run(["tasklist", "/FI", "IMAGENAME eq clipboard_sync.exe", "/FO", "CSV"],
                             capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        for line in res.stdout.splitlines():
            parts = line.split(",")
            if len(parts) >= 2:
                pid_str = parts[1].strip('"')
                if pid_str.isdigit():
                    p = int(pid_str)
                    if p != my_pid:
                        subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass
    time.sleep(0.5)

    if os.path.exists(src_exe) and os.path.abspath(src_exe).lower() != os.path.abspath(target_exe).lower():
        shutil.copy2(src_exe, target_exe)
        log(f"[Install] Copied binary -> {target_exe}")

    local_jar = find_scrcpy_server()
    if local_jar and os.path.exists(local_jar) and os.path.abspath(local_jar).lower() != os.path.abspath(target_jar).lower():
        shutil.copy2(local_jar, target_jar)
        log(f"[Install] Copied companion server jar -> {target_jar}")

    # Copy app.ico
    target_ico = os.path.join(INSTALL_DIR, "app.ico")
    for possible_ico in [
        os.path.join(os.path.dirname(__file__), "assets", "app.ico"),
        os.path.join(os.path.dirname(__file__), "app.ico")
    ]:
        if os.path.exists(possible_ico):
            if os.path.abspath(possible_ico).lower() != os.path.abspath(target_ico).lower():
                shutil.copy2(possible_ico, target_ico)
                log(f"[Install] Copied icon -> {target_ico}")
            break

    enable_autostart(target_exe)
    
    # Create uninstaller script
    uninst_bat = os.path.join(INSTALL_DIR, "uninstall.bat")
    with open(uninst_bat, "w", encoding="utf-8") as f:
        f.write('@echo off\n"%~dp0clipboard_sync.exe" --uninstall\necho Uninstalled successfully.\npause\n')
    
    log("[Install] Installation completed successfully!")
    log(f"[Install] Launching background daemon: {target_exe} --silent")
    subprocess.Popen([target_exe, "--silent"], shell=False, creationflags=CREATE_NO_WINDOW)

    # Show friendly setup tutorial dialog for users
    guide_text = (
        "Agent Phone Toolkit 安装成功！\n\n"
        "【手机端简易准备指南】\n"
        "1. 开启手机【USB 调试】\n"
        "   进入【设置 -> 关于本机 -> 版本信息】，连续点击【版本号】5 次开启开发者选项；\n"
        "   进入【设置 -> 开发者选项】，开启【USB 调试】。\n"
        "   （ColorOS/OPPO 用户务必同时开启【禁止权限监控】）\n\n"
        "2. 建立连接（二选一）\n"
        "   - 方案 A（免流量热点，强烈推荐）：手机开启个人热点，电脑连接该热点；\n"
        "   - 方案 B（局域网）：手机与电脑连接同一个 Wi-Fi。\n\n"
        "3. 首次连接授权\n"
        "   手机若弹出「允许 USB 调试吗？」，请勾选「始终允许来自此计算机」并点确定。\n\n"
        "程序现已在 Windows 后台隐形静默运行，无需开着任何窗口！"
    )
    try:
        user32.MessageBoxW(None, guide_text, "Agent Phone Toolkit - 安装成功与手机设置指南", 0x40)
    except Exception:
        pass

class ClipboardSyncBridge:
    def __init__(self, adb_path: str, forward_port: int = 28888, scid: str = "00cb5901",
                 enable_images: bool = True):
        self.adb = adb_path
        self.port = forward_port
        self.scid = scid
        self.last_synced_text = ""
        self.enable_images = enable_images
        self.last_synced_image_hash = ""
        self.last_phone_screenshot_ts = 0
        self.lock = threading.Lock()
        self.running = False
        self.sock = None
        self.current_device = None



    def ensure_connection(self) -> bool:
        ips = detect_phone_ip()
        log(f"[Discovery] Testing phone IP candidates: {ips}")
        
        for ip in ips:
            target = ip if ":" in ip else f"{ip}:5555"
            log(f"[ADB] Trying to connect {target}...")
            run_cmd([self.adb, "connect", target], timeout=3)
            out = run_cmd([self.adb, "devices"], timeout=3)
            if target in out and "\tdevice" in out:
                self.current_device = target
                log(f"[ADB] Successfully connected to {self.current_device}")
                return True
        return False

    def push_server_if_needed(self):
        check = run_cmd([self.adb, "-s", self.current_device, "shell", "ls -l /data/local/tmp/scrcpy-server.jar"], timeout=3)
        if "/data/local/tmp/scrcpy-server.jar" not in check:
            local_server = find_scrcpy_server()
            if local_server:
                log(f"[Deploy] Pushing {local_server} to phone...")
                run_cmd([self.adb, "-s", self.current_device, "push", local_server, "/data/local/tmp/scrcpy-server.jar"], timeout=10)

    def start_phone_server(self):
        run_cmd([self.adb, "-s", self.current_device, "forward", f"tcp:{self.port}", f"localabstract:scrcpy_{self.scid}"], timeout=3)
        
        # Kill previous scrcpy instance if any
        run_cmd([self.adb, "-s", self.current_device, "shell", "pkill -f com.genymobile.scrcpy.Server"], timeout=3)
        time.sleep(0.3)

        # Launch server process in background on Android
        server_cmd = (
            f"CLASSPATH=/data/local/tmp/scrcpy-server.jar app_process / "
            f"com.genymobile.scrcpy.Server 4.1 scid={self.scid} log_level=info video=false audio=false tunnel_forward=true"
        )
        log("[Server] Starting background scrcpy-server daemon on phone...")
        subprocess.Popen([self.adb, "-s", self.current_device, "shell", server_cmd],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False, creationflags=CREATE_NO_WINDOW)
        time.sleep(1.2)

    def send_to_phone(self, text: str) -> bool:
        if not self.sock:
            return False
        try:
            text_bytes = text.encode('utf-8')
            msg = struct.pack('>B Q B I', 9, 0, 0, len(text_bytes)) + text_bytes
            self.sock.sendall(msg)
            return True
        except Exception as ex:
            log(f"[Error] Failed to send clipboard to phone: {ex}")
            return False

    def phone_screenshot_watcher_thread(self):
        """Watches phone's screenshot folder for new screenshots and pulls to PC clipboard."""
        log("[ScreenshotWatcher] Monitoring phone screenshots (3-finger / status bar / gesture)...")
        init_cmd = [self.adb, "-s", self.current_device, "shell",
                    "stat -c '%Y %n' /sdcard/DCIM/Screenshots/* /sdcard/Pictures/Screenshots/* 2>/dev/null | sort -n | tail -n 1"]
        out = run_cmd(init_cmd, timeout=3)
        if out:
            parts = out.strip().split()
            if len(parts) >= 2 and parts[0].isdigit():
                self.last_phone_screenshot_ts = int(parts[0])

        temp_dir = tempfile.gettempdir()
        local_target = os.path.join(temp_dir, "phone_screenshot_latest.jpg")

        while self.running and self.current_device:
            time.sleep(1.0)
            try:
                stat_cmd = [self.adb, "-s", self.current_device, "shell",
                            "stat -c '%Y %n' /sdcard/DCIM/Screenshots/* /sdcard/Pictures/Screenshots/* 2>/dev/null | sort -n | tail -n 1"]
                stat_out = run_cmd(stat_cmd, timeout=3)
                if not stat_out:
                    continue
                parts = stat_out.strip().split()
                if len(parts) < 2 or not parts[0].isdigit():
                    continue
                ts = int(parts[0])
                remote_path = parts[1]

                if "PC_Clip_" in remote_path:
                    continue

                if ts > self.last_phone_screenshot_ts:
                    self.last_phone_screenshot_ts = ts
                    filename = os.path.basename(remote_path)
                    log(f"[Phone -> PC Screenshot] Detected new screenshot on phone: {filename}")
                    run_cmd([self.adb, "-s", self.current_device, "pull", remote_path, local_target], timeout=10)
                    if os.path.exists(local_target) and HAS_PIL:
                        try:
                            with Image.open(local_target) as img:
                                new_hash = set_windows_clipboard_image(img)
                                if new_hash:
                                    with self.lock:
                                        self.last_synced_image_hash = new_hash
                                    log(f"[Phone -> PC Screenshot] Injected into Windows Clipboard! (Ready to Ctrl+V, size: {img.size})")
                        except Exception as e:
                            log(f"[Phone -> PC Screenshot] Failed to process image: {e}")
            except Exception as ex:
                if self.running:
                    log(f"[ScreenshotWatcher] Error: {ex}")

    def phone_reader_thread(self):
        while self.running and self.sock:
            try:
                msg_type_b = recv_exact(self.sock, 1)
                if not msg_type_b:
                    log("[PhoneReader] Connection lost.")
                    break
                msg_type = msg_type_b[0]
                if msg_type == 0:  # DEVICE_MSG_TYPE_CLIPBOARD
                    len_b = recv_exact(self.sock, 4)
                    if not len_b:
                        break
                    text_len = struct.unpack('>I', len_b)[0]
                    text_b = recv_exact(self.sock, text_len)
                    if text_b is None:
                        break
                    phone_text = text_b.decode('utf-8', errors='ignore')
                    
                    with self.lock:
                        if phone_text != self.last_synced_text:
                            self.last_synced_text = phone_text
                            set_windows_clipboard(phone_text)
                            preview = phone_text.replace('\n', ' ')[:40]
                            log(f"[Phone -> PC] Received ({len(phone_text)} chars): '{preview}'")
                elif msg_type == 1:  # ACK_CLIPBOARD
                    seq_b = recv_exact(self.sock, 8)
                else:
                    log(f"[PhoneReader] Ignored msg type: {msg_type}")
            except Exception as ex:
                if self.running:
                    log(f"[PhoneReader] Exception: {ex}")
                break
        self.running = False

    def run(self):
        log("=" * 60)
        log("Agent Phone Toolkit - Wireless Clipboard Synchronizer")
        log("=" * 60)
        
        while True:
            try:
                if not self.ensure_connection():
                    log("[Sync] Waiting for phone to connect... retry in 4s")
                    time.sleep(4)
                    continue

                self.push_server_if_needed()
                self.start_phone_server()

                log(f"[Bridge] Connecting to scrcpy tunnel 127.0.0.1:{self.port}...")
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(10.0)
                
                connected = False
                for attempt in range(5):
                    try:
                        self.sock.connect(('127.0.0.1', self.port))
                        connected = True
                        break
                    except Exception:
                        time.sleep(0.5)

                if not connected:
                    log("[Bridge] Connection to socket timed out. Restarting loop...")
                    time.sleep(2)
                    continue

                header = recv_exact(self.sock, 65)
                if not header:
                    log("[Bridge] Handshake failed (did not receive 65 bytes).")
                    time.sleep(2)
                    continue

                dev_name = header[1:].split(b'\x00')[0].decode('utf-8', errors='ignore')
                log(f"[Bridge] Handshake successful! Connected to device: [{dev_name}]")
                log("[Bridge] Real-time bidirectional clipboard sync is now RUNNING!")
                log("  - Copy anything on PC -> Immediately available on Phone")
                log("  - Copy anything on Phone -> Immediately available on PC")

                self.sock.settimeout(None)
                self.running = True
                
                with self.lock:
                    self.last_synced_text = get_windows_clipboard()

                t_reader = threading.Thread(target=self.phone_reader_thread, daemon=True)
                t_reader.start()

                if self.enable_images and HAS_PIL:
                    t_screenshot = threading.Thread(target=self.phone_screenshot_watcher_thread, daemon=True)
                    t_screenshot.start()

                temp_dir = tempfile.gettempdir()
                local_pc_clip = os.path.join(temp_dir, "pc_clipboard_image.png")

                while self.running:
                    time.sleep(0.25)
                    # 1. Text sync
                    current_win = get_windows_clipboard()
                    if current_win and current_win != self.last_synced_text:
                        with self.lock:
                            self.last_synced_text = current_win
                        preview = current_win.replace('\n', ' ')[:40]
                        log(f"[PC -> Phone Text] Syncing ({len(current_win)} chars): '{preview}'")
                        success = self.send_to_phone(current_win)
                        if not success:
                            break

                    # 2. Image sync
                    if self.enable_images and HAS_PIL:
                        img_hash, img_obj = get_windows_clipboard_image()
                        if img_hash and img_hash != self.last_synced_image_hash:
                            with self.lock:
                                self.last_synced_image_hash = img_hash
                            log(f"[PC -> Phone Image] Detected image on Windows clipboard ({img_obj.size})")
                            try:
                                img_obj.save(local_pc_clip, format='PNG')
                                ts_str = time.strftime('%Y%m%d_%H%M%S')
                                remote_target = f"/sdcard/Pictures/Screenshots/PC_Clip_{ts_str}.png"
                                run_cmd([self.adb, "-s", self.current_device, "push", local_pc_clip, remote_target], timeout=10)
                                run_cmd([self.adb, "-s", self.current_device, "shell",
                                         f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{remote_target}"], timeout=5)
                                log(f"[PC -> Phone Image] Pushed to phone album: {remote_target}")
                            except Exception as ex:
                                log(f"[PC -> Phone Image] Sync error: {ex}")



            except KeyboardInterrupt:
                log("[Exit] User stopped service.")
                break
            except Exception as e:
                log(f"[Bridge Loop Error] {e}")
            finally:
                self.running = False
                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
                log("[Bridge] Connection closed. Auto-reconnecting in 3s...")
                time.sleep(3)

if __name__ == '__main__':
    args = [a.lower() for a in sys.argv[1:]]

    if '--install' in args or '-i' in args:
        install_to_system()
        sys.exit(0)

    if '--uninstall' in args or '-u' in args:
        disable_autostart()
        sys.exit(0)

    if '--autostart' in args or '--enable-autostart' in args:
        enable_autostart()
        sys.exit(0)

    if '--disable-autostart' in args:
        disable_autostart()
        sys.exit(0)

    if '--silent' in args or '-s' in args:
        hide_console()

    # Automatically ensure autostart on boot is enabled
    if not is_autostart_enabled():
        enable_autostart()

    enable_images = '--no-images' not in args

    if enable_images:
        log("[Feature] Dual-direction Image & Screenshot Sync: ENABLED")

    adb_bin = find_adb()
    bridge = ClipboardSyncBridge(adb_bin, enable_images=enable_images)
    bridge.run()


