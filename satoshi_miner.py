#!/usr/bin/env python3
"""
Satoshi (SAT) Token Miner v3.0 — 反应式挖矿 + GUI
整合测试安装包的全部挖矿规则:
  - WebSocket 订阅 Mint 事件 (零轮询检测新挑战号)
  - GPU OpenCL 求解器 (高难度时自动启用)
  - CPU 常驻热池 (多进程, 零冷启动)
  - 多 relay 并行广播 (bloXroute / 48 Club)
  - Gas 跟网络地板价, 不加价
  - 自动 detect 模式 (logs -> heads 退化)
  - 试运行 (DRY_RUN) 支持
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
import signal
import asyncio
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
    from web3.middleware import ExtraDataToPOAMiddleware as _POA
except Exception:
    from web3.middleware import geth_poa_middleware as _POA

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import websockets
    HAS_WS = True
except ImportError:
    HAS_WS = False

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image, ImageTk, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from Crypto.Hash import keccak as _pycryptodome_keccak
    def _fast_keccak256(data):
        return _pycryptodome_keccak.new(digest_bits=256, data=data).digest()
    KECCAK_ENGINE = "pycryptodome"
except ImportError:
    def _fast_keccak256(data):
        return bytes(Web3.keccak(data))
    KECCAK_ENGINE = "web3 (slow)"

try:
    import keccak_pow
    HAS_C_EXT = True
except ImportError:
    HAS_C_EXT = False

# ─── Constants ───────────────────────────────────────────────────────────────

CONTRACT_ADDRESS = "0x14Dc4b4929c664534f1d4D64107d8F36CbF906a0"
DEFAULT_RPC = "https://bsc-dataseed.bnbchain.org"
CONFIG_FILE = "miner_config.json"
HISTORY_FILE = "mining_history.json"
SOLVED_CACHE_FILE = "solved_challenges.json"
YAML_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

IS_WINDOWS = (os.name == "nt")

MINT_SELECTOR = "1801fbe5"  # mint(uint256,bytes32)
MINT_TOPIC = "0x" + Web3.keccak(text="Mint(address,uint256,uint256,bytes32)").hex().lstrip("0x")

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

# 默认 relay 节点 (直投验证者, 减少 mempool 延迟)
DEFAULT_RELAYS = [
    "https://bsc.rpc.blxrbdn.com",
    "https://rpc-bsc.48.club",
    "https://0.48.club",
]

# 默认 WebSocket 节点
DEFAULT_WS = ["wss://bsc.drpc.org"]
DEFAULT_HEAD_WS = "wss://bsc-rpc.publicnode.com"

# 默认 RPC 测速列表
DEFAULT_RPC_LIST = [
    "https://bsc.rpc.blxrbdn.com",
    "https://1rpc.io/bnb",
    "https://binance.nodereal.io",
    "https://bsc-mainnet.public.blastapi.io",
    "https://bsc-dataseed.bnbchain.org",
]

# Multicall3
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"
MULTICALL3_ABI = json.loads('''[
    {"inputs":[{"components":[{"name":"target","type":"address"},{"name":"callData","type":"bytes"}],"name":"calls","type":"tuple[]"}],"name":"aggregate","outputs":[{"name":"blockNumber","type":"uint256"},{"name":"returnData","type":"bytes[]"}],"stateMutability":"view","type":"function"}
]''')


# ─── YAML 配置加载 ────────────────────────────────────────────────────────────

def load_yaml_config():
    """加载 config.yaml, 返回字典; 不存在则返回默认值"""
    defaults = {
        "private_key": "",
        "contract_address": CONTRACT_ADDRESS,
        "chain_id": 56,
        "use_network_gas": True,
        "network_gas_multiplier": 1.0,
        "min_gas_price_gwei": 0.01,
        "max_gas_price_gwei": 5,
        "gas_price_gwei": 0.05,
        "gas_limit": 200000,
        "solver": "cpu",
        "gpu_device": "",
        "gpu_util": 100,
        "gpu_batch_size": 16000000,
        "relay_urls": DEFAULT_RELAYS,
        "ws_urls": DEFAULT_WS,
        "detect_mode": "auto",
        "head_ws": DEFAULT_HEAD_WS,
        "dry_run": False,
        "verbose_logs": False,
    }
    if HAS_YAML and os.path.exists(YAML_CONFIG_FILE):
        try:
            with open(YAML_CONFIG_FILE, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            defaults.update(cfg)
        except Exception:
            pass
    return defaults


# ─── 已解决 Challenge 缓存 ───────────────────────────────────────────────────

class SolvedChallengeCache:
    MAX_SIZE = 2000
    def __init__(self, filepath=SOLVED_CACHE_FILE):
        self._filepath = filepath
        self._lock = threading.Lock()
        self._cache = set()
        self._load()
    def _load(self):
        if os.path.exists(self._filepath):
            try:
                with open(self._filepath) as f:
                    data = json.load(f)
                    self._cache = set(data[-self.MAX_SIZE:])
            except Exception:
                self._cache = set()
    def _save(self):
        try:
            items = list(self._cache)[-self.MAX_SIZE:]
            with open(self._filepath, "w") as f:
                json.dump(items, f)
        except Exception:
            pass
    def is_solved(self, challenge_hex):
        with self._lock:
            return challenge_hex in self._cache
    def mark_solved(self, challenge_hex):
        with self._lock:
            self._cache.add(challenge_hex)
            if len(self._cache) > self.MAX_SIZE:
                excess = len(self._cache) - self.MAX_SIZE
                for _ in range(excess):
                    self._cache.pop()
            self._save()

_solved_cache = SolvedChallengeCache()


# ─── RPC 工具 ────────────────────────────────────────────────────────────────

class Multicall:
    def __init__(self, w3):
        self.w3 = w3
        self.multicall = w3.eth.contract(
            address=Web3.to_checksum_address(MULTICALL3_ADDRESS), abi=MULTICALL3_ABI)
    def batch_call(self, calls):
        aggregate_calls = []
        decoders = []
        for contract, fn_name, args in calls:
            fn = contract.functions[fn_name](*args)
            call_data = fn._encode_transaction_data()
            aggregate_calls.append((contract.address, call_data))
            decoders.append(fn)
        _, return_data = self.multicall.functions.aggregate(aggregate_calls).call()
        results = []
        for i, raw in enumerate(return_data):
            fn = decoders[i]
            output_types = [o['type'] for o in fn.abi['outputs']]
            decoded = self.w3.codec.decode(output_types, raw)
            results.append(decoded[0] if len(decoded) == 1 else decoded)
        return results


def select_best_rpc(rpc_urls, on_log=None):
    best, best_lat = None, None
    for url in rpc_urls:
        try:
            t0 = time.time()
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 6}))
            if not w3.is_connected():
                if on_log: on_log(f"  {url}  连接失败")
                continue
            _ = w3.eth.block_number
            lat = (time.time() - t0) * 1000
            if on_log: on_log(f"  {url}  {lat:.0f}ms")
            if best_lat is None or lat < best_lat:
                best, best_lat = url, lat
        except Exception as e:
            if on_log: on_log(f"  {url}  失败: {str(e)[:40]}")
    return best, best_lat


# ─── 广播器: 同一签名交易并行发往多个 relay ──────────────────────────────────

class Broadcaster:
    """复用 keep-alive 连接, 同一签名交易并行广播到多个直投验证者 relay."""
    def __init__(self, urls):
        self.urls = urls
        self.sessions = {}
        for u in urls:
            s = requests.Session()
            s.headers.update({"Content-Type": "application/json"})
            self.sessions[u] = s
        self._warm()

    def _warm(self):
        for u, s in self.sessions.items():
            try:
                s.post(u, json={"jsonrpc": "2.0", "id": 1,
                                "method": "eth_blockNumber", "params": []}, timeout=5)
            except Exception:
                pass

    def _send_one(self, url, raw_hex):
        t0 = time.perf_counter()
        try:
            r = self.sessions[url].post(url, json={
                "jsonrpc": "2.0", "id": 1,
                "method": "eth_sendRawTransaction", "params": [raw_hex]}, timeout=5)
            j = r.json()
            ms = (time.perf_counter() - t0) * 1000
            if "result" in j:
                return (url, True, ms, j["result"])
            err = str(j.get("error", {}).get("message", j))[:60]
            known = any(s in err.lower() for s in
                        ("already known", "known transaction", "already imported"))
            return (url, known, ms, err)
        except Exception as e:
            return (url, False, (time.perf_counter() - t0) * 1000, str(e)[:50])

    def broadcast(self, raw_hex):
        results = []
        threads = []
        lock = threading.Lock()
        def run(u):
            res = self._send_one(u, raw_hex)
            with lock:
                results.append(res)
        for u in self.urls:
            t = threading.Thread(target=run, args=(u,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=5)
        return results


# ─── Gas 策略: 跟网络地板价 ──────────────────────────────────────────────────

def gas_price_wei(w3, cfg):
    """跟网络地板价, 不加价 (与对手一致, 省钱)."""
    try:
        net = w3.eth.gas_price
    except Exception:
        net = Web3.to_wei(float(cfg.get("gas_price_gwei", 0.05)), "gwei")
    if cfg.get("use_network_gas", True):
        g = int(net * float(cfg.get("network_gas_multiplier", 1.0)))
        lo = Web3.to_wei(float(cfg.get("min_gas_price_gwei", 0.01)), "gwei")
        hi = Web3.to_wei(float(cfg.get("max_gas_price_gwei", 5)), "gwei")
        return max(lo, min(g, hi))
    return Web3.to_wei(float(cfg.get("gas_price_gwei", 0.05)), "gwei")


# ─── CPU 常驻热池 (多进程, 零冷启动) ──────────────────────────────────────────

def warm_worker(wid, num_workers, prefix_arr, target_arr, gen_val, base_val,
                stop_event, result_q):
    """常驻 CPU 求解进程: 从共享内存读 (prefix, target, generation),
    挑战号一变立刻切到新解, 零冷启动."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    from Crypto.Hash import keccak as _kc
    new = _kc.new
    local_gen = -1
    prefix = b""
    target = 0
    nonce = 0
    step = num_workers
    BATCH = 8192
    while not stop_event.is_set():
        g = gen_val.value
        if g == 0:
            time.sleep(0.002)
            continue
        if g != local_gen:
            local_gen = g
            with prefix_arr.get_lock():
                prefix = bytes(prefix_arr[:])
            with target_arr.get_lock():
                target = int.from_bytes(bytes(target_arr[:]), "big")
            nonce = (base_val.value + wid) & ((1 << 64) - 1)
        hit = False
        for _ in range(BATCH):
            k = new(digest_bits=256)
            k.update(prefix + nonce.to_bytes(32, "big"))
            d = k.digest()
            if int.from_bytes(d, "big") <= target:
                result_q.put((local_gen, nonce, d))
                hit = True
                break
            nonce += step
        if hit:
            while gen_val.value == local_gen and not stop_event.is_set():
                time.sleep(0.005)


def resolve_workers(cfg):
    cores = os.cpu_count() or 4
    try:
        pct = float(cfg.get("cpu_percent", 0) or 0)
    except (TypeError, ValueError):
        pct = 0
    if pct > 0:
        return max(1, round(cores * pct / 100))
    w = cfg.get("workers", "auto")
    if isinstance(w, int):
        return max(1, w)
    if isinstance(w, str) and w.isdigit():
        return max(1, int(w))
    if w == "max":
        return max(1, cores - 1)
    return max(1, cores // 2)


class CpuPool:
    """常驻多进程 CPU 求解池, 挑战号一变立刻切换, 零冷启动."""
    def __init__(self, cfg):
        method = cfg.get("start_method", "fork")
        if IS_WINDOWS:
            method = "spawn"
        try:
            self.ctx = multiprocessing.get_context(method)
        except ValueError:
            self.ctx = multiprocessing.get_context()
        self.n = resolve_workers(cfg)
        self.prefix = self.ctx.Array("B", 52)
        self.target = self.ctx.Array("B", 32)
        self.gen = self.ctx.Value("l", 0)
        self.base = self.ctx.Value("Q", 0)
        self.stop = self.ctx.Event()
        self.result_q = self.ctx.Queue()
        self.procs = []
        for wid in range(self.n):
            p = self.ctx.Process(target=warm_worker,
                                 args=(wid, self.n, self.prefix, self.target,
                                       self.gen, self.base, self.stop, self.result_q),
                                 daemon=True)
            p.start()
            self.procs.append(p)

    def set_challenge(self, prefix_bytes, target_int, gen, base_nonce):
        with self.prefix.get_lock():
            self.prefix[:] = prefix_bytes
        with self.target.get_lock():
            self.target[:] = target_int.to_bytes(32, "big")
        self.base.value = base_nonce & ((1 << 64) - 1)
        self.gen.value = gen

    def shutdown(self):
        self.stop.set()


# ─── GPU 求解器 ──────────────────────────────────────────────────────────────

class GpuSolver:
    """GPU OpenCL 求解器, 高难度时比 CPU 快得多."""
    def __init__(self, cfg):
        from gpu_miner import GpuMiner
        self.gpu = GpuMiner(cfg)
        util = cfg.get("gpu_util", 100)
        try:
            util = float(util)
        except (TypeError, ValueError):
            util = 100.0
        self.gpu.target_util = min(100.0, max(1.0, util))
        self.util = self.gpu.target_util
        self.batch = int(cfg.get("gpu_batch_size", 1_000_000))
        self.name = self.gpu.device_name

    def solve(self, prefix, target_bytes, target_int, start):
        n = start & ((1 << 48) - 1)
        while True:
            win = self.gpu.search(prefix, target_bytes, n, self.batch)
            if win is not None:
                k = _pycryptodome_keccak.new(digest_bits=256)
                k.update(prefix + int(win).to_bytes(32, "big"))
                d = k.digest()
                if int.from_bytes(d, "big") <= target_int:
                    return int(win), d
            n += self.batch
        return None, None


# ─── 反应式挖矿引擎 (整合测试安装包全部规则) ─────────────────────────────────

class ReactiveMiner:
    """整合测试安装包的全部挖矿规则:
    - WS 订阅 Mint 事件检测新挑战号 (零轮询)
    - CPU 热池 / GPU 求解
    - 多 relay 并行广播
    - Gas 跟网络地板价
    - 过期解自动丢弃
    - 试运行模式
    """
    def __init__(self, cfg, on_log=None, on_win=None, on_lose=None, on_stats=None):
        self.cfg = cfg
        self.on_log = on_log or (lambda msg, lv="INFO": None)
        self.on_win = on_win or (lambda epoch: None)
        self.on_lose = on_lose or (lambda: None)
        self.on_stats = on_stats or (lambda s: None)
        self.running = False
        self.dry = bool(os.environ.get("DRY_RUN")) or bool(cfg.get("dry_run", False))
        self.verbose = bool(cfg.get("verbose_logs", False))

        # Web3 连接 (用 relay 里最快的做 setup RPC)
        setup_rpc = (cfg.get("relay_urls") or DEFAULT_RELAYS)[0]
        self.w3 = Web3(Web3.HTTPProvider(setup_rpc, request_kwargs={"timeout": 8}))
        try:
            self.w3.middleware_onion.inject(_POA, layer=0)
        except Exception:
            self.w3.middleware_onion.inject(_POA(self.w3), layer=0)

        pk = cfg.get("_pk") or cfg.get("private_key", "")
        if not pk.startswith("0x"):
            pk = "0x" + pk
        self.acct = self.w3.eth.account.from_key(pk)
        self.me = self.acct.address
        self.me_lc = self.me.lower()
        self.addr_bytes = bytes.fromhex(self.me[2:])
        self.contract_addr = Web3.to_checksum_address(cfg.get("contract_address", CONTRACT_ADDRESS))
        self.chain_id = int(cfg.get("chain_id", 56))
        self.gas_limit = int(cfg.get("gas_limit", 200000))
        self.c = self.w3.eth.contract(address=self.contract_addr, abi=CONTRACT_ABI)

        # 状态
        self.target = self.c.functions.miningTarget().call()
        self.difficulty = self.c.functions.getMiningDifficulty().call()
        self.gas_wei = gas_price_wei(self.w3, cfg)
        self.nonce = self.w3.eth.get_transaction_count(self.me, "pending")
        self.nlock = threading.Lock()
        self.last_fired_challenge = None
        self.last_fire_ts = 0.0

        # 统计
        self.sent = 0
        self.won = 0
        self.lost = 0
        self.fired_challenges = set()
        self.start_time = time.time()

        # 求解器
        self.mode = str(cfg.get("solver", "cpu")).lower()
        if self.mode not in ("cpu", "gpu"):
            self.mode = "cpu"
        self.gpu = None
        self.pool = None
        self.cur_gen = 0
        self.gen_meta = {}
        self.fired_gen = -1
        self.submitted_gen = -1

        if self.mode == "gpu":
            try:
                self.gpu = GpuSolver(cfg)
                self.on_log(f"求解器: GPU {self.gpu.name}  占用 {self.gpu.util:.0f}%")
            except Exception as e:
                self.on_log(f"GPU 不可用, 退回 CPU 热池: {str(e)[:70]}")
                self.mode = "cpu"
        if self.mode == "cpu":
            self.pool = CpuPool(cfg)
            self.on_log(f"求解器: CPU 热池 ({self.pool.n} 进程, 常驻预热)")

        self.bc = None if self.dry else Broadcaster(cfg.get("relay_urls") or DEFAULT_RELAYS)

    def start(self):
        self.running = True
        # 后台刷新线程
        threading.Thread(target=self._refresh_loop, daemon=True).start()
        # 统计线程
        threading.Thread(target=self._stats_loop, daemon=True).start()
        # CPU 收集线程
        if self.mode == "cpu":
            threading.Thread(target=self._collector, daemon=True).start()
        # 启动时先为当前挑战号算一发
        try:
            cur = self.c.functions.challengeNumber().call().hex()
            cur = cur if cur.startswith("0x") else "0x" + cur
            self.set_challenge(cur)
        except Exception:
            pass
        # WebSocket 检测线程
        threading.Thread(target=self._ws_thread, daemon=True).start()

    def stop(self):
        self.running = False
        if self.pool:
            self.pool.shutdown()

    def set_challenge(self, challenge_hex):
        ch = bytes.fromhex(challenge_hex[2:] if challenge_hex.startswith("0x") else challenge_hex)
        if ch in self.fired_challenges:
            return
        with self.nlock:
            self.cur_gen += 1
            gen = self.cur_gen
        self.gen_meta[gen] = (ch, time.perf_counter())
        self.last_fired_challenge = ch
        prefix = ch + self.addr_bytes
        base = random.getrandbits(64)
        if self.mode == "cpu":
            self.pool.set_challenge(prefix, self.target, gen, base)
        else:
            threading.Thread(target=self._gpu_solve, args=(gen, ch, prefix, base),
                             daemon=True).start()

    def _gpu_solve(self, gen, ch, prefix, base):
        tb = self.target.to_bytes(32, "big")
        n = base & ((1 << 48) - 1)
        while self.running and gen == self.cur_gen:
            win = self.gpu.gpu.search(prefix, tb, n, self.gpu.batch)
            if win is not None:
                k = _pycryptodome_keccak.new(digest_bits=256)
                k.update(prefix + int(win).to_bytes(32, "big"))
                d = k.digest()
                if int.from_bytes(d, "big") <= self.target:
                    self._submit_solution(gen, int(win), d)
                    return
            n += self.gpu.batch

    def _collector(self):
        while self.running:
            try:
                gen, nonce, digest = self.pool.result_q.get(timeout=1.0)
            except Exception:
                continue
            self._submit_solution(gen, nonce, digest)

    def _submit_solution(self, gen, nonce_v, digest):
        if gen != self.cur_gen or gen == self.fired_gen:
            return
        meta = self.gen_meta.get(gen)
        if meta is None:
            return
        ch, t0 = meta
        self.fired_gen = gen

        with self.nlock:
            tx_nonce = self.nonce
            self.nonce += 1
        calldata = ("0x" + MINT_SELECTOR
                    + nonce_v.to_bytes(32, "big").hex() + digest.hex())
        tx = {"to": self.contract_addr, "value": 0, "data": calldata,
              "gas": self.gas_limit, "gasPrice": self.gas_wei,
              "nonce": tx_nonce, "chainId": self.chain_id}
        signed = self.acct.sign_transaction(tx)
        raw_hex = signed.raw_transaction.hex()
        if not raw_hex.startswith("0x"):
            raw_hex = "0x" + raw_hex
        solve_ms = (time.perf_counter() - t0) * 1000

        self.fired_challenges.add(ch)
        self.last_fire_ts = time.time()

        if self.dry:
            self.on_log(f"[DRY] 挑战 {ch.hex()[:12]}.. 解出 nonce={nonce_v} "
                        f"算解+签 {solve_ms:.1f}ms (未广播)")
            return

        if gen != self.cur_gen:
            with self.nlock:
                self.nonce = min(self.nonce, tx_nonce)
            return
        results = self.bc.broadcast(raw_hex)
        self.sent += 1
        oks = [r for r in results if r[1]]
        if oks:
            self.submitted_gen = gen
        if self.verbose:
            best = min((r[2] for r in oks), default=None)
            total_ms = (time.perf_counter() - t0) * 1000
            tag = f"解+签+广播 {best:.0f}ms" if best else "广播全失败"
            self.on_log(f"→ 发出 挑战 {ch.hex()[:12]}.. nonce={tx_nonce} "
                        f"接受 {len(oks)}/{len(results)} 路  端到端 {total_ms:.0f}ms ({tag})")
        if not oks:
            with self.nlock:
                self.nonce = min(self.nonce, tx_nonce)

    def on_mint(self, log_obj):
        data = log_obj["data"]
        data = data.hex() if hasattr(data, "hex") else data
        data = data[2:] if data.startswith("0x") else data
        epoch = int(data[64:128], 16)
        new_challenge = "0x" + data[128:192]
        frm = log_obj["topics"][1]
        frm = frm.hex() if hasattr(frm, "hex") else frm
        frm = frm[2:] if frm.startswith("0x") else frm
        frm_addr = "0x" + frm[-40:]
        won = frm_addr.lower() == self.me_lc
        resolved_gen = self.cur_gen
        did_submit = (self.submitted_gen == resolved_gen and resolved_gen != 0)
        if won:
            self.won += 1
            self.on_log(f"✓ 成功 mint!  第 {self.won} 块  epoch={epoch}")
            self.on_win(epoch)
        elif did_submit:
            self.lost += 1
            self.on_log(f"✗ 失败 (被抢先)  累计 成功 {self.won} / 失败 {self.lost}")
            self.on_lose()
        self.set_challenge(new_challenge)

    def fetch_block_mint(self, block_num):
        try:
            logs = self.w3.eth.get_logs({
                "address": self.contract_addr, "topics": [MINT_TOPIC],
                "fromBlock": block_num, "toBlock": block_num})
            return logs[-1] if logs else None
        except Exception:
            return None

    def _refresh_loop(self):
        while self.running:
            time.sleep(10)
            try:
                d = self.c.functions.getMiningDifficulty().call()
                if d != self.difficulty:
                    self.target = self.c.functions.miningTarget().call()
                    self.on_log(f"难度变化 {self.difficulty} -> {d}")
                    self.difficulty = d
            except Exception:
                pass
            try:
                self.gas_wei = gas_price_wei(self.w3, self.cfg)
            except Exception:
                pass
            if time.time() - self.last_fire_ts > 3:
                try:
                    chain_n = self.w3.eth.get_transaction_count(self.me, "pending")
                    with self.nlock:
                        if chain_n != self.nonce:
                            self.nonce = chain_n
                except Exception:
                    pass

    def _stats_loop(self):
        while self.running:
            time.sleep(15)
            el = time.time() - self.start_time
            settled = self.won + self.lost
            wr = (self.won / settled * 100) if settled else 0
            stats = {
                "elapsed": el, "sent": self.sent, "won": self.won,
                "lost": self.lost, "win_rate": wr, "difficulty": self.difficulty,
                "mode": self.mode.upper(),
            }
            self.on_stats(stats)
            if self.verbose:
                self.on_log(f"── 统计 运行 {el:.0f}s  发出 {self.sent}  赢 {self.won}  "
                            f"输 {self.lost}  胜率 {wr:.0f}%  难度 {self.difficulty}  "
                            f"模式 {self.mode.upper()}")

    # ── WebSocket 检测层 ──

    def _ws_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._detect())
        except Exception:
            pass

    async def _detect(self):
        mode = str(self.cfg.get("detect_mode", "auto")).lower()
        head_ws = self.cfg.get("head_ws") or DEFAULT_HEAD_WS
        if mode in ("logs", "auto"):
            ok = await self._logs_loop(self.cfg.get("ws_urls") or DEFAULT_WS)
            if ok or mode == "logs" or not self.running:
                return
            self.on_log("logs-WS 连续失败, 自动切到 heads 模式")
        await self._heads_loop(head_ws)

    async def _logs_loop(self, urls):
        if not HAS_WS:
            self.on_log("websockets 未安装, 无法使用 logs 模式")
            return False
        flt = {"address": self.contract_addr.lower(), "topics": [MINT_TOPIC]}
        fails = 0
        i = 0
        while self.running:
            url = urls[i % len(urls)]
            i += 1
            try:
                async with websockets.connect(url, open_timeout=10, ping_interval=None,
                                              max_size=None) as ws:
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1,
                        "method": "eth_subscribe", "params": ["logs", flt]}))
                    sub = json.loads(await asyncio.wait_for(ws.recv(), 10))
                    if "result" not in sub:
                        raise RuntimeError(str(sub.get("error", sub))[:60])
                    self.on_log(f"WS 监听已连接 (logs @ {url})")
                    fails = 0
                    while self.running:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 90))
                        p = m.get("params", {}).get("result")
                        if p:
                            self.on_mint(p)
            except Exception as e:
                if not self.running:
                    break
                fails += 1
                if self.verbose:
                    self.on_log(f"logs-WS 失败 ({url}): {type(e).__name__} {str(e)[:50]}")
                if fails >= 3:
                    return False
                await asyncio.sleep(2)
        return True

    async def _heads_loop(self, head_ws):
        if not HAS_WS:
            self.on_log("websockets 未安装, 无法使用 heads 模式, 退回轮询")
            await self._poll_fallback()
            return
        loop = asyncio.get_event_loop()
        last_block = 0
        while self.running:
            try:
                async with websockets.connect(head_ws, open_timeout=10, ping_interval=None,
                                              max_size=None) as ws:
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1,
                        "method": "eth_subscribe", "params": ["newHeads"]}))
                    sub = json.loads(await asyncio.wait_for(ws.recv(), 10))
                    if "result" not in sub:
                        raise RuntimeError(str(sub.get("error", sub))[:60])
                    self.on_log(f"WS 监听已连接 (heads @ {head_ws})")
                    while self.running:
                        m = json.loads(await asyncio.wait_for(ws.recv(), 90))
                        p = m.get("params", {}).get("result")
                        if not p:
                            continue
                        bn = int(p["number"], 16)
                        if bn <= last_block:
                            continue
                        last_block = bn
                        lg = await loop.run_in_executor(None, self.fetch_block_mint, bn)
                        if lg:
                            self.on_mint(lg)
            except Exception as e:
                if not self.running:
                    break
                if self.verbose:
                    self.on_log(f"heads-WS 断开: {type(e).__name__} {str(e)[:50]} — 2s 重连")
                await asyncio.sleep(2)

    async def _poll_fallback(self):
        """无 websockets 时的轮询兜底"""
        self.on_log("使用轮询模式检测新挑战号 (建议安装 websockets 以获得更快检测)")
        last_challenge = None
        while self.running:
            try:
                ch = self.c.functions.challengeNumber().call()
                ch_hex = "0x" + ch.hex()
                if last_challenge is not None and ch != last_challenge:
                    self.set_challenge(ch_hex)
                last_challenge = ch
            except Exception:
                pass
            await asyncio.sleep(3)


# ─── Bitcoin 风格配色 ────────────────────────────────────────────────────────

COLORS = {
    'bg':           '#0d1117',
    'bg_card':      '#161b22',
    'bg_card2':     '#1c2333',
    'bg_input':     '#0d1117',
    'bg_hover':     '#21262d',
    'accent':       '#f7931a',
    'accent_dark':  '#e8850f',
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

# ─── 国际化 ──────────────────────────────────────────────────────────────────

LANG = {
    'en': {
        'title': 'Satoshi Miner',
        'subtitle': 'BSC PoW Reactive Mining',
        'tab_wallet': 'Wallet',
        'tab_mine': 'Mine',
        'tab_history': 'History',
        'tab_settings': 'Settings',
        'connection': 'Connection',
        'rpc_url': 'RPC Endpoint',
        'private_key': 'Private Key',
        'show': 'Show', 'hide': 'Hide',
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
        'time': 'Time', 'nonce': 'Nonce', 'reward': 'Reward',
        'tx_hash': 'TX Hash', 'status': 'Status',
        'gas_settings': 'Gas Settings',
        'gas_price': 'Gas Price (Gwei)',
        'gas_limit': 'Gas Limit',
        'contract': 'Contract Address',
        'save_settings': 'Save Settings',
        'about': 'About',
        'about_text': (
            "Satoshi (SAT) PoW Miner v3.0 — Reactive Mining Edition\n"
            "Features: WS Mint event detection, GPU/CPU solver,\n"
            "multi-relay broadcast, floor gas price tracking.\n"
            "Total Supply: 21,000,000 SAT (8 decimals)\n"
            "Mining: keccak256(challenge, address, nonce) <= target"
        ),
        'not_connected': 'Disconnected',
        'connected': 'Connected',
        'network': 'Network',
        'max_supply': 'Max Supply',
        'halving': 'Halving',
        'every_era': 'Every Era',
        'contract_info': 'Contract Info',
        'success': 'Success', 'failed': 'Failed', 'error': 'Error',
        'no_history': 'No mining history yet',
        'mining_started': 'Reactive mining started...',
        'mining_stopped': 'Mining stopped',
        'connect_first': 'Please connect wallet first',
        'enter_rpc': 'Please enter RPC URL',
        'enter_pk': 'Please enter private key',
        'conn_failed': 'Connection failed',
        'settings_saved': 'Settings saved',
        'copy': 'Copy', 'copied': 'Copied!',
        'mining_active': 'MINING ACTIVE',
        'mining_idle': 'IDLE',
        'total_hashes': 'Total Hashes',
        'avg_hashrate': 'Avg Hashrate',
        'history_title': 'Mining History',
        'no_records': 'No records yet. Start mining to see results here.',
        'save_pk': 'Save Private Key Locally',
        'save_pk_tip': '(Base64 obfuscated, not plaintext)',
        'solver_mode': 'Solver Mode',
        'ws_status': 'WS Status',
        'relay_count': 'Relay Nodes',
        'win_rate': 'Win Rate',
        'sent_count': 'TX Sent',
        'won_count': 'Won',
        'lost_count': 'Lost',
    },
    'zh': {
        'title': 'Satoshi 矿机',
        'subtitle': 'BSC PoW 反应式挖矿',
        'tab_wallet': '钱包',
        'tab_mine': '挖矿',
        'tab_history': '记录',
        'tab_settings': '设置',
        'connection': '连接设置',
        'rpc_url': 'RPC 节点',
        'private_key': '私钥',
        'show': '显示', 'hide': '隐藏',
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
        'time': '时间', 'nonce': 'Nonce', 'reward': '奖励',
        'tx_hash': '交易哈希', 'status': '状态',
        'gas_settings': 'Gas 设置',
        'gas_price': 'Gas 价格 (Gwei)',
        'gas_limit': 'Gas 上限',
        'contract': '合约地址',
        'save_settings': '保存设置',
        'about': '关于',
        'about_text': (
            "Satoshi (SAT) PoW 矿机 v3.0 — 反应式挖矿版\n"
            "特性：WS Mint 事件检测、GPU/CPU 求解器、\n"
            "多 relay 并行广播、Gas 跟网络地板价。\n"
            "总供应量：21,000,000 SAT（8位小数）\n"
            "挖矿：keccak256(challenge, address, nonce) <= target"
        ),
        'not_connected': '未连接',
        'connected': '已连接',
        'network': '网络',
        'max_supply': '最大供应量',
        'halving': '减半',
        'every_era': '每个时代',
        'contract_info': '合约信息',
        'success': '成功', 'failed': '失败', 'error': '错误',
        'no_history': '暂无挖矿记录',
        'mining_started': '反应式挖矿已开始...',
        'mining_stopped': '挖矿已停止',
        'connect_first': '请先连接钱包',
        'enter_rpc': '请输入 RPC 地址',
        'enter_pk': '请输入私钥',
        'conn_failed': '连接失败',
        'settings_saved': '设置已保存',
        'copy': '复制', 'copied': '已复制!',
        'mining_active': '挖矿中',
        'mining_idle': '空闲',
        'total_hashes': '总哈希数',
        'avg_hashrate': '平均算力',
        'history_title': '挖矿记录',
        'no_records': '暂无记录。开始挖矿后将在此显示结果。',
        'save_pk': '保存私钥到本地',
        'save_pk_tip': '(Base64 混淆存储，非明文)',
        'solver_mode': '求解模式',
        'ws_status': 'WS 状态',
        'relay_count': 'Relay 节点',
        'win_rate': '胜率',
        'sent_count': '已发送',
        'won_count': '成功',
        'lost_count': '失败',
    }
}

# ─── Icon 加载 ───────────────────────────────────────────────────────────────

def get_icon_path():
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, 'icon_circle.png')


# ─── GUI 主程序 ──────────────────────────────────────────────────────────────

class SatoshiMinerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Satoshi Miner v3.0")
        self.root.geometry("980x780")
        self.root.minsize(880, 680)
        self.root.configure(bg=COLORS['bg'])

        self.w3 = None
        self.contract = None
        self.account = None
        self.miner = None
        self.multicall = None
        self.mining = False
        self.history = []
        self.cur_lang = 'zh'
        self.i18n_widgets = []
        self.start_time = None
        self.logo_img = None
        self.logo_img_small = None
        self.yaml_cfg = load_yaml_config()

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

    def _load_logo(self):
        if not HAS_PIL:
            return
        try:
            icon_path = get_icon_path()
            if os.path.exists(icon_path):
                img = Image.open(icon_path).convert("RGBA")
                logo_large = img.resize((42, 42), Image.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(logo_large)
                logo_small = img.resize((24, 24), Image.LANCZOS)
                self.logo_img_small = ImageTk.PhotoImage(logo_small)
        except:
            pass

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

    @staticmethod
    def _obfuscate_key(pk):
        if not pk: return ""
        return base64.b64encode(pk.encode('utf-8')).decode('utf-8')

    @staticmethod
    def _deobfuscate_key(obf):
        if not obf: return ""
        try:
            return base64.b64decode(obf.encode('utf-8')).decode('utf-8')
        except Exception:
            return obf

    def _load_config(self):
        self.config = {"rpc": DEFAULT_RPC, "gas_price": "0.1", "gas_limit": "200000",
                        "private_key_saved": "", "save_private_key": False}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE) as f:
                    self.config.update(json.load(f))
            except:
                pass

    def _save_config(self):
        pk_to_save = ""
        save_pk = self.save_pk_var.get() if hasattr(self, 'save_pk_var') else False
        if save_pk and hasattr(self, 'pk_var'):
            pk_to_save = self._obfuscate_key(self.pk_var.get().strip())
        to_save = {
            "rpc": self.rpc_var.get(),
            "gas_price": self.gas_price_var.get(),
            "gas_limit": self.gas_limit_var.get(),
            "save_private_key": save_pk,
            "private_key_saved": pk_to_save,
        }
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
        self.main_container = tk.Frame(self.root, bg=COLORS['bg'])
        self.main_container.pack(fill='both', expand=True)
        self._build_sidebar()
        self._build_content_area()
        self._build_panels()
        self._show_panel('wallet')

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.main_container, bg=COLORS['bg_card'], width=220)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)

        logo_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=20, padx=16)
        logo_frame.pack(fill='x')
        logo_row = tk.Frame(logo_frame, bg=COLORS['bg_card'])
        logo_row.pack(anchor='center')
        if self.logo_img:
            tk.Label(logo_row, image=self.logo_img, bg=COLORS['bg_card']).pack(side='left', padx=(0, 10))
        title_col = tk.Frame(logo_row, bg=COLORS['bg_card'])
        title_col.pack(side='left')
        title_lbl = tk.Label(title_col, text=self.t('title'), font=('Segoe UI', 14, 'bold'),
                              fg=COLORS['white'], bg=COLORS['bg_card'])
        title_lbl.pack(anchor='w')
        self._register_i18n(title_lbl, 'title')
        subtitle_lbl = tk.Label(title_col, text=self.t('subtitle'), font=('Segoe UI', 8),
                                 fg=COLORS['text3'], bg=COLORS['bg_card'])
        subtitle_lbl.pack(anchor='w')
        self._register_i18n(subtitle_lbl, 'subtitle')

        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        self.status_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], padx=16, pady=12)
        self.status_frame.pack(fill='x')
        status_row = tk.Frame(self.status_frame, bg=COLORS['bg_card'])
        status_row.pack(fill='x')
        self.status_dot = tk.Canvas(status_row, width=10, height=10, bg=COLORS['bg_card'],
                                     highlightthickness=0)
        self.status_dot.pack(side='left', padx=(0, 8))
        self.status_dot.create_oval(1, 1, 9, 9, fill=COLORS['red_dim'], outline='')
        self.status_label = tk.Label(status_row, text=self.t('not_connected'),
                                      font=('Segoe UI', 9), fg=COLORS['text2'], bg=COLORS['bg_card'])
        self.status_label.pack(side='left')

        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)

        nav_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=8)
        nav_frame.pack(fill='x')
        self.tab_buttons = {}
        tabs = [('wallet', 'tab_wallet', '\u229a'), ('mine', 'tab_mine', '\u26cf'),
                ('history', 'tab_history', '\u2630'), ('settings', 'tab_settings', '\u2699')]
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
            for widget in (btn_frame, icon_lbl, text_lbl):
                widget.bind('<Button-1>', lambda e, t=tab_id: self._show_panel(t))
                widget.bind('<Enter>', lambda e, bf=btn_frame, il=icon_lbl, tl=text_lbl, t=tab_id:
                            self._on_tab_hover(t, bf, il, tl, True))
                widget.bind('<Leave>', lambda e, bf=btn_frame, il=icon_lbl, tl=text_lbl, t=tab_id:
                            self._on_tab_hover(t, bf, il, tl, False))

        spacer = tk.Frame(self.sidebar, bg=COLORS['bg_card'])
        spacer.pack(fill='both', expand=True)
        tk.Frame(self.sidebar, bg=COLORS['border'], height=1).pack(fill='x', padx=16)
        bottom_frame = tk.Frame(self.sidebar, bg=COLORS['bg_card'], pady=12, padx=16)
        bottom_frame.pack(fill='x', side='bottom')
        self.lang_btn = tk.Button(bottom_frame, text='EN', font=('Segoe UI', 9, 'bold'),
                                   bg=COLORS['bg_card2'], fg=COLORS['text2'],
                                   activebackground=COLORS['bg_hover'], activeforeground=COLORS['accent'],
                                   relief='flat', padx=12, pady=4, cursor='hand2', bd=0,
                                   command=self._toggle_lang)
        self.lang_btn.pack(side='left')
        tk.Label(bottom_frame, text='v3.0', font=('Segoe UI', 8),
                 fg=COLORS['text3'], bg=COLORS['bg_card']).pack(side='right')

    def _on_tab_hover(self, tab_id, btn_frame, icon_lbl, text_lbl, entering):
        if hasattr(self, '_active_tab') and self._active_tab == tab_id:
            return
        bg = COLORS['bg_hover'] if entering else COLORS['bg_card']
        for w in (btn_frame, icon_lbl, text_lbl):
            w.config(bg=bg)

    def _build_content_area(self):
        self.content_area = tk.Frame(self.main_container, bg=COLORS['bg'])
        self.content_area.pack(side='left', fill='both', expand=True)
        topbar = tk.Frame(self.content_area, bg=COLORS['bg'], pady=12, padx=24)
        topbar.pack(fill='x')
        self.page_title = tk.Label(topbar, text='', font=('Segoe UI', 18, 'bold'),
                                    fg=COLORS['white'], bg=COLORS['bg'])
        self.page_title.pack(side='left')
        self.mining_status_label = tk.Label(topbar, text=self.t('mining_idle'),
                                             font=('Segoe UI', 9, 'bold'),
                                             fg=COLORS['text3'], bg=COLORS['bg_card2'], padx=12, pady=4)
        self.mining_status_label.pack(side='right')
        tk.Frame(self.content_area, bg=COLORS['border'], height=1).pack(fill='x')
        self.content_frame = tk.Frame(self.content_area, bg=COLORS['bg'])
        self.content_frame.pack(fill='both', expand=True)

    def _show_panel(self, name):
        self._active_tab = name
        for tid, (bf, il, tl) in self.tab_buttons.items():
            if tid == name:
                bf.config(bg=COLORS['bg_card2'])
                il.config(fg=COLORS['accent'], bg=bf.cget('bg'))
                tl.config(fg=COLORS['white'], bg=bf.cget('bg'), font=('Segoe UI', 11, 'bold'))
            else:
                bf.config(bg=COLORS['bg_card'])
                il.config(fg=COLORS['text3'], bg=COLORS['bg_card'])
                tl.config(fg=COLORS['text2'], bg=COLORS['bg_card'], font=('Segoe UI', 11))
        title_map = {'wallet': 'tab_wallet', 'mine': 'tab_mine',
                     'history': 'tab_history', 'settings': 'tab_settings'}
        self.page_title.config(text=self.t(title_map.get(name, name)))
        for child in self.content_frame.winfo_children():
            child.pack_forget()
        if hasattr(self, 'panels') and name in self.panels:
            self.panels[name].pack(fill='both', expand=True)
        if name == 'history':
            self._populate_history()

    def _build_panels(self):
        self.panels = {}
        self._build_wallet_panel()
        self._build_mine_panel()
        self._build_history_panel()
        self._build_settings_panel()

    def _make_scrollable_panel(self, parent_frame):
        canvas = tk.Canvas(parent_frame, bg=COLORS['bg'], highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(parent_frame, orient='vertical', command=canvas.yview,
                                  bg=COLORS['bg_card2'], troughcolor=COLORS['bg'])
        content = tk.Frame(canvas, bg=COLORS['bg'])
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas_window = canvas.create_window((0, 0), window=content, anchor='nw')
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width - 2)
        canvas.bind('<Configure>', _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        def _bind_wheel(event):
            canvas.bind_all('<MouseWheel>', lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))
        def _unbind_wheel(event):
            canvas.unbind_all('<MouseWheel>')
        canvas.bind('<Enter>', _bind_wheel)
        canvas.bind('<Leave>', _unbind_wheel)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        return canvas, content

    def _make_card(self, parent):
        return tk.Frame(parent, bg=COLORS['bg_card'], padx=20, pady=16,
                         highlightbackground=COLORS['border'], highlightthickness=1)

    def _make_separator(self, parent):
        tk.Frame(parent, bg=COLORS['border'], height=1).pack(fill='x', pady=(10, 12))

    def _make_entry(self, parent, **kwargs):
        return tk.Entry(parent, bg=COLORS['bg_input'], fg=COLORS['text'],
                          insertbackground=COLORS['accent'], relief='flat',
                          font=('Consolas', 11), highlightthickness=1,
                          highlightcolor=COLORS['accent'],
                          highlightbackground=COLORS['border'], **kwargs)

    def _make_accent_btn(self, parent, text='', command=None):
        btn = tk.Button(parent, text=text, command=command,
                         bg=COLORS['accent'], fg=COLORS['black'],
                         activebackground=COLORS['accent_dark'], activeforeground=COLORS['black'],
                         font=('Segoe UI', 12, 'bold'), relief='flat', cursor='hand2', bd=0)
        btn.bind('<Enter>', lambda e: btn.config(bg=COLORS['accent_dark']))
        btn.bind('<Leave>', lambda e: btn.config(bg=COLORS['accent']))
        return btn

    # ── WALLET PANEL ──

    def _build_wallet_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['wallet'] = panel
        canvas, content = self._make_scrollable_panel(panel)
        pad = {'padx': 24, 'pady': (0, 16)}

        # Connection Card
        conn_card = self._make_card(content)
        conn_card.pack(fill='x', padx=24, pady=(16, 16))
        conn_header = tk.Frame(conn_card, bg=COLORS['bg_card'])
        conn_header.pack(fill='x')
        tk.Label(conn_header, text='\u26a1', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        conn_title = tk.Label(conn_header, text=self.t('connection'),
                               font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        conn_title.pack(side='left')
        self._register_i18n(conn_title, 'connection')
        self._make_separator(conn_card)

        rpc_lbl = tk.Label(conn_card, text=self.t('rpc_url'), font=('Segoe UI', 9, 'bold'),
                            fg=COLORS['text2'], bg=COLORS['bg_card'])
        rpc_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(rpc_lbl, 'rpc_url')
        self.rpc_var = tk.StringVar(value=self.config['rpc'])
        self._make_entry(conn_card, textvariable=self.rpc_var).pack(fill='x', pady=(0, 12), ipady=8)

        pk_lbl = tk.Label(conn_card, text=self.t('private_key'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        pk_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(pk_lbl, 'private_key')
        pk_row = tk.Frame(conn_card, bg=COLORS['bg_card'])
        pk_row.pack(fill='x', pady=(0, 16))
        self.pk_var = tk.StringVar()
        # 优先从 yaml 配置读取私钥
        yaml_pk = self.yaml_cfg.get("private_key", "")
        if yaml_pk:
            self.pk_var.set(yaml_pk)
        elif self.config.get('save_private_key') and self.config.get('private_key_saved'):
            self.pk_var.set(self._deobfuscate_key(self.config['private_key_saved']))
        self.pk_entry = self._make_entry(pk_row, textvariable=self.pk_var, show='*')
        self.pk_entry.pack(side='left', fill='x', expand=True, ipady=8)
        self.show_pk_var = tk.BooleanVar(value=False)
        show_btn = tk.Button(pk_row, text=self.t('show'), font=('Segoe UI', 9),
                              bg=COLORS['bg_card2'], fg=COLORS['text2'],
                              activebackground=COLORS['bg_hover'], relief='flat',
                              padx=12, cursor='hand2', bd=0, command=self._toggle_pk)
        show_btn.pack(side='left', padx=(8, 0), ipady=8)

        save_pk_row = tk.Frame(conn_card, bg=COLORS['bg_card'])
        save_pk_row.pack(fill='x', pady=(0, 12))
        self.save_pk_var = tk.BooleanVar(value=self.config.get('save_private_key', False))
        tk.Checkbutton(save_pk_row, text=self.t('save_pk'), variable=self.save_pk_var,
                        font=('Segoe UI', 9), fg=COLORS['text2'], bg=COLORS['bg_card'],
                        selectcolor=COLORS['bg_input'], activebackground=COLORS['bg_card'],
                        highlightthickness=0, bd=0, cursor='hand2').pack(side='left')

        self.connect_btn = self._make_accent_btn(conn_card, text=self.t('connect'), command=self._connect)
        self.connect_btn.pack(fill='x', ipady=6)
        self._register_i18n(self.connect_btn, 'connect')

        # Balance Card
        balance_card = self._make_card(content)
        balance_card.pack(fill='x', **pad)
        bal_header = tk.Frame(balance_card, bg=COLORS['bg_card'])
        bal_header.pack(fill='x')
        if self.logo_img_small:
            tk.Label(bal_header, image=self.logo_img_small, bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        bal_title = tk.Label(bal_header, text=self.t('wallet_overview'),
                              font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        bal_title.pack(side='left')
        self._register_i18n(bal_title, 'wallet_overview')
        refresh_btn = tk.Button(bal_header, text=self.t('refresh'), font=('Segoe UI', 9),
                                 bg=COLORS['bg_card2'], fg=COLORS['text2'],
                                 activebackground=COLORS['bg_hover'], relief='flat',
                                 padx=10, pady=2, cursor='hand2', bd=0, command=self._refresh_info)
        refresh_btn.pack(side='right')
        self._register_i18n(refresh_btn, 'refresh')
        self._make_separator(balance_card)

        self.main_balance_frame = tk.Frame(balance_card, bg=COLORS['bg_card'], pady=8)
        self.main_balance_frame.pack(fill='x')
        tk.Label(self.main_balance_frame, text='₿', font=('Segoe UI', 28),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        bal_col = tk.Frame(self.main_balance_frame, bg=COLORS['bg_card'])
        bal_col.pack(side='left')
        self.big_balance_label = tk.Label(bal_col, text='0.00000000 SAT',
                                           font=('Segoe UI', 24, 'bold'),
                                           fg=COLORS['white'], bg=COLORS['bg_card'])
        self.big_balance_label.pack(anchor='w')
        self.address_label = tk.Label(bal_col, text='--', font=('Consolas', 10),
                                       fg=COLORS['text3'], bg=COLORS['bg_card'])
        self.address_label.pack(anchor='w')
        self._make_separator(balance_card)

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
        canvas, content = self._make_scrollable_panel(panel)

        ctrl_card = self._make_card(content)
        ctrl_card.pack(fill='x', padx=24, pady=(16, 16))
        ctrl_header = tk.Frame(ctrl_card, bg=COLORS['bg_card'])
        ctrl_header.pack(fill='x')
        tk.Label(ctrl_header, text='\u26cf', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        ctrl_title = tk.Label(ctrl_header, text=self.t('mining_dashboard'),
                               font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        ctrl_title.pack(side='left')
        self._register_i18n(ctrl_title, 'mining_dashboard')
        self._make_separator(ctrl_card)

        self.mine_btn = tk.Button(ctrl_card, text=self.t('start_mining'),
                                   font=('Segoe UI', 14, 'bold'),
                                   bg=COLORS['accent'], fg=COLORS['black'],
                                   activebackground=COLORS['accent_dark'],
                                   relief='flat', cursor='hand2', bd=0,
                                   command=self._toggle_mining)
        self.mine_btn.pack(fill='x', ipady=12)

        # Stats row
        stats_row = tk.Frame(ctrl_card, bg=COLORS['bg_card'])
        stats_row.pack(fill='x', pady=(16, 0))
        mining_stats = [
            ('solver_mode', 'CPU', COLORS['blue']),
            ('won_count', '0', COLORS['green']),
            ('lost_count', '0', COLORS['red']),
            ('sent_count', '0', COLORS['accent']),
            ('win_rate', '0%', COLORS['purple']),
        ]
        self.mining_stat_labels = {}
        for i, (key, default, color) in enumerate(mining_stats):
            cell = tk.Frame(stats_row, bg=COLORS['bg_card2'], padx=10, pady=8)
            cell.pack(side='left', fill='x', expand=True,
                      padx=(0 if i == 0 else 3, 3 if i < len(mining_stats)-1 else 0))
            lbl = tk.Label(cell, text=self.t(key).upper(), font=('Segoe UI', 7, 'bold'),
                           fg=COLORS['text3'], bg=COLORS['bg_card2'])
            lbl.pack(anchor='w')
            self._register_i18n(lbl, key)
            val_lbl = tk.Label(cell, text=default, font=('Segoe UI', 13, 'bold'),
                               fg=color, bg=COLORS['bg_card2'])
            val_lbl.pack(anchor='w', pady=(2, 0))
            self.mining_stat_labels[key] = val_lbl

        # Mining Log
        log_card = self._make_card(content)
        log_card.pack(fill='x', padx=24, pady=(0, 16))
        log_header = tk.Frame(log_card, bg=COLORS['bg_card'])
        log_header.pack(fill='x')
        tk.Label(log_header, text='\u2630', font=('Segoe UI', 13),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        log_title = tk.Label(log_header, text=self.t('mining_log'),
                              font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
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
            highlightcolor=COLORS['border'], highlightbackground=COLORS['border'])
        self.log_text.pack(fill='both', expand=True)

    # ── HISTORY PANEL ──

    def _build_history_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['history'] = panel
        header_card = self._make_card(panel)
        header_card.pack(fill='x', padx=24, pady=(16, 0))
        h_header = tk.Frame(header_card, bg=COLORS['bg_card'])
        h_header.pack(fill='x')
        tk.Label(h_header, text='\u2630', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        h_title = tk.Label(h_header, text=self.t('history_title'),
                            font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        h_title.pack(side='left')
        self._register_i18n(h_title, 'history_title')

        col_frame = tk.Frame(panel, bg=COLORS['bg_card2'], padx=24, pady=10)
        col_frame.pack(fill='x', padx=24, pady=(12, 2))
        cols = [('time', 16), ('nonce', 14), ('reward', 14), ('tx_hash', 22), ('status', 8)]
        for key, w in cols:
            lbl = tk.Label(col_frame, text=self.t(key).upper(), font=('Segoe UI', 8, 'bold'),
                           fg=COLORS['accent'], bg=COLORS['bg_card2'], width=w, anchor='w')
            lbl.pack(side='left', padx=2)
            self._register_i18n(lbl, key)

        h_canvas = tk.Canvas(panel, bg=COLORS['bg'], highlightthickness=0, bd=0)
        h_scroll = tk.Scrollbar(panel, orient='vertical', command=h_canvas.yview,
                                 bg=COLORS['bg_card2'], troughcolor=COLORS['bg'])
        self.history_list_frame = tk.Frame(h_canvas, bg=COLORS['bg'])
        self.history_list_frame.bind('<Configure>',
                                      lambda e: h_canvas.configure(scrollregion=h_canvas.bbox('all')))
        h_canvas_window = h_canvas.create_window((0, 0), window=self.history_list_frame, anchor='nw')
        h_canvas.configure(yscrollcommand=h_scroll.set)
        def _on_h(event): h_canvas.itemconfig(h_canvas_window, width=event.width)
        h_canvas.bind('<Configure>', _on_h)
        h_canvas.pack(side='left', fill='both', expand=True, padx=(24, 0), pady=(0, 16))
        h_scroll.pack(side='right', fill='y', padx=(0, 24), pady=(0, 16))
        self._populate_history()

    def _populate_history(self):
        for w in self.history_list_frame.winfo_children():
            w.destroy()
        if not self.history:
            tk.Label(self.history_list_frame, text=self.t('no_records'),
                     font=('Segoe UI', 11), fg=COLORS['text3'], bg=COLORS['bg'], pady=40).pack()
            return
        for entry in reversed(self.history):
            self._add_history_row(entry, prepend=False)

    def _add_history_row(self, entry, prepend=True):
        bg = COLORS['bg_card']
        row = tk.Frame(self.history_list_frame, bg=bg, padx=24, pady=8)
        if prepend:
            for c in self.history_list_frame.winfo_children():
                if isinstance(c, tk.Label): c.destroy()
            existing = self.history_list_frame.winfo_children()
            if existing:
                row.pack(fill='x', pady=1, before=existing[0])
            else:
                row.pack(fill='x', pady=1)
        else:
            row.pack(fill='x', pady=1)
        status = entry.get('status', '')
        status_color = COLORS['green'] if status == 'Success' else COLORS['red']
        vals = [
            (entry.get('time', ''), 16, COLORS['text2']),
            (str(entry.get('nonce', ''))[:14], 14, COLORS['text']),
            (entry.get('reward', ''), 14, COLORS['accent']),
            ((entry.get('tx_hash', '')[:20] + '...' if len(entry.get('tx_hash', '')) > 20
              else entry.get('tx_hash', '')), 22, COLORS['blue']),
            (status, 8, status_color),
        ]
        for text, w, fg in vals:
            tk.Label(row, text=text, font=('Consolas', 9), fg=fg, bg=bg,
                     width=w, anchor='w').pack(side='left', padx=2)

    # ── SETTINGS PANEL ──

    def _build_settings_panel(self):
        panel = tk.Frame(self.content_frame, bg=COLORS['bg'])
        self.panels['settings'] = panel
        canvas, content = self._make_scrollable_panel(panel)

        gas_card = self._make_card(content)
        gas_card.pack(fill='x', padx=24, pady=(16, 16))
        gas_header = tk.Frame(gas_card, bg=COLORS['bg_card'])
        gas_header.pack(fill='x')
        tk.Label(gas_header, text='\u2699', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        gas_title = tk.Label(gas_header, text=self.t('gas_settings'),
                              font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        gas_title.pack(side='left')
        self._register_i18n(gas_title, 'gas_settings')
        self._make_separator(gas_card)

        gp_lbl = tk.Label(gas_card, text=self.t('gas_price'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        gp_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(gp_lbl, 'gas_price')
        self.gas_price_var = tk.StringVar(value=self.config.get('gas_price', '0.05'))
        self._make_entry(gas_card, textvariable=self.gas_price_var).pack(fill='x', pady=(0, 12), ipady=8)

        gl_lbl = tk.Label(gas_card, text=self.t('gas_limit'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        gl_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(gl_lbl, 'gas_limit')
        self.gas_limit_var = tk.StringVar(value=self.config.get('gas_limit', '200000'))
        self._make_entry(gas_card, textvariable=self.gas_limit_var).pack(fill='x', pady=(0, 12), ipady=8)

        ct_lbl = tk.Label(gas_card, text=self.t('contract'), font=('Segoe UI', 9, 'bold'),
                           fg=COLORS['text2'], bg=COLORS['bg_card'])
        ct_lbl.pack(anchor='w', pady=(0, 4))
        self._register_i18n(ct_lbl, 'contract')
        tk.Label(gas_card, text=CONTRACT_ADDRESS, font=('Consolas', 10),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(anchor='w', pady=(0, 16))
        save_btn = self._make_accent_btn(gas_card, text=self.t('save_settings'), command=self._save_config)
        save_btn.pack(fill='x', ipady=6)
        self._register_i18n(save_btn, 'save_settings')

        # About
        about_card = self._make_card(content)
        about_card.pack(fill='x', padx=24, pady=(0, 24))
        about_header = tk.Frame(about_card, bg=COLORS['bg_card'])
        about_header.pack(fill='x')
        tk.Label(about_header, text='\u2139', font=('Segoe UI', 14),
                 fg=COLORS['accent'], bg=COLORS['bg_card']).pack(side='left', padx=(0, 8))
        about_title = tk.Label(about_header, text=self.t('about'),
                                font=('Segoe UI', 13, 'bold'), fg=COLORS['white'], bg=COLORS['bg_card'])
        about_title.pack(side='left')
        self._register_i18n(about_title, 'about')
        self._make_separator(about_card)
        about_label = tk.Label(about_card, text=self.t('about_text'),
                                 font=('Segoe UI', 10), fg=COLORS['text2'],
                                 bg=COLORS['bg_card'], justify='left', wraplength=550)
        about_label.pack(anchor='w', fill='x')
        self._register_i18n(about_label, 'about_text')

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
        if not pk:
            messagebox.showerror(self.t('error'), self.t('enter_pk'))
            return
        try:
            if not rpc or rpc == DEFAULT_RPC:
                self._log("多 RPC 测速中...")
                best_rpc, best_lat = select_best_rpc(DEFAULT_RPC_LIST, on_log=self._log)
                if best_rpc:
                    rpc = best_rpc
                    self.rpc_var.set(rpc)
                    self._log(f"选中最快节点: {rpc} ({best_lat:.0f}ms)")
                else:
                    rpc = DEFAULT_RPC

            self.w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
            if not self.w3.is_connected():
                raise Exception("Cannot connect to RPC")

            self.account = Account.from_key(pk)
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

            try:
                self.multicall = Multicall(self.w3)
                self._log("Multicall3 已启用")
            except Exception:
                self.multicall = None

            self._log(f"已连接  钱包: {self.account.address}")
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
        now = time.monotonic()
        if hasattr(self, '_last_refresh_time') and (now - self._last_refresh_time) < 5.0:
            return
        self._last_refresh_time = now
        threading.Thread(target=self._do_refresh, daemon=True).start()

    def _do_refresh(self):
        try:
            addr = self.account.address
            bnb = self.w3.eth.get_balance(addr)
            if self.multicall:
                results = self.multicall.batch_call([
                    (self.contract, 'balanceOf', (addr,)),
                    (self.contract, 'getMiningDifficulty', ()),
                    (self.contract, 'getMiningReward', ()),
                    (self.contract, 'epochCount', ()),
                    (self.contract, 'tokensMinted', ()),
                    (self.contract, 'rewardEra', ()),
                ])
                sat, difficulty, reward, epoch, minted, era = results
            else:
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
        except Exception as e:
            self._log(f"[Error] 刷新: {e}")

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

        # 构建反应式挖矿配置
        cfg = dict(self.yaml_cfg)
        pk = self.pk_var.get().strip()
        cfg["_pk"] = pk if pk.startswith("0x") else "0x" + pk
        cfg["private_key"] = pk
        cfg["gas_limit"] = int(self.gas_limit_var.get())

        def on_log(msg, lv="INFO"):
            self._log(msg)

        def on_win(epoch):
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nonce": "", "reward": "50 SAT",
                "tx_hash": f"epoch={epoch}", "status": "Success"
            }
            self.history.append(entry)
            self._save_history()
            self.root.after(0, lambda: self._add_history_row(entry))
            self._refresh_info()

        def on_lose():
            entry = {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "nonce": "", "reward": "0",
                "tx_hash": "被抢先 revert", "status": "Failed"
            }
            self.history.append(entry)
            self._save_history()
            self.root.after(0, lambda: self._add_history_row(entry))

        def on_stats(s):
            def _upd():
                self.mining_stat_labels['solver_mode'].config(text=s.get('mode', 'CPU'))
                self.mining_stat_labels['won_count'].config(text=str(s.get('won', 0)))
                self.mining_stat_labels['lost_count'].config(text=str(s.get('lost', 0)))
                self.mining_stat_labels['sent_count'].config(text=str(s.get('sent', 0)))
                self.mining_stat_labels['win_rate'].config(text=f"{s.get('win_rate', 0):.0f}%")
            self.root.after(0, _upd)

        try:
            self.miner = ReactiveMiner(cfg, on_log=on_log, on_win=on_win,
                                        on_lose=on_lose, on_stats=on_stats)
            self.miner.start()
            self._log(f"反应式挖矿引擎启动  求解器: {self.miner.mode.upper()}  "
                      f"难度: {self.miner.difficulty}  "
                      f"Gas: {Web3.from_wei(self.miner.gas_wei, 'gwei')} Gwei")
            if self.miner.dry:
                self._log("*** DRY_RUN 模式: 只算解+计时, 不广播不花 gas ***")
        except Exception as e:
            self._log(f"[Error] 启动失败: {e}")
            self.mining = False
            self.mine_btn.config(text=self.t('start_mining'), bg=COLORS['accent'])
            self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])

    def _stop_mining(self):
        self.mining = False
        if self.miner:
            self.miner.stop()
            self.miner = None
        self.mine_btn.config(text=self.t('start_mining'), bg=COLORS['accent'])
        self.mining_status_label.config(text=self.t('mining_idle'), fg=COLORS['text3'])
        self._log(self.t('mining_stopped'))


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def main():
    multiprocessing.freeze_support()
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
