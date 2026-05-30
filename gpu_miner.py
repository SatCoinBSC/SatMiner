#!/usr/bin/env python3
"""GPU 挖矿引擎 (PyOpenCL + keccak256 内核).

在 macOS / Apple Silicon (M4 Pro) 上, OpenCL 由系统转译到 Metal 执行.
本模块惰性依赖 pyopencl —— 只有 engine=gpu 时才会被导入.

⚠️ 此实现尚未在链上验证. 默认引擎为 CPU. 使用前请自行测试.
   安全保障: 找到候选 nonce 后, 调用方会用 pycryptodome 在 CPU 上复核
   digest 是否真的 <= target, 复核不通过则丢弃, 不会提交错误的解.

合约 PoW: digest = keccak256( challengeNumber(32) ++ minerAddress(20) ++ nonce(uint256,32) )
即对 84 字节消息做 keccak256, 单个吸收块即可 (rate=136 字节).

可两种方式使用:
  1) 被 miner.py 导入: from gpu_miner import GpuMiner  (engine: gpu 时)
  2) 独立运行: python3 gpu_miner.py  —— 自带 RPC 测速/轮询、gas 省钱闸门、
     提交前模拟、多钱包轮换、自动重启、累计统计, 与 miner.py 共用同一 config.yaml.
     可与 miner.py(CPU) 同时各开一个进程, 实现 CPU+GPU 双进程并挖.
"""

import os
import sys
import time
import queue
import random
import signal
import threading

import yaml
from web3 import Web3

try:
    from web3.exceptions import TransactionNotFound
except Exception:  # web3 版本差异兜底
    class TransactionNotFound(Exception):
        pass

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

ABI = [
    {"inputs": [], "name": "challengeNumber", "outputs": [{"type": "bytes32"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "miningTarget", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getMiningDifficulty", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "getMiningReward", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "epochCount", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "tokensMinted", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "", "type": "address"}], "name": "balanceOf", "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [{"name": "nonce", "type": "uint256"}, {"name": "challengeDigest", "type": "bytes32"}], "name": "mint", "outputs": [{"type": "bool"}], "stateMutability": "nonpayable", "type": "function"},
]

running = True

COLORS = {
    "INFO": "\033[37m", "OK": "\033[92m", "WARN": "\033[93m",
    "ERROR": "\033[91m", "HASH": "\033[36m", "MINE": "\033[95m", "RESET": "\033[0m",
}


def log(msg, level="INFO"):
    ts = time.strftime("%H:%M:%S")
    c = COLORS.get(level, COLORS["INFO"])
    print(f"{c}[{ts}] [{level:>5}] {msg}{COLORS['RESET']}", flush=True)

# OpenCL C 内核: 对 84 字节消息做 keccak256, 扫描 nonce = start_nonce + global_id
KERNEL_SRC = r"""
__constant ulong RC[24] = {
  0x0000000000000001UL, 0x0000000000008082UL, 0x800000000000808aUL, 0x8000000080008000UL,
  0x000000000000808bUL, 0x0000000080000001UL, 0x8000000080008081UL, 0x8000000000008009UL,
  0x000000000000008aUL, 0x0000000000000088UL, 0x0000000080008009UL, 0x000000008000000aUL,
  0x000000008000808bUL, 0x800000000000008bUL, 0x8000000000008089UL, 0x8000000000008003UL,
  0x8000000000008002UL, 0x8000000000000080UL, 0x000000000000800aUL, 0x800000008000000aUL,
  0x8000000080008081UL, 0x8000000000008080UL, 0x0000000080000001UL, 0x8000000080008008UL
};

__constant int ROTC[24] = {
  1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
  27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44
};

__constant int PILN[24] = {
  10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
  15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1
};

static inline ulong rotl64(ulong x, int n) {
    return (x << n) | (x >> (64 - n));
}

static void keccacf(ulong st[25]) {
    ulong bc[5], t;
    for (int round = 0; round < 24; round++) {
        // Theta
        for (int i = 0; i < 5; i++)
            bc[i] = st[i] ^ st[i+5] ^ st[i+10] ^ st[i+15] ^ st[i+20];
        for (int i = 0; i < 5; i++) {
            t = bc[(i+4)%5] ^ rotl64(bc[(i+1)%5], 1);
            for (int j = 0; j < 25; j += 5)
                st[j+i] ^= t;
        }
        // Rho + Pi
        t = st[1];
        for (int i = 0; i < 24; i++) {
            int j = PILN[i];
            bc[0] = st[j];
            st[j] = rotl64(t, ROTC[i]);
            t = bc[0];
        }
        // Chi
        for (int j = 0; j < 25; j += 5) {
            for (int i = 0; i < 5; i++) bc[i] = st[j+i];
            for (int i = 0; i < 5; i++)
                st[j+i] ^= (~bc[(i+1)%5]) & bc[(i+2)%5];
        }
        // Iota
        st[0] ^= RC[round];
    }
}

__kernel void mine(__global const uchar* prefix52,   // 52 字节: challenge(32)+addr(20)
                   __global const uchar* target32,   // 32 字节, big-endian
                   const ulong start_nonce,
                   __global ulong* result)           // 输出: 命中的 nonce, 初值 0 表示未找到
{
    ulong nonce = start_nonce + (ulong)get_global_id(0);

    // 构建 136 字节填充块
    uchar b[136];
    for (int i = 0; i < 136; i++) b[i] = 0;
    for (int i = 0; i < 52; i++) b[i] = prefix52[i];
    // nonce 作为 uint256 big-endian 占 b[52..83]; 仅低 64 位非零 -> b[76..83]
    for (int i = 0; i < 8; i++)
        b[83 - i] = (uchar)((nonce >> (8 * i)) & 0xff);
    b[84] = 0x01;    // keccak padding 起始
    b[135] = 0x80;   // keccak padding 结束

    // 吸收: 17 个 lane (小端), XOR 进 state
    ulong st[25];
    for (int i = 0; i < 25; i++) st[i] = 0;
    for (int j = 0; j < 17; j++) {
        ulong lane = 0;
        for (int k = 0; k < 8; k++)
            lane |= ((ulong)b[j*8 + k]) << (8 * k);
        st[j] ^= lane;
    }

    keccacf(st);

    // 输出 32 字节 digest: digest[L*8+k] = (st[L] >> (8k)) & 0xff, L=0..3
    // 按 big-endian 与 target32 逐字节比较 (digest[0] 为最高位)
    for (int i = 0; i < 32; i++) {
        int L = i / 8;
        int k = i % 8;
        uchar dbyte = (uchar)((st[L] >> (8 * k)) & 0xff);
        uchar tbyte = target32[i];
        if (dbyte < tbyte) {           // digest < target -> 有效
            result[0] = nonce;
            return;
        } else if (dbyte > tbyte) {    // digest > target -> 无效
            return;
        }
        // 相等则比较下一字节
    }
    // 全部相等 (digest == target), 也算有效 (<=)
    result[0] = nonce;
}
"""


class GpuMiner:
    def __init__(self, cfg):
        import pyopencl as cl
        import numpy as np
        self.cl = cl
        self.np = np

        self.batch_size = int(cfg.get("gpu_batch_size", 4_000_000))

        # GPU 占空比节流 (温控):
        #   gpu_target_util = 目标平均占用率(%), 范围 1..100.
        #   100 = 全速不节流; 50 = 算一批歇一批(温度≈砍半); 越低越凉, 算力同比下降.
        #   原理: 每批 search 实测耗时 t_batch, 之后 sleep = t_batch*(100-U)/U,
        #         使 占用率 = 忙/(忙+歇) ≈ U. 不依赖预设算力, 换机器/换 batch 都自适应.
        util = cfg.get("gpu_target_util", 100)
        try:
            util = float(util)
        except (TypeError, ValueError):
            util = 100.0
        self.target_util = min(100.0, max(1.0, util))

        # 选设备: 优先 GPU. 若配置了 gpu_device 子串 (如 "3070"/"NVIDIA"), 优先匹配它
        # (多 OpenCL 平台/设备时避免选错, 例如核显 + 独显并存).
        want = str(cfg.get("gpu_device", "") or "").lower()
        gpus = []
        for platform in cl.get_platforms():
            for d in platform.get_devices():
                if d.type & cl.device_type.GPU:
                    gpus.append(d)
        device = None
        if want:
            for d in gpus:
                if want in d.name.strip().lower():
                    device = d
                    break
        if device is None and gpus:
            device = gpus[0]
        if device is None:
            # 退而求其次用任意设备
            device = cl.get_platforms()[0].get_devices()[0]

        self.device = device
        self.ctx = cl.Context([device])
        self.queue = cl.CommandQueue(self.ctx)
        self.program = cl.Program(self.ctx, KERNEL_SRC).build()
        self.kernel = self.program.mine

        self.device_name = device.name.strip()

    def search(self, prefix52, target32, start_nonce, count):
        """扫描 [start_nonce, start_nonce+count) 区间.
        返回命中的 nonce (int) 或 None."""
        cl = self.cl
        np = self.np
        mf = cl.mem_flags

        prefix_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                               hostbuf=np.frombuffer(prefix52, dtype=np.uint8))
        target_buf = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                               hostbuf=np.frombuffer(target32, dtype=np.uint8))
        result = np.array([0], dtype=np.uint64)
        result_buf = cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=result)

        t0 = time.time()
        self.kernel(self.queue, (int(count),), None,
                    prefix_buf, target_buf, np.uint64(start_nonce), result_buf)
        cl.enqueue_copy(self.queue, result, result_buf)
        self.queue.finish()
        t_batch = time.time() - t0

        # 占空比节流: 算一批后按目标占用率休眠, 把 GPU 平均占用(≈温度)锁定在 target_util.
        # sleep = t_batch * (100 - U) / U  ->  忙/(忙+歇) = U
        if self.target_util < 100.0:
            sleep_s = t_batch * (100.0 - self.target_util) / self.target_util
            if sleep_s > 0:
                time.sleep(sleep_s)

        return None if result[0] == 0 else int(result[0])


# ============================================================================
# 以下为独立运行所需逻辑 (与 miner.py 共用同一 config.yaml).
# 被 import 时 (__name__ != "__main__") 这些函数定义好但不会执行 main().
# ============================================================================

# ----------------------------------------------------------------------------
# 配置 / 连接
# ----------------------------------------------------------------------------
def _norm_key(k):
    k = str(k).strip()
    return k if k.startswith("0x") else "0x" + k


def load_config():
    with open(CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)
    keys = cfg.get("private_keys") or []
    if keys:
        cfg["private_keys"] = [_norm_key(k) for k in keys]
    else:
        pk = cfg.get("private_key")
        if not pk or pk == "YOUR_PRIVATE_KEY_HERE":
            log("请先在 config.yaml 中填写 private_key 或 private_keys", "ERROR")
            sys.exit(1)
        cfg["private_keys"] = [_norm_key(pk)]
    return cfg


def select_rpc(cfg):
    """若配置了 rpc_urls 列表, 测速选最快可达的; 否则用单个 rpc_url."""
    urls = cfg.get("rpc_urls") or []
    if not urls:
        return cfg["rpc_url"]
    log(f"测速 {len(urls)} 个 RPC 节点, 选最快可达的...")
    best = None
    best_lat = None
    for url in urls:
        try:
            t0 = time.time()
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 6}))
            if not w3.is_connected():
                log(f"  {url}  连接失败", "WARN")
                continue
            _ = w3.eth.block_number
            lat = (time.time() - t0) * 1000
            log(f"  {url}  {lat:.0f}ms")
            if best_lat is None or lat < best_lat:
                best, best_lat = url, lat
        except Exception as e:
            log(f"  {url}  失败: {str(e)[:40]}", "WARN")
    if best is None:
        log("所有 rpc_urls 均无法连接, 回退到 rpc_url", "WARN")
        return cfg.get("rpc_url") or urls[0]
    log(f"选中: {best}  ({best_lat:.0f}ms)", "OK")
    return best


def connect(cfg):
    rpc = select_rpc(cfg)
    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        log(f"无法连接 RPC: {rpc}", "ERROR")
        sys.exit(1)
    cfg["rpc_url"] = rpc  # 记录实际选中的节点
    log(f"已连接 RPC: {rpc}  Chain ID: {w3.eth.chain_id}")
    accounts = [w3.eth.account.from_key(k) for k in cfg["private_keys"]]
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(cfg["contract_address"]), abi=ABI)
    return w3, accounts, contract


def show_status(w3, contract, miner_addr):
    try:
        epoch = contract.functions.epochCount().call()
        difficulty = contract.functions.getMiningDifficulty().call()
        reward = contract.functions.getMiningReward().call()
        minted = contract.functions.tokensMinted().call()
        sat_balance = contract.functions.balanceOf(miner_addr).call()
        bnb_balance = w3.eth.get_balance(miner_addr)
        log(f"Epoch: {epoch}  难度: {difficulty}  区块奖励: {Web3.from_wei(reward, 'ether')} SAT")
        log(f"已铸造: {Web3.from_wei(minted, 'ether')} / 21,000,000 SAT")
        log(f"余额: {Web3.from_wei(bnb_balance, 'ether')} BNB  |  {Web3.from_wei(sat_balance, 'ether')} SAT", "OK")
    except Exception as e:
        log(f"读取链上状态失败: {e}", "WARN")


# ----------------------------------------------------------------------------
# Gas 策略
# ----------------------------------------------------------------------------
def get_gas_price(w3, cfg):
    """返回本次使用的 gas 价格 (Gwei) 以及网络实时 gas 价格 (Gwei)"""
    net_gwei = None
    try:
        net_gwei = float(Web3.from_wei(w3.eth.gas_price, "gwei"))
    except Exception:
        pass
    if cfg.get("use_network_gas", True) and net_gwei is not None:
        gwei = net_gwei * float(cfg.get("network_gas_multiplier", 1.2))
        floor = float(cfg.get("min_gas_price_gwei", 0.1))
        cap = float(cfg.get("max_gas_price_gwei", 5))
        return max(floor, min(gwei, cap)), net_gwei
    return float(cfg.get("gas_price_gwei", 1)), net_gwei


def wait_for_cheap_gas(w3, cfg):
    """若启用 mine_only_below_gwei, 阻塞直到网络 gas <= 阈值.
    返回 (proceed, current_gas, net_gas): proceed=False 表示被 Ctrl+C 中断;
    返回的 gas 值即最后一次读取的价, 调用方可直接复用, 避免再查一次 eth_gas_price.
    gas 查询失败时放行(net=None)."""
    threshold = float(cfg.get("mine_only_below_gwei", 0) or 0)
    recheck = float(cfg.get("gas_recheck_secs", 15))
    waited = False
    while running:
        current, net = get_gas_price(w3, cfg)
        if threshold <= 0 or net is None or net <= threshold:
            if waited and net is not None:
                log(f"网络 gas 回落到 {net:.3f} Gwei (<= {threshold}), 恢复挖矿", "OK")
            return True, current, net
        if not waited:
            log(f"网络 gas {net:.3f} Gwei > 阈值 {threshold} Gwei, 暂停挖矿省钱...", "WARN")
            waited = True
        else:
            log(f"等待中: 网络 gas {net:.3f} Gwei > {threshold} Gwei, {recheck:.0f}s 后重查", "WARN")
        slept = 0.0
        while running and slept < recheck:
            time.sleep(min(1.0, recheck - slept))
            slept += 1.0
    return False, None, None


def submit_mint(w3, contract, account, cfg, nonce_val, digest, gas_price_gwei):
    miner_addr = account.address

    # 提交前模拟 (eth_call): 不花 gas 先验一遍 mint 是否会成功.
    # 若此刻挑战号已被他人抢先更新, 模拟会 revert -> 直接跳过, 省下这次失败的 gas.
    if cfg.get("simulate_before_submit", True):
        try:
            contract.functions.mint(nonce_val, digest).call({"from": miner_addr})
        except Exception:
            log("提交前模拟检测到会失败 (已被抢先), 跳过提交 → 本轮 0 gas", "WARN")
            return None  # None = 未发送交易, 没花 gas

    log(f"正在构建 mint 交易... (gas: {gas_price_gwei:.2f} Gwei)", "WARN")
    tx = contract.functions.mint(nonce_val, digest).build_transaction({
        "from": miner_addr,
        "nonce": w3.eth.get_transaction_count(miner_addr),
        "gas": cfg["gas_limit"],
        "gasPrice": Web3.to_wei(gas_price_gwei, "gwei"),
        "chainId": cfg["chain_id"],
    })
    signed = w3.eth.account.sign_transaction(tx, account.key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    log(f"交易已发送: {tx_hash.hex()}")
    log("等待链上确认...", "WARN")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status == 1:
        cost = Web3.from_wei(receipt.gasUsed * Web3.to_wei(gas_price_gwei, "gwei"), "ether")
        log(f"Mint 成功! 区块: {receipt.blockNumber}  Gas Used: {receipt.gasUsed}  花费: {cost} BNB", "OK")
        show_status(w3, contract, miner_addr)
        return True
    log("Mint 交易失败 (reverted, 被他人抢先上链)", "ERROR")
    return False


# ----------------------------------------------------------------------------
# Fire-and-forget 提交: 发出即返回, 确认放后台, GPU 不空等
# ----------------------------------------------------------------------------
def should_simulate(cfg, net_gwei):
    """是否在提交前做 eth_call 模拟预检.
    总开关 simulate_before_submit=false -> 永不模拟.
    否则按实时网络 gas 动态决定: 仅当 net_gwei > simulate_gas_threshold_gwei 时才模拟
    (gas 便宜时跳过模拟全力抢先; gas 贵时才用模拟省下失败 gas).
    阈值 <=0 或拿不到网络价 -> 保守地总是模拟."""
    if not cfg.get("simulate_before_submit", True):
        return False
    thr = float(cfg.get("simulate_gas_threshold_gwei", 0.1))
    if thr <= 0 or net_gwei is None:
        return True
    return net_gwei > thr


class NonceManager:
    """本地维护每钱包的待发 nonce. fire-and-forget 下上一笔可能还没进块,
    若用 get_transaction_count(latest) 会拿到旧 nonce 导致顶替/underpriced,
    故首次用 'pending' 初始化, 之后每成功发一笔本地 +1."""

    def __init__(self):
        self._n = {}

    def reserve(self, w3, addr):
        if addr not in self._n:
            self._n[addr] = w3.eth.get_transaction_count(addr, "pending")
        return self._n[addr]

    def commit(self, addr):
        self._n[addr] = self._n.get(addr, 0) + 1

    def resync(self, w3, addr):
        self._n[addr] = w3.eth.get_transaction_count(addr, "pending")
        return self._n[addr]

    def peek(self, addr):
        """本地下一个待用 nonce; 从未为该钱包发过则返回 None."""
        return self._n.get(addr)

    def set(self, addr, n):
        self._n[addr] = n


def send_mint(w3, contract, account, cfg, nonce_val, digest, gas_price_gwei,
              net_gwei, nonce_mgr):
    """构建并发送 mint, 立即返回, 不等确认.
    返回 (tx_hash, tx_nonce, send_ms) 表示已发送 (send_ms = send_raw_transaction
    网络往返耗时, 毫秒); 返回 None 表示模拟预检拦截(未发送, 0 gas).
    insufficient funds / nonce 类异常向上抛出, 由调用方处理."""
    miner_addr = account.address

    if should_simulate(cfg, net_gwei):
        try:
            contract.functions.mint(nonce_val, digest).call({"from": miner_addr})
        except Exception:
            log("提交前模拟检测到会失败 (已被抢先), 跳过提交 → 本轮 0 gas", "WARN")
            return None

    tx_nonce = nonce_mgr.reserve(w3, miner_addr)
    tx = contract.functions.mint(nonce_val, digest).build_transaction({
        "from": miner_addr,
        "nonce": tx_nonce,
        "gas": cfg["gas_limit"],
        "gasPrice": Web3.to_wei(gas_price_gwei, "gwei"),
        "chainId": cfg["chain_id"],
    })
    signed = w3.eth.account.sign_transaction(tx, account.key)
    _t0 = time.time()
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    send_ms = (time.time() - _t0) * 1000.0
    nonce_mgr.commit(miner_addr)
    return tx_hash, tx_nonce, send_ms


class Confirmer:
    """后台确认线程: 单循环 + 在途列表轮询 (非阻塞, 多笔并行确认, 一笔卡住不堵其它),
    以 receipt_poll_secs 节奏轮询 receipt (替代 web3 默认 0.1s 轮询, 大幅削减 RPC),
    按钱包累计 发出/成功/失败/超时/gas, 每 stats_interval_secs 打印一次汇总.
    quiet=True 时除周期汇总外不打印逐笔日志."""

    # 连续多少次"非 TransactionNotFound"的 receipt 查询异常后告警 (穿透 quiet),
    # 用于把"RPC 故障/限流"与"交易真的还没进块/超时"区分开.
    RPC_ERR_WARN_AT = 10

    def __init__(self, w3, cfg, labels=None, quiet=True):
        self.w3 = w3
        self.poll = max(0.5, float(cfg.get("receipt_poll_secs", 3)))
        self.timeout = float(cfg.get("receipt_timeout_secs", 180))
        self.stats_interval = float(
            cfg.get("stats_interval_secs", cfg.get("log_interval", 10)))
        self.quiet = quiet
        self.labels = labels or {}            # addr -> "钱包[i]" 标签
        self.addresses = list(self.labels)    # 需后台刷新余额的地址
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.stats = {}      # addr -> {sent,mined,failed,timed_out,skipped,gas}
        self.balances = {}   # addr -> 余额(wei); 后台每 stats_interval 刷新一次
        # 延迟诊断累计: 把"找到解->链上确认"拆成各段, 量化竞速瓶颈在哪.
        #   send  = send_raw_transaction 网络往返 (RPC 写延迟)
        #   recheck = 发送前 challengeNumber 兜底查询往返 (此延迟直接吃掉竞速窗口)
        #   confirm = 找到解 -> 进块成功 的端到端耗时 (仅成功的笔计)
        self.lat = {"send_ms": 0.0, "send_n": 0,
                    "recheck_ms": 0.0, "recheck_n": 0,
                    "confirm_ms": 0.0, "confirm_n": 0}
        self.inflight = []   # [{tx,addr,gas,nonce,deadline}] 仅后台线程访问
        self._rpc_err_streak = 0
        self.start = time.time()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _bucket(self, addr):
        b = self.stats.get(addr)
        if b is None:
            b = {"sent": 0, "mined": 0, "failed": 0,
                 "timed_out": 0, "skipped": 0, "gas": 0.0}
            self.stats[addr] = b
        return b

    def update_w3(self, w3):
        self.w3 = w3

    def submit(self, tx_hash, addr, gas_gwei, nonce,
               found_at=None, send_ms=None, recheck_ms=None):
        with self.lock:
            self._bucket(addr)["sent"] += 1
            if send_ms is not None:
                self.lat["send_ms"] += send_ms
                self.lat["send_n"] += 1
            if recheck_ms is not None:
                self.lat["recheck_ms"] += recheck_ms
                self.lat["recheck_n"] += 1
        self.q.put((tx_hash, addr, gas_gwei, nonce, found_at))

    def note_skip(self, addr):
        """记一次被抢先/模拟拦截的跳过 (未发送, 0 gas)."""
        with self.lock:
            self._bucket(addr)["skipped"] += 1

    def pending_for(self, addr):
        """该钱包当前待确认笔数 = 发出 - 成功 - 失败 - 超时."""
        with self.lock:
            b = self.stats.get(addr)
            if not b:
                return 0
            return b["sent"] - b["mined"] - b["failed"] - b["timed_out"]

    def get_cached_balance(self, addr):
        """返回后台缓存的余额(wei); 尚未刷新过则返回 None (调用方按未知处理)."""
        with self.lock:
            return self.balances.get(addr)

    def join_drain(self, max_wait=30.0):
        """退出前给后台一点时间把在途交易确认完 (尽力而为), 最后再汇总一次."""
        deadline = time.time() + max_wait
        while running and time.time() < deadline:
            if self.q.empty() and not self.inflight:
                break
            time.sleep(0.5)
        self._print_summary()

    def _run(self):
        last_summary = time.time()
        while running:
            # 1. 收新提交并入在途列表
            while True:
                try:
                    tx_hash, addr, gas, nonce, found_at = self.q.get_nowait()
                except queue.Empty:
                    break
                self.inflight.append({
                    "tx": tx_hash, "addr": addr, "gas": gas, "nonce": nonce,
                    "found_at": found_at, "deadline": time.time() + self.timeout})
            # 2. 对每笔在途各查一次 receipt
            still = []
            for it in self.inflight:
                if not running:
                    break
                if self._check(it):
                    continue  # 已结算
                if time.time() >= it["deadline"]:
                    with self.lock:
                        self._bucket(it["addr"])["timed_out"] += 1
                    if not self.quiet:
                        log(f"⏳ 确认超时 nonce={it['nonce']} "
                            f"tx={it['tx'].hex()[:18]}..", "WARN")
                else:
                    still.append(it)
            self.inflight = still
            # 3. 周期: 刷新余额 + 打印汇总 (合并在同一节奏, 不额外加 RPC 频率)
            now = time.time()
            if now - last_summary >= self.stats_interval:
                last_summary = now
                self._refresh_balances()
                self._print_summary()
            time.sleep(self.poll)

    def _check(self, it):
        """已出结果(成功/失败, 含 gas) -> True; 尚未进块/查询失败 -> False.
        区分 TransactionNotFound(正常, 还没进块) 与真正的 RPC 异常(限流/宕机),
        后者累计到一定次数后告警, 避免精简日志下故障被'超时'掩盖."""
        try:
            rcpt = self.w3.eth.get_transaction_receipt(it["tx"])
            self._rpc_err_streak = 0
        except TransactionNotFound:
            self._rpc_err_streak = 0  # 正常: 尚未进块
            return False
        except Exception as e:
            self._rpc_err_streak += 1
            if self._rpc_err_streak == self.RPC_ERR_WARN_AT:
                log(f"⚠ 确认 RPC 连续 {self.RPC_ERR_WARN_AT} 次查询失败 "
                    f"(可能限流/节点故障, '超时'统计可能失真): {str(e)[:60]}", "WARN")
            return False
        if rcpt is None:
            return False
        cost = float(Web3.from_wei(
            rcpt.gasUsed * Web3.to_wei(it["gas"], "gwei"), "ether"))
        with self.lock:
            b = self._bucket(it["addr"])
            b["gas"] += cost  # 成功或 revert 都已耗 gas
            if rcpt.status == 1:
                b["mined"] += 1
                if it.get("found_at") is not None:
                    self.lat["confirm_ms"] += (time.time() - it["found_at"]) * 1000.0
                    self.lat["confirm_n"] += 1
            else:
                b["failed"] += 1
        if not self.quiet:
            if rcpt.status == 1:
                log(f"✓ 确认 区块 {rcpt.blockNumber} nonce={it['nonce']} "
                    f"{cost:.8f} BNB", "OK")
            else:
                log(f"✗ revert(已付gas) nonce={it['nonce']} "
                    f"tx={it['tx'].hex()[:18]}..", "WARN")
        return True

    def _refresh_balances(self):
        """后台批量刷新各钱包余额 (每 stats_interval 一次), 主循环改读缓存,
        从而消除'每轮 get_balance'的高频 RPC. 查询失败保留旧值, 不覆盖为 None."""
        for addr in self.addresses:
            if not running:
                break
            try:
                bal = self.w3.eth.get_balance(addr)
            except Exception:
                continue
            with self.lock:
                self.balances[addr] = bal

    def _print_summary(self):
        with self.lock:
            snap = [(a, dict(b)) for a, b in self.stats.items()]
            bals = dict(self.balances)
            lat = dict(self.lat)
        if not snap:
            return
        elapsed = time.time() - self.start
        log("─" * 10 + f" 钱包统计 (运行 {elapsed:.0f}s) " + "─" * 10, "MINE")
        tot = {"sent": 0, "mined": 0, "failed": 0,
               "timed_out": 0, "skipped": 0, "gas": 0.0}
        for addr, b in snap:
            pend = b["sent"] - b["mined"] - b["failed"] - b["timed_out"]
            tag = self.labels.get(addr, addr[:10] + "..")
            bw = bals.get(addr)
            bstr = f"{float(Web3.from_wei(bw, 'ether')):.5f}" if bw is not None else "?"
            log(f"  {tag} {addr[:10]}..  发出 {b['sent']}  成功 {b['mined']}  "
                f"失败 {b['failed']}  超时 {b['timed_out']}  跳过 {b['skipped']}  "
                f"待确认 {pend}  gas {b['gas']:.6f}  余额 {bstr} BNB", "MINE")
            for k in tot:
                tot[k] += b[k]
        tpend = tot["sent"] - tot["mined"] - tot["failed"] - tot["timed_out"]
        log(f"  合计  发出 {tot['sent']}  成功 {tot['mined']}  "
            f"失败(浪费gas) {tot['failed']}  超时 {tot['timed_out']}  "
            f"跳过 {tot['skipped']}  待确认 {tpend}  gas {tot['gas']:.6f} BNB", "MINE")

        # 诊断: 已结算(成功+失败)中的胜率, 以及各段延迟均值. 用于判断瓶颈是"延迟"还是"gas".
        settled = tot["mined"] + tot["failed"]
        win = (tot["mined"] / settled * 100.0) if settled else 0.0
        send_avg = (lat["send_ms"] / lat["send_n"]) if lat["send_n"] else 0.0
        rck_avg = (lat["recheck_ms"] / lat["recheck_n"]) if lat["recheck_n"] else 0.0
        cfm_avg = (lat["confirm_ms"] / lat["confirm_n"]) if lat["confirm_n"] else 0.0
        rck_str = (f"recheck {rck_avg:.0f}ms  " if lat["recheck_n"] else "recheck 关闭  ")
        log(f"  诊断  胜率 {win:.0f}% ({tot['mined']}/{settled})  "
            f"发送 {send_avg:.0f}ms  {rck_str}"
            f"确认 {cfm_avg:.0f}ms (找到解→进块, n={lat['confirm_n']})", "MINE")


def fmt_hashrate(rate):
    if rate >= 1_000_000:
        return f"{rate / 1_000_000:.2f} MH/s"
    if rate >= 1_000:
        return f"{rate / 1_000:.2f} KH/s"
    return f"{rate:.0f} H/s"


# ----------------------------------------------------------------------------
# 单轮 GPU 搜索: 返回 (found, round_hashes, abandoned)
#   found = (nonce:int, digest:bytes) 或 None
#   abandoned = True 表示挑战号被他人抢先, 本轮放弃
# ----------------------------------------------------------------------------
def gpu_search_round(gpu, prefix, target, base_nonce,
                     w3, contract, challenge, log_interval, challenge_check_secs,
                     quiet=True):
    from Crypto.Hash import keccak as _kc
    batch = gpu.batch_size
    # 限制到 48 位起点, 避免一轮内 nonce 超出 64 位
    nonce = base_nonce & ((1 << 48) - 1)
    total_hashes = 0
    start_time = time.time()
    last_log_time = start_time
    last_check_time = start_time
    found = None
    abandoned = False

    # 目标值转 32 字节 big-endian
    target_bytes = target.to_bytes(32, "big")

    if not quiet:
        log(f"开始 PoW 计算 (GPU batch={batch})  起始 Nonce: {nonce}", "MINE")

    while running:
        win = gpu.search(prefix, target_bytes, nonce, batch)
        total_hashes += batch

        if win is not None:
            # CPU 复核 (pycryptodome), 防止内核误报
            k = _kc.new(digest_bits=256)
            k.update(prefix + int(win).to_bytes(32, "big"))
            digest = k.digest()
            if int.from_bytes(digest, "big") <= target:
                found = (int(win), digest)
                break
            if not quiet:
                log(f"GPU 候选解 {win} 复核未通过, 继续扫描", "WARN")

        nonce += batch

        now = time.time()
        if not quiet and now - last_log_time >= log_interval:
            rate = total_hashes / (now - start_time) if now > start_time else 0
            log(f"算力: {fmt_hashrate(rate)}  总哈希: {total_hashes}  耗时: {now - start_time:.0f}s", "HASH")
            last_log_time = now

        if now - last_check_time >= challenge_check_secs:
            last_check_time = now
            try:
                if contract.functions.challengeNumber().call() != challenge:
                    if not quiet:
                        log("挑战号已更新（被他人先挖到），切换到新一轮...", "WARN")
                    abandoned = True
                    break
            except Exception as e:
                log(f"检查挑战号失败: {e}", "WARN")

    return found, total_hashes, abandoned


# ----------------------------------------------------------------------------
# 网络容错: 抖动/代理断连时等待重试, 而不是崩溃退出
# ----------------------------------------------------------------------------
_NET_ERR_KEYS = (
    "proxy", "connection", "timeout", "timed out", "max retries",
    "remote end", "disconnected", "temporarily unavailable",
    "connection aborted", "connection reset", "name resolution",
    "failed to establish", "read timed out", "bad gateway",
    "service unavailable", "too many requests", "ssl", "eof occurred",
)


def _is_network_error(e):
    """粗略判断异常是否为网络/RPC 抖动类(可重试), 而非逻辑错误."""
    s = str(e).lower()
    return any(k in s for k in _NET_ERR_KEYS)


def _sleep_interruptible(secs):
    """可被 Ctrl+C 打断的休眠. running 变 False 时提前返回."""
    slept = 0.0
    while running and slept < secs:
        time.sleep(min(1.0, secs - slept))
        slept += 1.0


def reconnect(cfg, retry_secs=10):
    """网络故障后重新测速选 RPC 并重建 w3 / contract.
    一直重试直到成功; 被 Ctrl+C 打断时返回 (None, None)."""
    while running:
        try:
            rpc = select_rpc(cfg)
            w3 = Web3(Web3.HTTPProvider(rpc))
            if w3.is_connected():
                cfg["rpc_url"] = rpc
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(cfg["contract_address"]), abi=ABI)
                log(f"已重连 RPC: {rpc}", "OK")
                return w3, contract
            log(f"重连后仍无法连接, {retry_secs}s 后重试...", "WARN")
        except Exception as e:
            log(f"重连失败: {str(e)[:80]}, {retry_secs}s 后重试...", "WARN")
        _sleep_interruptible(retry_secs)
    return None, None


# ----------------------------------------------------------------------------
# 主挖矿循环 (GPU 引擎; gas 闸门 / 多钱包轮换 / 自动重启 / 统计)
# ----------------------------------------------------------------------------
def mine_loop(w3, contract, accounts, cfg, gpu):
    global running
    log_interval = cfg.get("log_interval", 10)
    challenge_check_secs = cfg.get("challenge_check_secs", 12)

    # 精简日志: 只保留 10s 一次的钱包统计汇总与真正的错误/网络告警,
    # 静音逐轮的 "正在 mint / 挑战号 / 算力 / 找到解" 等刷屏日志. quiet_logs=false 可恢复.
    quiet = bool(cfg.get("quiet_logs", True))

    def vlog(msg, level="INFO"):
        if not quiet:
            log(msg, level)

    vlog(f"挖矿引擎: GPU ({gpu.device_name})  batch={gpu.batch_size}  "
         f"目标占用 {gpu.target_util:.0f}%", "MINE")

    # fire-and-forget: 发出即返回, 确认放后台, GPU 不空等 (默认开启).
    # wait_for_receipt=true 可回退到旧的同步等确认行为.
    fire = not bool(cfg.get("wait_for_receipt", False))
    labels = {acc.address: f"钱包[{i + 1}]" for i, acc in enumerate(accounts)}
    confirmer = Confirmer(w3, cfg, labels=labels, quiet=quiet) if fire else None
    nonce_mgr = NonceManager() if fire else None
    if fire:
        sim_thr = float(cfg.get("simulate_gas_threshold_gwei", 0.1))
        log(f"提交模式: fire-and-forget  确认后台轮询 {confirmer.poll:.0f}s/次  "
            f"统计汇总每 {confirmer.stats_interval:.0f}s 一次"
            f"{'  (精简日志)' if quiet else ''}", "MINE")
        vlog(f"模拟阈值: 网络 gas > {sim_thr} Gwei 才模拟预检", "MINE")
    else:
        log("提交模式: 同步等确认 (wait_for_receipt=true)", "MINE")

    n_wallets = len(accounts)
    round_num = 0
    wallet_idx = 0   # 当前钱包指针, 只在成功 mint 后才前进
    dead = set()  # BNB 不足、已永久跳过的钱包地址
    total_hashes = 0
    total_mined = 0
    total_sent = 0  # fire-and-forget: 已发出的交易数 (确认结果由后台统计)
    total_skipped = 0  # 提交前模拟拦截、未花 gas 的轮次
    total_gas_spent = 0.0  # 累计 gas 花费 (BNB)
    global_start = time.time()

    # miningTarget 只随 epoch 难度调整变化, 无需每轮重取; 按时间节流刷新.
    target_refresh_secs = float(cfg.get("target_refresh_secs", 60))
    cached_target = None
    last_target_time = 0.0

    def read_balance(addr):
        """fire 模式读后台缓存(每 stats_interval 刷新, 0 额外频率); 未知返回 None.
        同步模式仍实时查. None 一律按'未知'处理, 不据此标 dead, 交由 send 兜底."""
        if fire:
            return confirmer.get_cached_balance(addr)
        try:
            return w3.eth.get_balance(addr)
        except Exception:
            return None

    # --- nonce 楔入自愈 (仅 fire) ---
    # 某钱包待确认堆到阈值时, 对照链上 nonce 判断是"交易被丢弃形成空洞"还是"低价卡在 mempool":
    #   本地超前于链上(含 mempool) -> 交易疑似被丢弃, 回退本地 nonce 即可, 无需花 gas.
    #   mempool 有积压        -> 用更高 gas 发一笔自转账替换最低那笔, 解开堵塞.
    # 按 cooldown 节流, 避免反复发 cancel; 期间该钱包在选择时被临时跳过, 给积压排空时间.
    stuck_threshold = int(cfg.get("nonce_stuck_threshold", 5))
    heal_cooldown = float(cfg.get("nonce_heal_cooldown_secs", 30))
    bump_mult = float(cfg.get("nonce_bump_multiplier", 1.5))
    gas_cap = float(cfg.get("max_gas_price_gwei", 5))
    last_heal = {}  # addr -> 上次自愈时间

    def try_heal(account, idx, cur_gas):
        """返回 True 表示该钱包当前卡住、本轮应跳过 (无论是否真正发了 cancel)."""
        addr = account.address
        if confirmer.pending_for(addr) < stuck_threshold:
            return False
        now = time.time()
        if now - last_heal.get(addr, 0) < heal_cooldown:
            return True  # 冷却中, 仍跳过该钱包, 但不重复操作
        last_heal[addr] = now
        try:
            chain_latest = w3.eth.get_transaction_count(addr, "latest")
            chain_pending = w3.eth.get_transaction_count(addr, "pending")
        except Exception as e:
            log(f"钱包[{idx + 1}] 自愈时读 nonce 失败: {str(e)[:60]}", "WARN")
            return True
        local_next = nonce_mgr.peek(addr)
        if local_next is not None and chain_pending < local_next:
            # 本地超前 => 有交易被丢弃, 本地 nonce 空洞. 回退本地, 下轮正常挖.
            nonce_mgr.set(addr, chain_pending)
            log(f"钱包[{idx + 1}] {addr[:10]}.. nonce 空洞(交易疑似被丢弃), "
                f"本地回退 {local_next}->{chain_pending}, 恢复挖矿", "WARN")
            return False
        if chain_pending > chain_latest:
            # mempool 有卡住的 tx, 最低那笔 nonce = chain_latest. 用 bump gas 自转账替换解楔.
            bump_gwei = min(max(cur_gas * bump_mult, cur_gas + 0.05), gas_cap)
            try:
                cancel = {
                    "from": addr, "to": addr, "value": 0,
                    "nonce": chain_latest, "gas": 21000,
                    "gasPrice": Web3.to_wei(bump_gwei, "gwei"),
                    "chainId": cfg["chain_id"],
                }
                signed = w3.eth.account.sign_transaction(cancel, account.key)
                h = w3.eth.send_raw_transaction(signed.raw_transaction)
                log(f"钱包[{idx + 1}] {addr[:10]}.. nonce {chain_latest} 卡住"
                    f"(待确认 {confirmer.pending_for(addr)}), 已用 {bump_gwei:.3f} Gwei "
                    f"自转账替换解楔: {h.hex()[:18]}..", "WARN")
            except Exception as e:
                log(f"钱包[{idx + 1}] 解楔交易失败(下轮重试): {str(e)[:70]}", "WARN")
            return True  # 本轮仍跳过, 等解楔交易上链
        # chain_pending == chain_latest: mempool 无积压, 纯属确认慢/RPC 抖动, 不动.
        return True

    # --- 每挑战号只提交一次 (仅 fire) ---
    # SAT 每个挑战号全局只能成功 mint 一次; 单 GPU 串行算解, 为同一挑战号多发只会互相
    # revert 烧 gas. 故提交一笔后记住该挑战号, 等它变化再挖下一个.
    one_per_challenge = bool(cfg.get("one_submit_per_challenge", True))
    recheck_before_send = bool(cfg.get("recheck_challenge_before_send", True))
    last_submitted_challenge = None

    def wait_challenge_change(cur, timeout=30.0):
        """轻量轮询 challengeNumber, 直到它 != cur 或超时/中断. 期间 GPU 短暂空闲,
        但本来也不该为已提交的挑战号继续算 doomed 解."""
        step = min(3.0, float(challenge_check_secs))
        waited = 0.0
        while running and waited < timeout:
            _sleep_interruptible(step)
            waited += step
            try:
                if contract.functions.challengeNumber().call() != cur:
                    return True
            except Exception:
                pass
        return False

    while running:
        # 省钱闸门: gas 过高则暂停, 等回落; 返回值直接复用, 不再重复查 eth_gas_price
        proceed, current_gas, net_gas = wait_for_cheap_gas(w3, cfg)
        if not proceed:
            break

        per_tx_wei = cfg["gas_limit"] * Web3.to_wei(current_gas, "gwei")

        # 从当前指针开始, 找第一个"还有钱且未卡住"的钱包.
        account = None
        sel_idx = wallet_idx % n_wallets
        wedged = 0  # 本轮因 nonce 卡住被临时跳过的钱包数 (可恢复, 区别于永久 dead)
        for off in range(n_wallets):
            i = (wallet_idx + off) % n_wallets
            cand = accounts[i]
            if cand.address in dead:
                continue
            bal = read_balance(cand.address)
            if bal is not None and bal < per_tx_wei:
                dead.add(cand.address)
                log(f"钱包[{i + 1}] {cand.address[:10]}... BNB 不足 "
                    f"({Web3.from_wei(bal, 'ether')} < 一次 mint 所需 ~{Web3.from_wei(per_tx_wei, 'ether')}), "
                    f"永久跳过 (剩余可用钱包 {n_wallets - len(dead)})", "WARN")
                continue
            if fire and try_heal(cand, i, current_gas):
                wedged += 1  # 卡住, 本轮跳过, 给积压排空/解楔时间
                continue
            account = cand
            sel_idx = i
            break

        if account is None:
            if wedged > 0:
                # 不是没钱, 是所有可用钱包都暂时卡住; 等待积压排空后重试, 不退出.
                log(f"所有可用钱包暂时卡住(待确认积压, 已尝试自愈), "
                    f"等待 {heal_cooldown:.0f}s 后重试...", "WARN")
                _sleep_interruptible(heal_cooldown)
                continue
            log("所有钱包 BNB 均已不足, 停止挖矿。请充值后重启。", "ERROR")
            break

        wallet_idx = sel_idx  # 停在当前钱包, 直到它成功才前进
        round_num += 1
        miner_addr = account.address
        addr_bytes = bytes.fromhex(miner_addr[2:])

        vlog("=" * 55, "MINE")
        wtag = f"  钱包[{sel_idx + 1}/{n_wallets}] {miner_addr[:10]}..." if n_wallets > 1 else ""
        vlog(f"第 {round_num} 轮挖矿开始  (GPU){wtag}", "MINE")
        net_str = f"{net_gas:.3f}" if net_gas is not None else "?"
        vlog(f"本轮 gas: {current_gas:.3f} Gwei  (网络实时: {net_str} Gwei)", "MINE")
        vlog("=" * 55, "MINE")

        if not quiet:
            show_status(w3, contract, miner_addr)

        vlog("获取挑战参数...")
        try:
            challenge = contract.functions.challengeNumber().call()
            # 难度目标按节流刷新 (随 epoch 才变), 平时复用缓存, 省一次/轮 RPC
            now = time.time()
            if cached_target is None or now - last_target_time >= target_refresh_secs:
                cached_target = contract.functions.miningTarget().call()
                last_target_time = now
            target = cached_target
        except Exception as e:
            if _is_network_error(e):
                log(f"读取挑战参数网络出错: {str(e)[:80]}", "WARN")
                log("等待 10s 后重连 RPC 重试 (不退出)...", "WARN")
                _sleep_interruptible(10)
                if not running:
                    break
                nw3, nctr = reconnect(cfg)
                if nw3 is None:
                    break  # Ctrl+C
                w3, contract = nw3, nctr
                if confirmer is not None:
                    confirmer.update_w3(w3)
                round_num -= 1  # 本轮没真正开始, 轮次号回退
                continue
            raise  # 非网络错误(逻辑/合约问题)照常抛出, 便于发现真 bug
        vlog(f"挑战号: {challenge.hex()[:36]}...")
        vlog(f"目标值: {target}")

        # 每挑战号只提交一次: 已为当前挑战号提交过, 就不再为它空算/重复提交
        # (该挑战号全局只能成功 1 笔, 多发只会互相 revert 烧 gas). 等它变化再挖.
        if fire and one_per_challenge and challenge == last_submitted_challenge:
            vlog("已为当前挑战号提交过, 等待挑战号更新后再挖...", "MINE")
            wait_challenge_change(challenge)
            continue

        prefix = challenge + addr_bytes
        base_nonce = random.getrandbits(64)

        round_start = time.time()
        found, round_hashes, abandoned = gpu_search_round(
            gpu, prefix, target, base_nonce,
            w3, contract, challenge, log_interval, challenge_check_secs, quiet)

        total_hashes += round_hashes

        if found and running:
            nonce_val, digest = found
            found_at = time.time()  # 找到解的时刻, 用于度量"找到解→进块"端到端延迟
            recheck_ms = None
            elapsed = found_at - round_start
            rate = round_hashes / elapsed if elapsed > 0 else 0
            vlog("*" * 55, "OK")
            vlog("找到有效解!", "OK")
            vlog(f"  Nonce   : {nonce_val}", "OK")
            vlog(f"  Digest  : {digest.hex()}", "OK")
            vlog(f"  本轮哈希: {round_hashes}", "OK")
            vlog(f"  耗时    : {elapsed:.1f}s", "OK")
            vlog(f"  本轮算力: {fmt_hashrate(rate)}", "OK")
            vlog("*" * 55, "OK")

            if fire:
                # 发送前再查一次挑战号: GPU grind 期间(1~3s)若挑战号已被他人/另一进程抢先
                # mint 掉, 此刻提交必 revert 烧 gas. 便宜 gas 下我们跳过了完整模拟, 故这里用
                # 一次轻量 challengeNumber 比对兜底, 变了就跳过不发 (0 gas).
                if recheck_before_send:
                    _rck0 = time.time()
                    try:
                        changed = contract.functions.challengeNumber().call() != challenge
                        recheck_ms = (time.time() - _rck0) * 1000.0
                        if changed:
                            total_skipped += 1
                            confirmer.note_skip(miner_addr)
                            vlog(f"发送前挑战号已变(被抢先), 跳过提交 (0 gas)  "
                                 f"[recheck {recheck_ms:.0f}ms]", "MINE")
                            continue
                    except Exception:
                        recheck_ms = (time.time() - _rck0) * 1000.0
                        pass  # 查询失败就照常尝试发送, 不因 RPC 抖动错过机会

                # --- fire-and-forget: 发出即返回, 立刻乐观轮换, GPU 不空等 ---
                res = None
                err = False
                try:
                    res = send_mint(w3, contract, account, cfg, nonce_val, digest,
                                    current_gas, net_gas, nonce_mgr)
                except Exception as e:
                    err = True
                    msg = str(e)
                    if "insufficient funds" in msg.lower() or "余额" in msg:
                        dead.add(miner_addr)
                        log(f"钱包[{sel_idx + 1}] {miner_addr[:10]}... BNB 不足, 永久跳过 "
                            f"(剩余可用钱包 {n_wallets - len(dead)})", "WARN")
                    elif "nonce" in msg.lower() or "underpriced" in msg.lower() \
                            or "already known" in msg.lower():
                        # nonce 漂移 (上一笔尚未被 RPC 计入 / 顶替): 重新同步, 下轮重试
                        new_n = nonce_mgr.resync(w3, miner_addr)
                        log(f"nonce 冲突, 已重新同步为 {new_n}: {msg[:80]}", "WARN")
                    elif _is_network_error(e):
                        # 429 限流 / 节点抖动: 退避并重连, 而不是以原频率继续猛打
                        log(f"发送交易网络出错(限流/抖动?), 退避重连: {msg[:80]}", "WARN")
                        _sleep_interruptible(5)
                        if running:
                            nw3, nctr = reconnect(cfg)
                            if nw3 is not None:
                                w3, contract = nw3, nctr
                                confirmer.update_w3(w3)
                    else:
                        log(f"发送交易异常: {e}", "ERROR")

                if res is None:
                    if not err:
                        # 模拟预检拦截 (已被抢先), 未发送, 0 gas
                        total_skipped += 1
                        confirmer.note_skip(miner_addr)
                        vlog("本轮被抢先, 已跳过提交 (0 gas)，进入下一轮", "MINE")
                    # err 情形上面已各自打印, 不重复计数; 直接进入下一轮
                else:
                    tx_hash, tx_nonce, send_ms = res
                    total_sent += 1
                    last_submitted_challenge = challenge  # 该挑战号已出手, 不再重复提交
                    confirmer.submit(tx_hash, miner_addr, current_gas, tx_nonce,
                                     found_at=found_at, send_ms=send_ms,
                                     recheck_ms=recheck_ms)
                    vlog(f"已发出 (fire-and-forget) nonce={tx_nonce} tx={tx_hash.hex()[:18]}.. "
                         f"[send {send_ms:.0f}ms]", "OK")
                    if n_wallets > 1:
                        wallet_idx = (sel_idx + 1) % n_wallets  # 发出即轮换 (乐观)
                        nxt = accounts[wallet_idx].address
                        vlog(f"钱包[{sel_idx + 1}] 已发出, 轮换到 钱包[{wallet_idx + 1}] {nxt[:10]}...", "MINE")
                    if not cfg.get("auto_restart", True):
                        log("auto_restart 已关闭, 等待后台确认在途交易后退出...")
                        confirmer.join_drain()
                        return
                # GPU 立刻进入下一轮, 不 sleep, 确认在后台进行
                continue

            # --- 同步等确认 (wait_for_receipt=true, 旧行为) ---
            try:
                ok = submit_mint(w3, contract, account, cfg, nonce_val, digest, current_gas)
            except Exception as e:
                msg = str(e)
                if "insufficient funds" in msg.lower() or "余额" in msg:
                    dead.add(miner_addr)
                    log(f"钱包[{sel_idx + 1}] {miner_addr[:10]}... BNB 不足, 永久跳过 "
                        f"(剩余可用钱包 {n_wallets - len(dead)})", "WARN")
                else:
                    log(f"提交交易异常: {e}", "ERROR")
                ok = False

            if ok:
                total_mined += 1
                total_gas_spent += 92000 * current_gas * 1e-9  # 约略累计 (BNB)
                te = time.time() - global_start
                avg = total_hashes / te if te > 0 else 0
                log(f"累计统计: 已挖 {total_mined} 次  跳过(省gas) {total_skipped}  总哈希 {total_hashes}  平均算力 {fmt_hashrate(avg)}  运行 {te:.0f}s", "OK")
                log(f"累计 gas 花费: ~{total_gas_spent:.6f} BNB", "OK")
                if n_wallets > 1:
                    wallet_idx = (sel_idx + 1) % n_wallets  # 成功后切到下一个钱包
                    nxt = accounts[wallet_idx].address
                    log(f"钱包[{sel_idx + 1}] 成功, 轮换到 钱包[{wallet_idx + 1}] {nxt[:10]}...", "MINE")
                if not cfg.get("auto_restart", True):
                    log("auto_restart 已关闭，退出。")
                    return
                log("自动重新开始挖矿...", "MINE")
            elif ok is None:
                # 提交前模拟拦截, 没花 gas
                total_skipped += 1
                log("本轮被抢先但已跳过提交 (0 gas)，进入下一轮", "MINE")
            else:
                log("本轮失败 (被抢先, 已付 gas)，直接进入下一轮 (不提价)", "WARN")
                time.sleep(2)
        elif not abandoned and not running:
            break  # Ctrl+C


def main():
    global running

    def handle_signal(sig, frame):
        global running
        if running:
            log("收到中断信号，正在停止...", "WARN")
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    cfg = load_config()

    print()
    log("=" * 55, "MINE")
    log("  SAT (Satoshi) PoW GPU 自动挖矿程序", "MINE")
    log("  合约: 0x14Dc...906a0  链: BSC Mainnet", "MINE")
    log("=" * 55, "MINE")
    print()

    w3, accounts, contract = connect(cfg)
    log(f"钱包数量: {len(accounts)}{'  (多钱包轮换)' if len(accounts) > 1 else ''}")

    max_bal = 0
    for i, acc in enumerate(accounts):
        bal = w3.eth.get_balance(acc.address)
        max_bal = max(max_bal, bal)
        log(f"  钱包[{i + 1}] {acc.address}  {Web3.from_wei(bal, 'ether')} BNB")

    if cfg.get("use_network_gas", True):
        _, net = get_gas_price(w3, cfg)
        net_str = f"{net:.3f}" if net is not None else "?"
        log(f"Gas 模式: 跟随网络 x{cfg.get('network_gas_multiplier', 1.2)} "
            f"(下限 {cfg.get('min_gas_price_gwei', 0.1)} / 上限 {cfg.get('max_gas_price_gwei', 5)} Gwei)  "
            f"当前网络: {net_str} Gwei")
    else:
        log(f"Gas 模式: 固定 {cfg['gas_price_gwei']} Gwei")
    thr = float(cfg.get("mine_only_below_gwei", 0) or 0)
    if thr > 0:
        log(f"省钱闸门: 仅在网络 gas <= {thr} Gwei 时挖矿, 超过则暂停 (每 {cfg.get('gas_recheck_secs', 15)}s 重查)")
    else:
        log("省钱闸门: 关闭 (任何 gas 都挖)")
    log(f"自动重启: {'是' if cfg.get('auto_restart', True) else '否'}  日志间隔: {cfg.get('log_interval', 10)}s")

    # 初始化 GPU 引擎
    try:
        gpu = GpuMiner(cfg)
    except Exception as e:
        log(f"GPU 初始化失败: {e}", "ERROR")
        log("请确认已 pip install -r requirements-gpu.txt, 且本机有可用 OpenCL/Metal 设备。", "ERROR")
        sys.exit(1)
    log(f"GPU 设备: {gpu.device_name}  batch={gpu.batch_size}  目标占用: {gpu.target_util:.0f}%")

    # 门槛按实际 gas 成本估算 (单次 tx 最坏成本 × 3 作为缓冲)
    eff_gas, _ = get_gas_price(w3, cfg)
    per_tx_wei = cfg["gas_limit"] * Web3.to_wei(eff_gas, "gwei")
    min_needed = per_tx_wei * 3
    if max_bal < min_needed:
        log(f"所有钱包 BNB 余额都不足 (需 ~{Web3.from_wei(min_needed, 'ether')} BNB, "
            f"约 3 次 mint 的 gas)", "ERROR")
        sys.exit(1)
    runway = max_bal // per_tx_wei
    log(f"余额可支撑约 {runway} 次 mint (按当前 gas {eff_gas:.3f} Gwei 估算)")

    print()
    mine_loop(w3, contract, accounts, cfg, gpu)
    print()
    log("挖矿程序已退出。")


if __name__ == "__main__":
    main()
