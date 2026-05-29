#!/usr/bin/env python3
"""
Satoshi (SAT) Token Miner - BSC PoW Mining Client
A desktop GUI mining application for the Satoshi ERC20 PoW token on BSC.
Bitcoin wallet-style dark UI with CN/EN language switching.
"""

import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import multiprocessing
import ctypes
import struct
import time
import json
import os
import sys
import random
import base64
import io
from datetime import datetime

# Third-party imports
try:
    from web3 import Web3
    from eth_abi.packed import encode_packed
    from eth_account import Account
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "web3", "eth-account"])
    from web3 import Web3
    from eth_abi.packed import encode_packed
    from eth_account import Account

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─── Constants ───────────────────────────────────────────────────────────────

CONTRACT_ADDRESS = "0x14Dc4b4929c664534f1d4D64107d8F36CbF906a0"
DEFAULT_RPC = "https://bsc-dataseed1.binance.org"
CONFIG_FILE = "miner_config.json"
HISTORY_FILE = "mining_history.json"

CONTRACT_ABI = json.loads('''[
    {"inputs":[],"name":"challengeNumber","outputs":[{"type":"bytes32"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"miningTarget","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getMiningDifficulty","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getMiningReward","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"epochCount","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"tokensMinted","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"rewardEra","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"nonce","type":"uint256"},{"name":"challengeDigest","type":"bytes32"}],"name":"mint","outputs":[{"type":"bool"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"","type":"bytes32"}],"name":"solutionForChallenge","outputs":[{"type":"bytes32"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"lastRewardTo","outputs":[{"type":"address"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"lastRewardAmount","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"lastRewardEthBlockNumber","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"},
    {"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"name":"rewardAmount","type":"uint256"},{"name":"epochCount","type":"uint256"},{"name":"newChallengeNumber","type":"bytes32"}],"name":"Mint","type":"event"},
    {"inputs":[],"name":"totalSupply","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"}
]''')

# ─── Bitcoin Wallet Theme Colors ─────────────────────────────────────────────

COLORS = {
    'bg':           '#0d1117',
    'bg_card':      '#161b22',
    'bg_card2':     '#1c2333',
    'bg_input':     '#0d1117',
    'bg_hover':     '#21262d',
    'accent':       '#f7931a',    # Bitcoin orange
    'accent_dark':  '#e8850f',
    'accent_glow':  '#f7931a33',
    'green':        '#3fb950',
    'green_dim':    '#238636',
    'red':          '#f85149',
    'red_dim':      '#da3633',
    'blue':         '#58a6ff',
    'purple':       '#bc8cff',
    'text':         '#e6edf3',
    'text2':        '#8b949e',
    'text3':        '#484f58',
    'border':       '#30363d',
    'border_light': '#3d444d',
    'white':        '#ffffff',
    'black':        '#000000',
}

# ─── I18N ────────────────────────────────────────────────────────────────────

LANG = {
    'en': {
        'title': 'Satoshi Miner',
        'subtitle': 'BSC PoW Mining Client',
        'tab_wallet': 'Wallet',
        'tab_mine': 'Mine',
        'tab_history': 'History',
        'tab_settings': 'Settings',
        'connection': 'Connection',
        'rpc_url': 'RPC Endpoint',
        'private_key': 'Private Key',
        'show': 'Show',
        'hide': 'Hide',
        'connect': 'Connect Wallet',
        'disconnect': 'Disconnect',
        'wallet_overview': 'Wallet Overview',
        'address': 'Address',
        'bnb_balance': 'BNB Balance',
        'sat_balance': 'SAT Balance',
        'total_mined': 'Total Mined',
        'mining_reward': 'Block Reward',
        'difficulty': 'Difficulty',
        'epoch': 'Epoch',
        'era': 'Reward Era',
        'refresh': 'Refresh',
        'mining_dashboard': 'Mining Dashboard',
        'start_mining': 'Start Mining',
        'stop_mining': 'Stop Mining',
        'hashrate': 'Hashrate',
        'blocks_found': 'Blocks Found',
        'uptime': 'Uptime',
        'mining_log': 'Mining Log',
        'clear_log': 'Clear',
        'time': 'Time',
        'nonce': 'Nonce',
        'reward': 'Reward',
        'tx_hash': 'TX Hash',
        'status': 'Status',
        'gas_settings': 'Gas Settings',
        'gas_price': 'Gas Price (Gwei)',
        'gas_limit': 'Gas Limit',
        'contract': 'Contract Address',
        'save_settings': 'Save Settings',
        'about': 'About',
        'about_text': (
            "Satoshi (SAT) is a Proof-of-Work mineable ERC20 token on BSC.\n"
            "Total Supply: 21,000,000 SAT (8 decimals)\n"
            "Initial Reward: 50 SAT per block, halving every era\n"
            "Difficulty adjusts every 1024 epochs\n"
            "Mining: keccak256(challenge, address, nonce) <= target"
        ),
        'not_connected': 'Disconnected',
        'connected': 'Connected',
        'network': 'Network',
        'max_supply': 'Max Supply',
        'halving': 'Halving',
        'every_era': 'Every Era',
        'contract_info': 'Contract Info',
        'success': 'Success',
        'failed': 'Failed',
        'error': 'Error',
        'no_history': 'No mining history yet',
        'mining_started': 'Mining started...',
        'mining_stopped': 'Mining stopped',
        'connect_first': 'Please connect wallet first',
        'enter_rpc': 'Please enter RPC URL',
        'enter_pk': 'Please enter private key',
        'conn_failed': 'Connection failed',
        'settings_saved': 'Settings saved',
        'copy': 'Copy',
        'copied': 'Copied!',
        'mining_active': 'MINING ACTIVE',
        'mining_idle': 'IDLE',
        'total_hashes': 'Total Hashes',
        'avg_hashrate': 'Avg Hashrate',
        'history_title': 'Mining History',
        'no_records': 'No records yet. Start mining to see results here.',
    },
    'zh': {
        'title': 'Satoshi 矿机',
        'subtitle': 'BSC PoW 挖矿客户端',
        'tab_wallet': '钱包',
        'tab_mine': '挖矿',
        'tab_history': '记录',
        'tab_settings': '设置',
        'connection': '连接设置',
        'rpc_url': 'RPC 节点',
        'private_key': '私钥',
        'show': '显示',
        'hide': '隐藏',
        'connect': '连接钱包',
        'disconnect': '断开连接',
        'wallet_overview': '钱包总览',
        'address': '地址',
        'bnb_balance': 'BNB 余额',
        'sat_balance': 'SAT 余额',
        'total_mined': '已挖总量',
        'mining_reward': '区块奖励',
        'difficulty': '难度',
        'epoch': '纪元',
        'era': '奖励时代',
        'refresh': '刷新',
        'mining_dashboard': '挖矿面板',
        'start_mining': '开始挖矿',
        'stop_mining': '停止挖矿',
        'hashrate': '算力',
        'blocks_found': '已出块',
        'uptime': '运行时间',
        'mining_log': '挖矿日志',
        'clear_log': '清除',
        'time': '时间',
        'nonce': 'Nonce',
        'reward': '奖励',
        'tx_hash': '交易哈希',
        'status': '状态',
        'gas_settings': 'Gas 设置',
        'gas_price': 'Gas 价格 (Gwei)',
        'gas_limit': 'Gas 上限',
        'contract': '合约地址',
        'save_settings': '保存设置',
        'about': '关于',
        'about_text': (
            "Satoshi (SAT) 是一个基于 BSC 的工作量证明 ERC20 代币。\n"
            "总供应量：21,000,000 SAT（8位小数）\n"
            "初始奖励：每区块 50 SAT，每个时代减半\n"
            "难度每 1024 个纪元调整一次\n"
            "挖矿原理：keccak256(challenge, address, nonce) <= target"
        ),
        'not_connected': '未连接',
        'connected': '已连接',
        'network': '网络',
        'max_supply': '最大供应量',
        'halving': '减半',
        'every_era': '每个时代',
        'contract_info': '合约信息',
        'success': '成功',
        'failed': '失败',
        'error': '错误',
        'no_history': '暂无挖矿记录',
        'mining_started': '挖矿已开始...',
        'mining_stopped': '挖矿已停止',
        'connect_first': '请先连接钱包',
        'enter_rpc': '请输入 RPC 地址',
        'enter_pk': '请输入私钥',
        'conn_failed': '连接失败',
        'settings_saved': '设置已保存',
        'copy': '复制',
        'copied': '已复制!',
        'mining_active': '挖矿中',
        'mining_idle': '空闲',
        'total_hashes': '总哈希数',
        'avg_hashrate': '平均算力',
        'history_title': '挖矿记录',
        'no_records': '暂无记录。开始挖矿后将在此显示结果。',
    }
}

# ─── Mining Engine (Optimized: multiprocessing + fast inner loop) ────────────

# Try to use fast native keccak implementation
try:
    from Crypto.Hash import keccak as _pycryptodome_keccak
    def _fast_keccak256(data):
        return _pycryptodome_keccak.new(digest_bits=256, data=data).digest()
    KECCAK_ENGINE = "pycryptodome"
except ImportError:
    try:
        import sha3 as _pysha3
        def _fast_keccak256(data):
            return _pysha3.keccak_256(data).digest()
        KECCAK_ENGINE = "pysha3"
    except ImportError:
        def _fast_keccak256(data):
            return bytes(Web3.keccak(data))
        KECCAK_ENGINE = "web3 (slow)"


def _increment_nonce_bytes(nonce_ba):
    """Increment a 32-byte big-endian bytearray in-place. Much faster than
    int.to_bytes() conversion on every iteration."""
    for i in range(31, -1, -1):
        nonce_ba[i] = (nonce_ba[i] + 1) & 0xFF
        if nonce_ba[i] != 0:
            return
    # overflow wraps around (extremely unlikely for 256-bit)


def _mining_worker(worker_id, prefix_bytes, target_bytes, num_workers,
                   stop_flag, result_nonce, result_digest,
                   hashrate_array, total_hashes_array):
    """Standalone mining worker that runs in its own process (no GIL)."""
    # Re-import keccak inside the child process
    try:
        from Crypto.Hash import keccak as _keccak_mod
        def keccak(data):
            return _keccak_mod.new(digest_bits=256, data=data).digest()
    except ImportError:
        try:
            import sha3 as _sha3_mod
            def keccak(data):
                return _sha3_mod.keccak_256(data).digest()
        except ImportError:
            from web3 import Web3 as _W3
            def keccak(data):
                return bytes(_W3.keccak(data))

    # Each worker starts from a unique random offset to avoid overlap
    nonce_int = random.randint(0, 2**64) + worker_id * (2**56)
    nonce_ba = bytearray(nonce_int.to_bytes(32, 'big'))
    prefix = bytes(prefix_bytes)
    target = bytes(target_bytes)

    batch_size = 200_000  # 10x larger batch = less overhead
    last_time = time.monotonic()
    local_hashes = 0

    while not stop_flag.value:
        for _ in range(batch_size):
            _increment_nonce_bytes(nonce_ba)
            digest = keccak(prefix + bytes(nonce_ba))
            if digest <= target:
                if stop_flag.value:
                    return
                # Found a valid nonce - store result
                stop_flag.value = 1
                found_int = int.from_bytes(nonce_ba, 'big')
                result_nonce.value = found_int
                result_digest[:] = digest
                return

        local_hashes += batch_size

        now = time.monotonic()
        elapsed = now - last_time
        if elapsed >= 2.0:
            rate = local_hashes / elapsed
            hashrate_array[worker_id] = rate
            total_hashes_array[worker_id] += local_hashes
            last_time = now
            local_hashes = 0


class MiningEngine:
    """Multi-process mining engine. Each CPU core runs an independent process,
    bypassing the GIL for true parallel hashing."""

    def __init__(self, w3, contract, account, on_log, on_found, num_threads=None):
        self.w3 = w3
        self.contract = contract
        self.account = account
        self.on_log = on_log
        self.on_found = on_found
        self.running = False
        self.hashrate = 0
        self.total_hashes = 0
        self.num_workers = num_threads or max(1, os.cpu_count() or 1)
        self._processes = []

    def start(self):
        self.running = True
        self.on_log(f"Keccak engine: {KECCAK_ENGINE} | Workers: {self.num_workers} (multiprocessing)")
        threading.Thread(target=self._mine_loop, daemon=True).start()

    def stop(self):
        self.running = False
        self._kill_workers()

    def _kill_workers(self):
        for p in self._processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=2)
        self._processes.clear()

    def _mine_loop(self):
        while self.running:
            try:
                challenge = self.contract.functions.challengeNumber().call()
                target = self.contract.functions.miningTarget().call()
                target_bytes = target.to_bytes(32, 'big')
                self.on_log(f"Challenge: {challenge.hex()[:16]}... | Target: {target}")
                self._search_nonce_multiprocess(challenge, target_bytes)
            except Exception as e:
                self.on_log(f"[Error] {e}")
                if self.running:
                    time.sleep(5)

    def _search_nonce_multiprocess(self, challenge, target_bytes):
        """Launch N independent processes to search for nonce."""
        prefix = challenge + bytes.fromhex(self.account.address[2:])

        # Shared memory for inter-process communication
        stop_flag = multiprocessing.Value(ctypes.c_int, 0)
        result_nonce = multiprocessing.Value(ctypes.c_uint64, 0)
        result_digest = multiprocessing.Array(ctypes.c_ubyte, 32)
        hashrate_array = multiprocessing.Array(ctypes.c_double, self.num_workers)
        total_hashes_array = multiprocessing.Array(ctypes.c_uint64, self.num_workers)

        self._processes = []
        for wid in range(self.num_workers):
            p = multiprocessing.Process(
                target=_mining_worker,
                args=(wid, prefix, target_bytes, self.num_workers,
                      stop_flag, result_nonce, result_digest,
                      hashrate_array, total_hashes_array),
                daemon=True
            )
            self._processes.append(p)
            p.start()

        # Monitor loop: poll shared memory for hashrate updates & result
        while self.running and not stop_flag.value:
            time.sleep(1.0)
            self.hashrate = sum(hashrate_array)
            self.total_hashes = sum(total_hashes_array)
            if self.hashrate > 0:
                self.on_log(f"Hashrate: {self.hashrate:.0f} H/s | Total: {self.total_hashes:,}")

        if not self.running:
            stop_flag.value = 1
            self._kill_workers()
            return

        # Wait for all processes to finish
        for p in self._processes:
            p.join(timeout=5)
        self._processes.clear()

        # Update final total
        self.total_hashes = sum(total_hashes_array)

        if stop_flag.value and self.running:
            nonce = result_nonce.value
            # Re-verify with web3 keccak for the on-chain digest
            digest_web3 = Web3.keccak(prefix + nonce.to_bytes(32, 'big'))
            self.on_log(f"[FOUND] Valid nonce: {nonce}")
            self.on_found(nonce, digest_web3, challenge)


# ─── Helper: load icon ──────────────────────────────────────────────────────

def get_icon_path():
    """Get path to icon file, handling PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'icon_circle.png')


# ─── Main Application ───────────────────────────────────────────────────────

class SatoshiMinerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Satoshi Miner")
        self.root.geometry("980x780")
        self.root.minsize(880, 680)
        self.root.configure(bg=COLORS['bg'])

        # State
        self.w3 = None
        self.contract = None
        self.account = None
        self.engine = None
        self.mining = False
        self.history = []
        self.cur_lang = 'en'
        self.i18n_widgets = []
        self.start_time = None
        self.logo_img = None
        self.logo_img_small = None

        # Set window icon
        try:
            ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except:
            pass

        self._load_config()
        self._load_history()
        self._load_logo()
        self._build_ui()

    # ── Logo ──

    def _load_logo(self):
        if not HAS_PIL:
            return
        try:
            icon_path = get_icon_path()
            if os.path.exists(icon_path):
                img = Image.open(icon_path).convert("RGBA")
                # Large logo for header
                logo_large = img.resize((42, 42), Image.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(logo_large)
                # Small logo
                logo_small = img.resize((24, 24), Image.LANCZOS)
                self.logo_img_small = ImageTk.PhotoImage(logo_small)
        except:
            pass

    # ── i18n ──

    def t(self, key):
        return LANG[self.cur_lang].get(key, key)

    def _register_i18n(self, widget, key, attr='text'):
        self.i18n_widgets.append((widget, key, attr))

    def _apply_lang(self):
        for widget, key, attr in self.i18n_widgets:
            try:
                widget.config(**{attr: self.t(key)})
            except:
                pass
        if self.mining:
            self.mine_btn.config(text=self.t('stop_mining'))
            self.mining_status_label.config(text=self.t('mining_active'), fg=COLORS['green'])
        else:
            self.mine_btn.config(text=self.t('start_mining'))
            self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])
        self._update_status_display()

    def _toggle_lang(self):
        self.cur_lang = 'zh' if self.cur_lang == 'en' else 'en'
        self.lang_btn.config(text='EN' if self.cur_lang == 'zh' else '中文')
        self._apply_lang()

    # ── Config ──

    def _load_config(self):
        self.config = {"rpc": DEFAULT_RPC, "gas_price": "0.1", "gas_limit": "200000"}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    self.config.update(json.load(f))
            except:
                pass

    def _save_config(self):
        to_save = {"rpc": self.rpc_var.get(), "gas_price": self.gas_price_var.get(),
                    "gas_limit": self.gas_limit_var.get()}
        with open(CONFIG_FILE, "w") as f:
            json.dump(to_save, f)
        self._show_toast(self.t('settings_saved'))

    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE) as f:
                    self.history = json.load(f)
            except:
                self.history = []

    def _save_history(self):
        with open(HISTORY_FILE, "w") as f:
            json.dump(self.history[-200:], f, indent=2)

    # ── Toast ──

    def _show_toast(self, msg, duration=3000):
        toast = tk.Frame(self.root, bg=COLORS['bg_card'], highlightbackground=COLORS['accent'],
                         highlightthickness=1)
        inner = tk.Label(toast, text=f"  {msg}  ", bg=COLORS['bg_card'], fg=COLORS['accent'],
                         font=('Segoe UI', 11, 'bold'), padx=20, pady=10)
        inner.pack()
        toast.place(relx=0.5, y=60, anchor='n')
        self.root.after(duration, toast.destroy)

    # ── Build UI ──

    def _build_ui(self):
        # Main layout: sidebar + content
        self.main_container = tk.Frame(self.root, bg=COLORS['bg'])
        self.main_container.pack(fill='both', expand=True)

        self._build_sidebar()
        self._build_content_area()
        self._build_panels()
        self._show_panel('wallet')

    def _build_sidebar(self):
        """Bitcoin wallet style left sidebar navigation."""
        self.sidebar = tk.Frame(self.main_container, bg=COLORS['bg_card'], width=220)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        # Logo area
        logo_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=20, padx=16)
        logo_frame.pack(fill='x')

        logo_row = tk.Frame(logo_frame, bg=COLORS['bg_card'])
        logo_row.pack(anchor='center')

        if self.logo_img:
            logo_label = tk.Label(logo_row, image=self.logo_img, bg=COLORS['bg_card'])
            logo_label.pack(side='left', padx=(0, 10))

        title_col = tk.Frame(logo_row, bg=COLORS['bg_card'])
        title_col.pack(side='left')

        title_lbl = tk.Label(title_col, text=self.t('title'),
                              font=('Segoe UI', 14, 'bold'),
                              fg=COLORS['white'], bg=COLORS['bg_card'])
        title_lbl.pack(anchor='w')
        self._register_i18n(title_lbl, 'title')

        subtitle_lbl = tk.Label(title_col, text=self.t('subtitle'),
                                 font=('Segoe UI', 8),
                                 fg=COLORS['text3'], bg=COLORS['bg_card'])
        subtitle_lbl.pack(anchor='w')
        self._register_i18n(subtitle_lbl, 'subtitle')

        # Separator
        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        # Connection status indicator
        self.status_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], padx=16, pady=12)
        self.status_frame.pack(fill='x')

        status_row = tk.Frame(self.status_frame, bg=COLORS['bg_card'])
        status_row.pack(fill='x')

        self.status_dot = tk.Canvas(status_row, width=10, height=10, bg=COLORS['bg_card'],
                                     highlightthickness=0)
        self.status_dot.pack(side='left', padx=(0, 8))
        self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['red_dim'], outline='')

        self.status_label = tk.Label(status_row, text=self.t('not_connected'),
                                      font=('Segoe UI', 9), fg=COLORS['text2'],
                                      bg=COLORS['bg_card'])
        self.status_label.pack(side='left')

        # Separator
        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        # Nav buttons
        nav_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=8)
        nav_frame.pack(fill='x')

        self.tab_buttons = {}
        tabs = [
            ('wallet', 'tab_wallet', '\u229a'),   # ⊚
            ('mine', 'tab_mine', '\u26cf'),        # ⛏
            ('history', 'tab_history', '\u2630'),   # ☰
            ('settings', 'tab_settings', '\u2699'), # ⚙
        ]

        for tab_id, lang_key, icon in tabs:
            btn_frame = tk.Frame(nav_frame, bg=COLORS['bg_card'], cursor='hand2')
            btn_frame.pack(fill='x', padx=8, pady=1)

            icon_lbl = tk.Label(btn_frame, text=icon, font=('Segoe UI', 13),
                                fg=COLORS['text3'], bg=COLORS['bg_card'], width=2)
            icon_lbl.pack(side='left', padx=(12, 6), pady=10)

            text_lbl = tk.Label(btn_frame, text=self.t(lang_key), font=('Segoe UI', 11),
                                fg=COLORS['text2'], bg=COLORS['bg_card'], anchor='w')
            text_lbl.pack(side='left', fill='x', expand=True, pady=10)
            self._register_i18n(text_lbl, lang_key)

            self.tab_buttons[tab_id] = (btn_frame, icon_lbl, text_lbl)

            # Click handlers
            for widget in (btn_frame, icon_lbl, text_lbl):
                widget.bind('<Button-1>', lambda e, t=tab_id: self._show_panel(t))
                widget.bind('<Enter>', lambda e, bf=btn_frame, il=icon_lbl, tl=text_lbl, t=tab_id:
                            self._on_tab_hover(t, bf, il, tl, True))
                widget.bind('<Leave>', lambda e, bf=btn_frame, il=icon_lbl, tl=text_lbl, t=tab_id:
                            self._on_tab_hover(t, bf, il, tl, False))

        # Bottom area: language toggle
        spacer = tk.Frame(self.sidebar, bg=COLORS['bg_card'])
        spacer.pack(fill='both', expand=True)

        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        bottom_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=12, padx=16)
        bottom_frame.pack(fill='x', side='bottom')

        self.lang_btn = tk.Button(bottom_frame, text='中文', font=('Segoe UI', 9, 'bold'),
                                   bg=COLORS['bg_card2'], fg=COLORS['text2'],
                                   activebackground=COLORS['bg_hover'], activeforeground=COLORS['accent'],
                                   relief='flat', padx=12, pady=4, cursor='hand2', bd=0,
                                   command=self._toggle_lang)
        self.lang_btn.pack(side='left')

        version_lbl = tk.Label(bottom_frame, text='v2.0.0', font=('Segoe UI', 8),
                                fg=COLORS['text3'], bg=COLORS['bg_card'])
        version_lbl.pack(side='right')

    def _on_tab_hover(self, tab_id, btn_frame, icon_lbl, text_lbl, entering):
        if hasattr(self, '_active_tab') and self._active_tab == tab_id:
            return
        if entering:
            btn_frame.config(bg=COLORS['bg_hover'])
            icon_lbl.config(bg=COLORS['bg_hover'])
            text_lbl.config(bg=COLORS['bg_hover'])
        else:
            btn_frame.config(bg=COLORS['bg_card'])
            icon_lbl.config(bg=COLORS['bg_card'])
            text_lbl.config(bg=COLORS['bg_card'])

    def _build_content_area(self):
        self.content_area = tk.Frame(self.main_container, bg=COLORS['bg'])
        self.content_area.pack(side='left', fill='both', expand=True)

        # Top bar
        topbar = tk.Frame(self.content_area, bg=COLORS['bg'], pady=12, padx=24)
        topbar.pack(fill='x')

        self.page_title = tk.Label(topbar, text='', font=('Segoe UI', 18, 'bold'),
                                    fg=COLORS['white'], bg=COLORS['bg'])
        self.page_title.pack(side='left')

        # Mining status badge (top right)
        self.mining_status_label = tk.Label(topbar, text=self.t('mining_idle'),
                                             font=('Segoe UI', 9, 'bold'),
                                             fg=COLORS['text3'], bg=COLORS['bg_card2'],
                                             padx=12, pady=4)
        self.mining_status_label.pack(side='right')

        tk.Frame(self.content_area, bg=COLORS['border'], height=1).pack(fill='x')

        # Content frame
        self.content_frame = tk.Frame(self.content_area, bg=COLORS['bg'])
        self.content_frame.pack(fill='both', expand=True)

    def _show_panel(self, name):
        self._active_tab = name

        # Update sidebar highlighting
        for tid, (bf, il, tl) in self.tab_buttons.items():
            if tid == name:
                bf.config(bg=COLORS['bg_card2'])
                il.config(fg=COLORS['accent'], bg=bf.cget('bg'))
                tl.config(fg=COLORS['white'], bg=bf.cget('bg'), font=('Segoe UI', 11, 'bold'))
            else:
                bf.config(bg=COLORS['bg_card'])
                il.config(fg=COLORS['text3'], bg=COLORS['bg_card'])
                tl.config(fg=COLORS['text2'], bg=COLORS['bg_card'], font=('Segoe UI', 11))

        # Update page title
        title_map = {
            'wallet': 'tab_wallet',
            'mine': 'tab_mine',
            'history': 'tab_history',
            'settings': 'tab_settings',
        }
        self.page_title.config(text=self.t(title_map.get(name, name)))

        # Show panel
        for child in self.content_frame.winfo_children():
            child.pack_forget()

        if hasattr(self, 'panels') and name in self.panels:
            self.panels[name].pack(fill='both', expand=True)

    def _build_panels(self):
        self.panels = {}
        self._build_wallet_panel()
        self._build_mine_panel()
        self._build_history_panel()
        self._build_settings_panel()

    # ── WALLET PANEL ──

    def _build_wallet_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['wallet'] = panel

        # Scrollable
        canvas = tk.Canvas(panel, bg=COLORS['bg'], highlightthickness=0, bd=0)
        content = tk.Frame(canvas, bg=COLORS['bg'])
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas_window = canvas.create_window((0, 0), window=content, anchor='nw')

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        canvas.pack(fill='both', expand=True)

        pad = {'padx': 24, 'pady': (0, 16)}

        # ── Connection Card ──
        conn_card = self._make_card(content)
        conn_card.pack(fill='x', padx=24, pady=(16, 16))

        conn_header = tk.Frame(conn_card, bg=COLORS['bg_card'])
        conn_header.pack(fill='x')
        conn_icon = tk.Label(conn_header, text='\u26a1', font=('Segoe UI', 14),
                              fg=COLORS['accent'], bg=COLORS['bg_card'])
        conn_icon.pack(side='left', padx=(0, 8))
        conn_title = tk.Label(conn_header, text=self.t('connection'),
                               font=('Segoe UI', 13, 'bold'),
                               fg=COLORS['white'], bg=COLORS['bg_card'])
        conn_title.pack(side='left')
        self._register_i18n(conn_title, 'connection')

        self._make_separator(conn_card)

        # RPC
        rpc_lbl = tk.Label(conn_card, text=self.t('rpc_url'), font=('Segoe UI', 9, 'bold'),
                            fg=COLORS['text2'], bg=COLORS['bg_card'])
        rpc_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(rpc_lbl, 'rpc_url')

        self.rpc_var = tk.StringVar(value=self.config['rpc'])
        rpc_entry = self._make_entry(conn_card, textvariable=self.rpc_var)
        rpc_entry.pack(fill='x', pady=(0, 12), ipady=8)

        # Private Key
        pk_lbl = tk.Label(conn_card, text=self.t('private_key'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        pk_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(pk_lbl, 'private_key')

        pk_row = tk.Frame(conn_card, bg=COLORS['bg_card'])
        pk_row.pack(fill='x', pady=(0, 16))

        self.pk_var = tk.StringVar()
        self.pk_entry = self._make_entry(pk_row, textvariable=self.pk_var, show='*')
        self.pk_entry.pack(side='left', fill='x', expand=True, ipady=8)

        self.show_pk_var = tk.BooleanVar(value=False)
        show_btn = tk.Button(pk_row, text=self.t('show'), font=('Segoe UI', 9),
                              bg=COLORS['bg_card2'], fg=COLORS['text2'],
                              activebackground=COLORS['bg_hover'], relief='flat',
                              padx=12, cursor='hand2', bd=0,
                              command=self._toggle_pk)
        show_btn.pack(side='left', padx=(8, 0), ipady=8)
        self._register_i18n(show_btn, 'show')

        # Connect button
        self.connect_btn = self._make_accent_btn(conn_card, text=self.t('connect'),
                                                   command=self._connect)
        self.connect_btn.pack(fill='x', ipady=6)
        self._register_i18n(self.connect_btn, 'connect')

        # ── Balance Card (Bitcoin wallet style) ──
        balance_card = self._make_card(content)
        balance_card.pack(fill='x', **pad)

        bal_header = tk.Frame(balance_card, bg=COLORS['bg_card'])
        bal_header.pack(fill='x')

        if self.logo_img_small:
            tk.Label(bal_header, image=self.logo_img_small, bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))

        bal_title = tk.Label(bal_header, text=self.t('wallet_overview'),
                              font=('Segoe UI', 13, 'bold'),
                              fg=COLORS['white'], bg=COLORS['bg_card'])
        bal_title.pack(side='left')
        self._register_i18n(bal_title, 'wallet_overview')

        refresh_btn = tk.Button(bal_header, text=self.t('refresh'), font=('Segoe UI', 9),
                                 bg=COLORS['bg_card2'], fg=COLORS['text2'],
                                 activebackground=COLORS['bg_hover'], relief='flat',
                                 padx=10, pady=2, cursor='hand2', bd=0,
                                 command=self._refresh_info)
        refresh_btn.pack(side='right')
        self._register_i18n(refresh_btn, 'refresh')

        self._make_separator(balance_card)

        # Main balance display (big number like Bitcoin wallet)
        self.main_balance_frame = tk.Frame(balance_card, bg=COLORS['bg_card'], pady=8)
        self.main_balance_frame.pack(fill='x')

        sat_icon = tk.Label(self.main_balance_frame, text='₿', font=('Segoe UI', 28),
                             fg=COLORS['accent'], bg=COLORS['bg_card'])
        sat_icon.pack(side='left', padx=(0, 8))

        bal_col = tk.Frame(self.main_balance_frame, bg=COLORS['bg_card'])
        bal_col.pack(side='left')

        self.big_balance_label = tk.Label(bal_col, text='0.00000000 SAT',
                                           font=('Segoe UI', 24, 'bold'),
                                           fg=COLORS['white'], bg=COLORS['bg_card'])
        self.big_balance_label.pack(anchor='w')

        self.address_label = tk.Label(bal_col, text='--',
                                       font=('Consolas', 10),
                                       fg=COLORS['text3'], bg=COLORS['bg_card'])
        self.address_label.pack(anchor='w')

        self._make_separator(balance_card)

        # Stats grid
        stats_frame = tk.Frame(balance_card, bg=COLORS['bg_card'])
        stats_frame.pack(fill='x')

        stat_defs = [
            ('bnb_balance', 'bnb_balance', COLORS['text']),
            ('sat_balance', 'sat_balance', COLORS['accent']),
            ('total_mined', 'total_mined', COLORS['text']),
            ('mining_reward', 'mining_reward', COLORS['accent']),
            ('difficulty', 'difficulty', COLORS['text']),
            ('epoch', 'epoch', COLORS['text']),
            ('era', 'era', COLORS['green']),
        ]

        self.stat_labels = {}
        for i, (sid, lang_key, color) in enumerate(stat_defs):
            r, c = divmod(i, 2)
            cell = tk.Frame(stats_frame, bg=COLORS['bg_card2'], padx=14, pady=10)
            cell.grid(row=r, column=c, padx=(0 if c == 0 else 4, 4 if c == 0 else 0),
                      pady=3, sticky='nsew')

            lbl = tk.Label(cell, text=self.t(lang_key).upper(), font=('Segoe UI', 8, 'bold'),
                           fg=COLORS['text3'], bg=COLORS['bg_card2'])
            lbl.pack(anchor='w')
            self._register_i18n(lbl, lang_key)

            val = tk.Label(cell, text='--', font=('Segoe UI', 13, 'bold'),
                           fg=color, bg=COLORS['bg_card2'])
            val.pack(anchor='w', pady=(2, 0))
            self.stat_labels[sid] = val

        stats_frame.columnconfigure(0, weight=1)
        stats_frame.columnconfigure(1, weight=1)

    # ── MINE PANEL ──

    def _build_mine_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['mine'] = panel

        canvas = tk.Canvas(panel, bg=COLORS['bg'], highlightthickness=0, bd=0)
        content = tk.Frame(canvas, bg=COLORS['bg'])
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas_window = canvas.create_window((0, 0), window=content, anchor='nw')

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all('<MouseWheel>', _on_mousewheel)
        canvas.pack(fill='both', expand=True)

        # ── Mining Control Card ──
        ctrl_card = self._make_card(content)
        ctrl_card.pack(fill='x', padx=24, pady=(16, 16))

        ctrl_header = tk.Frame(ctrl_card, bg=COLORS['bg_card'])
        ctrl_header.pack(fill='x')
        tk.Label(ctrl_header, text='\u26cf', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        ctrl_title = tk.Label(ctrl_header, text=self.t('mining_dashboard'),
                               font=('Segoe UI', 13, 'bold'),
                               fg=COLORS['white'], bg=COLORS['bg_card'])
        ctrl_title.pack(side='left')
        self._register_i18n(ctrl_title, 'mining_dashboard')

        self._make_separator(ctrl_card)

        # Big mine button
        self.mine_btn = tk.Button(ctrl_card, text=self.t('start_mining'),
                                   font=('Segoe UI', 14, 'bold'),
                                   bg=COLORS['accent'], fg=COLORS['black'],
                                   activebackground=COLORS['accent_dark'],
                                   activeforeground=COLORS['black'],
                                   relief='flat', cursor='hand2', bd=0,
                                   command=self._toggle_mining)
        self.mine_btn.pack(fill='x', ipady=12)
        self.mine_btn.bind('<Enter>', lambda e: self.mine_btn.config(
            bg=COLORS['red'] if self.mining else COLORS['accent_dark']))
        self.mine_btn.bind('<Leave>', lambda e: self.mine_btn.config(
            bg=COLORS['red'] if self.mining else COLORS['accent']))

        # Stats row (3 columns)
        stats_row = tk.Frame(ctrl_card, bg=COLORS['bg_card'])
        stats_row.pack(fill='x', pady=(16, 0))

        for i, (key, default, color) in enumerate([
            ('hashrate', '0 H/s', COLORS['green']),
            ('blocks_found', '0', COLORS['accent']),
            ('total_hashes', '0', COLORS['blue']),
        ]):
            cell = tk.Frame(stats_row, bg=COLORS['bg_card2'], padx=14, pady=10)
            cell.pack(side='left', fill='x', expand=True,
                      padx=(0 if i == 0 else 4, 4 if i < 2 else 0))

            lbl = tk.Label(cell, text=self.t(key).upper(), font=('Segoe UI', 8, 'bold'),
                           fg=COLORS['text3'], bg=COLORS['bg_card2'])
            lbl.pack(anchor='w')
            self._register_i18n(lbl, key)

            val_lbl = tk.Label(cell, text=default, font=('Segoe UI', 16, 'bold'),
                               fg=color, bg=COLORS['bg_card2'])
            val_lbl.pack(anchor='w', pady=(2, 0))

            if key == 'hashrate':
                self.hashrate_label = val_lbl
            elif key == 'blocks_found':
                self.blocks_label = val_lbl
            elif key == 'total_hashes':
                self.total_hashes_label = val_lbl

        # ── Mining Log Card ──
        log_card = self._make_card(content)
        log_card.pack(fill='x', padx=24, pady=(0, 16))

        log_header = tk.Frame(log_card, bg=COLORS['bg_card'])
        log_header.pack(fill='x')

        tk.Label(log_header, text='\u2630', font=('Segoe UI', 13),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        log_title = tk.Label(log_header, text=self.t('mining_log'),
                              font=('Segoe UI', 13, 'bold'),
                              fg=COLORS['white'], bg=COLORS['bg_card'])
        log_title.pack(side='left')
        self._register_i18n(log_title, 'mining_log')

        clear_btn = tk.Button(log_header, text=self.t('clear_log'), font=('Segoe UI', 9),
                               bg=COLORS['bg_card2'], fg=COLORS['text2'],
                               activebackground=COLORS['bg_hover'], relief='flat',
                               padx=10, pady=2, cursor='hand2', bd=0,
                               command=lambda: self.log_text.delete('1.0', 'end'))
        clear_btn.pack(side='right')
        self._register_i18n(clear_btn, 'clear_log')

        self._make_separator(log_card)

        self.log_text = scrolledtext.ScrolledText(
            log_card, height=14, bg=COLORS['bg'], fg=COLORS['green'],
            font=('Consolas', 9), insertbackground=COLORS['green'],
            relief='flat', highlightthickness=1, bd=0,
            highlightcolor=COLORS['border'], highlightbackground=COLORS['border']
        )
        self.log_text.pack(fill='both', expand=True)

    # ── HISTORY PANEL ──

    def _build_history_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['history'] = panel

        # Header card
        header_card = self._make_card(panel)
        header_card.pack(fill='x', padx=24, pady=(16, 0))

        h_header = tk.Frame(header_card, bg=COLORS['bg_card'])
        h_header.pack(fill='x')
        tk.Label(h_header, text='\u2630', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        h_title = tk.Label(h_header, text=self.t('history_title'),
                            font=('Segoe UI', 13, 'bold'),
                            fg=COLORS['white'], bg=COLORS['bg_card'])
        h_title.pack(side='left')
        self._register_i18n(h_title, 'history_title')

        # Column headers
        col_frame = tk.Frame(panel, bg=COLORS['bg_card2'], padx=24, pady=10)
        col_frame.pack(fill='x', padx=24, pady=(12, 2))

        cols = [('time', 16), ('nonce', 14), ('reward', 14), ('tx_hash', 22), ('status', 8)]
        self.history_col_labels = []
        for key, w in cols:
            lbl = tk.Label(col_frame, text=self.t(key).upper(), font=('Segoe UI', 8, 'bold'),
                           fg=COLORS['accent'], bg=COLORS['bg_card2'], width=w, anchor='w')
            lbl.pack(side='left', padx=2)
            self.history_col_labels.append((lbl, key))
            self._register_i18n(lbl, key)

        # Scrollable history
        h_canvas = tk.Canvas(panel, bg=COLORS['bg'], highlightthickness=0, bd=0)
        h_scroll = tk.Scrollbar(panel, orient='vertical', command=h_canvas.yview,
                                 bg=COLORS['bg_card2'], troughcolor=COLORS['bg'])
        self.history_list_frame = tk.Frame(h_canvas, bg=COLORS['bg'])

        self.history_list_frame.bind('<Configure>',
                                      lambda e: h_canvas.configure(scrollregion=h_canvas.bbox('all')))
        h_canvas_window = h_canvas.create_window((0, 0), window=self.history_list_frame, anchor='nw')
        h_canvas.configure(yscrollcommand=h_scroll.set)

        def _on_h_canvas_configure(event):
            h_canvas.itemconfig(h_canvas_window, width=event.width)
        h_canvas.bind('<Configure>', _on_h_canvas_configure)

        h_canvas.pack(side='left', fill='both', expand=True, padx=(24, 0), pady=(0, 16))
        h_scroll.pack(side='right', fill='y', padx=(0, 24), pady=(0, 16))

        self._populate_history()

    def _populate_history(self):
        for w in self.history_list_frame.winfo_children():
            w.destroy()
        if not self.history:
            tk.Label(self.history_list_frame, text=self.t('no_records'),
                     font=('Segoe UI', 11), fg=COLORS['text3'], bg=COLORS['bg'],
                     pady=40).pack()
            return
        for entry in reversed(self.history):
            self._add_history_row(entry, prepend=False)

    def _add_history_row(self, entry, prepend=True):
        bg = COLORS['bg_card']
        row = tk.Frame(self.history_list_frame, bg=bg, padx=24, pady=8)
        if prepend:
            children = self.history_list_frame.winfo_children()
            # Remove "no records" label if present
            for c in children:
                if isinstance(c, tk.Label):
                    c.destroy()
            row.pack(fill='x', pady=1, before=self.history_list_frame.winfo_children()[0]
                     if self.history_list_frame.winfo_children() else None)
        else:
            row.pack(fill='x', pady=1)

        status = entry.get('status', '')
        status_color = COLORS['green'] if status == 'Success' else COLORS['red']

        vals = [
            (entry.get('time', ''), 16, COLORS['text2']),
            (str(entry.get('nonce', ''))[:14], 14, COLORS['text']),
            (entry.get('reward', ''), 14, COLORS['accent']),
            (entry.get('tx_hash', '')[:20] + '...' if len(entry.get('tx_hash', '')) > 20 else entry.get('tx_hash', ''), 22, COLORS['blue']),
            (status, 8, status_color),
        ]
        for text, w, fg in vals:
            tk.Label(row, text=text, font=('Consolas', 9), fg=fg, bg=bg,
                     width=w, anchor='w').pack(side='left', padx=2)

    # ── SETTINGS PANEL ──

    def _build_settings_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['settings'] = panel

        canvas = tk.Canvas(panel, bg=COLORS['bg'], highlightthickness=0, bd=0)
        content = tk.Frame(canvas, bg=COLORS['bg'])
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas_window = canvas.create_window((0, 0), window=content, anchor='nw')

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', _on_canvas_configure)
        canvas.pack(fill='both', expand=True)

        # ── Gas Settings Card ──
        gas_card = self._make_card(content)
        gas_card.pack(fill='x', padx=24, pady=(16, 16))

        gas_header = tk.Frame(gas_card, bg=COLORS['bg_card'])
        gas_header.pack(fill='x')
        tk.Label(gas_header, text='\u2699', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        gas_title = tk.Label(gas_header, text=self.t('gas_settings'),
                              font=('Segoe UI', 13, 'bold'),
                              fg=COLORS['white'], bg=COLORS['bg_card'])
        gas_title.pack(side='left')
        self._register_i18n(gas_title, 'gas_settings')

        self._make_separator(gas_card)

        # Gas Price
        gp_lbl = tk.Label(gas_card, text=self.t('gas_price'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        gp_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(gp_lbl, 'gas_price')

        self.gas_price_var = tk.StringVar(value=self.config.get('gas_price', '5'))
        gp_entry = self._make_entry(gas_card, textvariable=self.gas_price_var)
        gp_entry.pack(fill='x', pady=(0, 12), ipady=8)

        # Gas Limit
        gl_lbl = tk.Label(gas_card, text=self.t('gas_limit'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        gl_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(gl_lbl, 'gas_limit')

        self.gas_limit_var = tk.StringVar(value=self.config.get('gas_limit', '200000'))
        gl_entry = self._make_entry(gas_card, textvariable=self.gas_limit_var)
        gl_entry.pack(fill='x', pady=(0, 12), ipady=8)

        # Contract
        ct_lbl = tk.Label(gas_card, text=self.t('contract'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        ct_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(ct_lbl, 'contract')

        ct_val = tk.Label(gas_card, text=CONTRACT_ADDRESS, font=('Consolas', 10),
                           fg=COLORS['accent'], bg=COLORS['bg_card'])
        ct_val.pack(anchor='w', pady=(0, 16))

        # Save
        save_btn = self._make_accent_btn(gas_card, text=self.t('save_settings'),
                                          command=self._save_config)
        save_btn.pack(fill='x', ipady=6)
        self._register_i18n(save_btn, 'save_settings')

        # ── Contract Info Card ──
        info_card = self._make_card(content)
        info_card.pack(fill='x', padx=24, pady=(0, 16))

        info_header = tk.Frame(info_card, bg=COLORS['bg_card'])
        info_header.pack(fill='x')
        tk.Label(info_header, text='₿', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        info_title = tk.Label(info_header, text=self.t('contract_info'),
                               font=('Segoe UI', 13, 'bold'),
                               fg=COLORS['white'], bg=COLORS['bg_card'])
        info_title.pack(side='left')
        self._register_i18n(info_title, 'contract_info')

        self._make_separator(info_card)

        info_items = [
            ('network', 'BSC Mainnet'),
            ('max_supply', '21,000,000 SAT'),
            ('halving', self.t('every_era')),
        ]
        for key, val in info_items:
            row = tk.Frame(info_card, bg=COLORS['bg_card'], pady=6)
            row.pack(fill='x')
            lbl = tk.Label(row, text=self.t(key), font=('Segoe UI', 10, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
            lbl.pack(side='left')
            self._register_i18n(lbl, key)
            tk.Label(row, text=val, font=('Segoe UI', 10, 'bold'),
                     fg=COLORS['white'], bg=COLORS['bg_card']).pack(side='right')

        # ── About Card ──
        about_card = self._make_card(content)
        about_card.pack(fill='x', padx=24, pady=(0, 24))

        about_header = tk.Frame(about_card, bg=COLORS['bg_card'])
        about_header.pack(fill='x')
        tk.Label(about_header, text='\u2139', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        about_title = tk.Label(about_header, text=self.t('about'),
                                font=('Segoe UI', 13, 'bold'),
                                fg=COLORS['white'], bg=COLORS['bg_card'])
        about_title.pack(side='left')
        self._register_i18n(about_title, 'about')

        self._make_separator(about_card)

        self.about_label = tk.Label(about_card, text=self.t('about_text'),
                                     font=('Segoe UI', 10), fg=COLORS['text2'],
                                     bg=COLORS['bg_card'], justify='left', wraplength=550)
        self.about_label.pack(anchor='w', fill='x')
        self._register_i18n(self.about_label, 'about_text')

        # Dynamic wraplength for about text (with guard to prevent infinite loop)
        self._about_last_width = 0
        def _update_about_wrap(event):
            new_w = max(200, event.width - 60)
            if abs(new_w - self._about_last_width) > 10:
                self._about_last_width = new_w
                self.about_label.config(wraplength=new_w)
        about_card.bind('<Configure>', _update_about_wrap)

    # ── Shared widget builders ──

    def _make_card(self, parent):
        card = tk.Frame(parent, bg=COLORS['bg_card'], padx=20, pady=16,
                         highlightbackground=COLORS['border'], highlightthickness=1)
        return card

    def _make_separator(self, parent):
        tk.Frame(parent, bg=COLORS['border'], height=1).pack(fill='x', pady=(10, 12))

    def _make_entry(self, parent, **kwargs):
        entry = tk.Entry(parent, bg=COLORS['bg_input'], fg=COLORS['text'],
                          insertbackground=COLORS['accent'], relief='flat',
                          font=('Consolas', 11), highlightthickness=1,
                          highlightcolor=COLORS['accent'],
                          highlightbackground=COLORS['border'], **kwargs)
        return entry

    def _make_accent_btn(self, parent, text='', command=None):
        btn = tk.Button(parent, text=text, command=command,
                         bg=COLORS['accent'], fg=COLORS['black'],
                         activebackground=COLORS['accent_dark'],
                         activeforeground=COLORS['black'],
                         font=('Segoe UI', 12, 'bold'), relief='flat',
                         cursor='hand2', bd=0)
        btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['accent_dark']))
        btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['accent']))
        return btn

    # ── Actions ──

    def _toggle_pk(self):
        self.show_pk_var.set(not self.show_pk_var.get())
        self.pk_entry.config(show='' if self.show_pk_var.get() else '*')

    def _update_status_display(self):
        if self.w3 and self.account:
            self.status_dot.delete('all')
            self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['green'], outline='')
            self.status_label.config(text=self.t('connected'), fg=COLORS['green'])
        else:
            self.status_dot.delete('all')
            self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['red_dim'], outline='')
            self.status_label.config(text=self.t('not_connected'), fg=COLORS['text2'])

    def _log(self, msg):
        def _do():
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert('end', f"[{ts}] {msg}\n")
            self.log_text.see('end')
        self.root.after(0, _do)

    def _connect(self):
        rpc = self.rpc_var.get().strip()
        pk = self.pk_var.get().strip()

        if not rpc:
            messagebox.showerror(self.t('error'), self.t('enter_rpc'))
            return
        if not pk:
            messagebox.showerror(self.t('error'), self.t('enter_pk'))
            return

        try:
            self.w3 = Web3(Web3.HTTPProvider(rpc))
            if not self.w3.is_connected():
                raise Exception("Cannot connect to RPC")

            self.account = Account.from_key(pk)
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

            chain_id = self.w3.eth.chain_id
            self._log(f"Connected to chain {chain_id} via {rpc}")
            self._log(f"Wallet: {self.account.address}")
            self._update_status_display()
            self._show_toast(self.t('connected'))
            self._save_config()
            self._refresh_info()

        except Exception as e:
            messagebox.showerror(self.t('error'), f"{self.t('conn_failed')}: {e}")
            self._log(f"[Error] {e}")

    def _refresh_info(self):
        if not self.w3 or not self.account:
            return
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            addr = self.account.address
            bnb = self.w3.eth.get_balance(addr)
            sat = self.contract.functions.balanceOf(addr).call()
            difficulty = self.contract.functions.getMiningDifficulty().call()
            reward = self.contract.functions.getMiningReward().call()
            epoch = self.contract.functions.epochCount().call()
            minted = self.contract.functions.tokensMinted().call()
            era = self.contract.functions.rewardEra().call()

            def _update():
                self.address_label.config(text=addr)
                self.big_balance_label.config(text=f"{sat / 1e8:.8f} SAT")
                self.stat_labels['bnb_balance'].config(text=f"{self.w3.from_wei(bnb, 'ether'):.6f}")
                self.stat_labels['sat_balance'].config(text=f"{sat / 1e8:.8f}")
                self.stat_labels['total_mined'].config(text=f"{minted / 1e8:.2f} / 21M")
                self.stat_labels['mining_reward'].config(text=f"{reward / 1e8:.8f}")
                self.stat_labels['difficulty'].config(text=f"{difficulty:,}")
                self.stat_labels['epoch'].config(text=f"{epoch:,}")
                self.stat_labels['era'].config(text=f"{era}")

            self.root.after(0, _update)
            self._log("Wallet info refreshed")
        except Exception as e:
            self._log(f"[Error] Refresh: {e}")

    def _toggle_mining(self):
        if self.mining:
            self._stop_mining()
        else:
            self._start_mining()

    def _start_mining(self):
        if not self.w3 or not self.account:
            messagebox.showerror(self.t('error'), self.t('connect_first'))
            return

        self.mining = True
        self.start_time = time.time()
        self.mine_btn.config(text=self.t('stop_mining'), bg=COLORS['red'])
        self.mining_status_label.config(text=self.t('mining_active'), fg=COLORS['green'])
        self._log(self.t('mining_started'))

        self.engine = MiningEngine(self.w3, self.contract, self.account,
                                    on_log=self._log, on_found=self._on_nonce_found)
        self.engine.start()
        self._update_hashrate()

    def _stop_mining(self):
        self.mining = False
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.mine_btn.config(text=self.t('start_mining'), bg=COLORS['accent'])
        self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])
        self._log(self.t('mining_stopped'))

    def _update_hashrate(self):
        if self.mining and self.engine:
            self.hashrate_label.config(text=f"{self.engine.hashrate:.0f} H/s")
            self.total_hashes_label.config(text=f"{self.engine.total_hashes:,}")
            self.root.after(2000, self._update_hashrate)

    def _on_nonce_found(self, nonce, digest, challenge):
        self._log(f"Submitting nonce={nonce}")
        threading.Thread(target=self._submit_solution, args=(nonce, digest, challenge), daemon=True).start()

    def _pre_validate_solution(self, nonce, digest, challenge):
        """提交前预判：检查 challenge 是否仍然有效，模拟执行 mint 交易。
        返回 (通过, 原因) 元组。"""
        try:
            # 检查1: 链上 challengeNumber 是否和挖矿时一致
            current_challenge = self.contract.functions.challengeNumber().call()
            if current_challenge != challenge:
                return False, "Challenge 已更新（被其他矿工抢先）"

            # 检查2: 该 challenge 是否已被解决
            solution = self.contract.functions.solutionForChallenge(challenge).call()
            if solution != b'\x00' * 32:
                return False, "该 Challenge 已被解决"

            # 检查3: digest 是否仍然满足当前 target
            current_target = self.contract.functions.miningTarget().call()
            if int.from_bytes(digest, 'big') > current_target:
                return False, "Digest 超过当前 target（难度已调整）"

            # 检查4: 用 eth_call 模拟执行 mint，捕获 revert
            self.contract.functions.mint(nonce, digest).call({
                'from': self.account.address
            })

            return True, "预验证通过"
        except Exception as e:
            error_msg = str(e)
            if "already solved" in error_msg.lower():
                return False, "Challenge 已被其他矿工解决"
            elif "exceeds" in error_msg.lower() or "target" in error_msg.lower():
                return False, "Digest 不满足当前难度要求"
            elif "invalid" in error_msg.lower():
                return False, "无效的 challenge digest"
            else:
                return False, f"模拟执行失败: {error_msg}"

    def _submit_solution(self, nonce, digest, challenge):
        try:
            # ── 预判阶段：提交前验证，避免浪费 gas ──
            valid, reason = self._pre_validate_solution(nonce, digest, challenge)
            if not valid:
                self._log(f"[跳过提交] {reason}，节省 gas 费")
                # 记录跳过的条目
                entry = {
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "nonce": str(nonce), "reward": "0",
                    "tx_hash": "N/A (预判跳过)", "status": "Skipped"
                }
                self.history.append(entry)
                self._save_history()
                self.root.after(0, lambda: self._add_history_row(entry))
                return
            self._log("[预判通过] 提交交易中...")

            addr = self.account.address
            gas_price = self.w3.to_wei(float(self.gas_price_var.get()), 'gwei')
            gas_limit = int(self.gas_limit_var.get())
            nonce_tx = self.w3.eth.get_transaction_count(addr)

            tx = self.contract.functions.mint(nonce, digest).build_transaction({
                'from': addr, 'gas': gas_limit, 'gasPrice': gas_price,
                'nonce': nonce_tx, 'chainId': self.w3.eth.chain_id
            })

            signed = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hex = tx_hash.hex()
            self._log(f"TX sent: {tx_hex}")

            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            status = "Success" if receipt['status'] == 1 else "Failed"
            reward = self.contract.functions.getMiningReward().call()
            self._log(f"TX {status}: {tx_hex}")

            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nonce": str(nonce), "reward": f"{reward / 1e8:.8f} SAT",
                "tx_hash": tx_hex, "status": status
            }
            self.history.append(entry)
            self._save_history()

            def _ui():
                self._add_history_row(entry)
                blocks = len([h for h in self.history if h.get('status') == 'Success'])
                self.blocks_label.config(text=str(blocks))
            self.root.after(0, _ui)
            self._refresh_info()

        except Exception as e:
            self._log(f"[Error] Submit: {e}")
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nonce": str(nonce), "reward": "0", "tx_hash": "N/A", "status": "Error"
            }
            self.history.append(entry)
            self._save_history()


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    multiprocessing.freeze_support()  # Required for PyInstaller on Windows
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
    app = SatoshiMinerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
