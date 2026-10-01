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

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# Win32 Clipboard implementation via ctypes (100% self-contained, no external pip dll dependencies)
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

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
    # Encode as null-terminated UTF-16LE
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

# ADB and device discovery
DEFAULT_ADB_PATHS = [
    r"C:\Users\Lenovo\Downloads\platform-tools-latest-windows (1)\platform-tools\adb.exe",
    "adb.exe"
]

SCRCPY_SERVER_PATHS = [
    r"C:\Users\Lenovo\AppData\Local\Microsoft\WinGet\Packages\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\scrcpy-win64-v4.1\scrcpy-server",
    os.path.join(os.path.dirname(__file__), "scrcpy-server"),
    os.path.join(os.path.dirname(__file__), "scrcpy-server.jar")
]

def find_adb():
    for p in DEFAULT_ADB_PATHS:
        if os.path.isabs(p) and os.path.exists(p):
            return p
    return "adb"

def find_scrcpy_server():
    for p in SCRCPY_SERVER_PATHS:
        if os.path.exists(p):
            return p
    return None

def run_cmd(args, timeout=10):
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=timeout, shell=False)
        return res.stdout.strip()
    except Exception as ex:
        return ""

def detect_phone_ip():
    """Detect current phone IP from WLAN default route or known candidates."""
    candidates = []
    # Try net route for default gateway
    try:
        cmd = ["powershell", "-NoProfile", "-Command", "Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Select-Object -ExpandProperty NextHop"]
        out = run_cmd(cmd, timeout=3)
        for line in out.splitlines():
            ip = line.strip()
            if ip and not ip.startswith("192.168.") and not ip.startswith("127."):
                candidates.append(ip)
    except Exception:
        pass
    
    candidates.extend(["172.31.39.190", "10.87.12.135"])
    # De-duplicate preserving order
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

class ClipboardSyncBridge:
    def __init__(self, adb_path: str, forward_port: int = 28888, scid: str = "00cb5901"):
        self.adb = adb_path
        self.port = forward_port
        self.scid = scid
        self.last_synced_text = ""
        self.lock = threading.Lock()
        self.running = False
        self.sock = None
        self.current_device = None

    def ensure_connection(self) -> bool:
        ips = detect_phone_ip()
        log(f"[Discovery] Testing phone IP candidates: {ips}")
        
        for ip in ips:
            target = f"{ip}:5555"
            log(f"[ADB] Trying to connect {target}...")
            run_cmd([self.adb, "connect", target], timeout=3)
            # Check devices
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
        # Setup forward
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
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
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
                
                # Retry socket connect up to 5 times
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

                # Read 65-byte handshake: 1 byte dummy + 64 bytes device name
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

                while self.running:
                    time.sleep(0.2)
                    current_win = get_windows_clipboard()
                    if current_win and current_win != self.last_synced_text:
                        with self.lock:
                            self.last_synced_text = current_win
                        preview = current_win.replace('\n', ' ')[:40]
                        log(f"[PC -> Phone] Syncing ({len(current_win)} chars): '{preview}'")
                        success = self.send_to_phone(current_win)
                        if not success:
                            break

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
    adb_bin = find_adb()
    bridge = ClipboardSyncBridge(adb_bin)
    bridge.run()
