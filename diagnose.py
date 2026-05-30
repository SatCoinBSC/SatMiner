# -*- coding: utf-8 -*-
"""Satoshi Miner 环境诊断工具"""
import os, sys, time, random

print()
print("=" * 60)
print("  Satoshi Miner - 环境诊断工具")
print("  检查你的挖矿环境是否配置正确")
print("=" * 60)
print()

# [1] Python
print(f"[1] Python 版本: {sys.version}")
print("    [OK]")
print()

# [2] C 编译器
print("[2] C 编译器 (cl.exe):")
ret = os.system("where cl >nul 2>&1")
if ret != 0:
    print("    [X] 未找到 cl.exe")
    print("    -> 需要安装 Visual Studio Build Tools")
    print("    -> 或从 'x64 Native Tools Command Prompt' 运行")
else:
    print("    [OK] 编译器可用")
print()

# [3] keccak_pow C 扩展
print("[3] keccak_pow C 扩展:")
try:
    import keccak_pow
    print("    [OK] C 扩展已加载 - 挖矿将使用 5-10 倍加速")
    has_c = True
except ImportError:
    print("    [X] C 扩展未安装")
    print("    -> 运行 install_c_extension.bat 来安装")
    has_c = False
print()

# [4] Keccak 引擎
print("[4] Keccak 引擎检测:")
if has_c:
    print("    -> 引擎: C-Extension (keccak_pow) [最快]")
else:
    try:
        from Crypto.Hash import keccak
        print("    -> 引擎: pycryptodome [中等]")
    except ImportError:
        try:
            import sha3
            print("    -> 引擎: pysha3 [中等]")
        except ImportError:
            print("    -> 引擎: web3 fallback [最慢!]")
print()

# [5] Python 依赖
print("[5] Python 依赖:")
deps = [
    ("web3", "from web3 import Web3"),
    ("eth-account", "from eth_account import Account"),
    ("pycryptodome", "from Crypto.Hash import keccak"),
    ("Pillow", "from PIL import Image"),
    ("requests", "import requests"),
]
for name, imp in deps:
    try:
        exec(imp)
        print(f"    {name:15s} [OK]")
    except Exception:
        print(f"    {name:15s} [X] 未安装")
print()

# [6] CPU
print(f"[6] CPU 核心数: {os.cpu_count()}")
print()

# [7] 性能测试
print("[7] 快速性能测试 (3 秒)...")
try:
    if has_c:
        import keccak_pow
        prefix = os.urandom(52)
        target = b'\xff' * 32
        start = time.monotonic()
        count = 0
        while time.monotonic() - start < 3.0:
            keccak_pow.pow_search(prefix, target, random.randint(0, 2**64), 100000)
            count += 100000
        elapsed = time.monotonic() - start
        rate = count / elapsed
        cores = os.cpu_count() or 1
        print(f"    C 扩展单核: {rate:,.0f} H/s")
        print(f"    预估全部 {cores} 核: {rate * cores:,.0f} H/s")
    else:
        try:
            from Crypto.Hash import keccak as _k
            start = time.monotonic()
            count = 0
            data = os.urandom(84)
            while time.monotonic() - start < 3.0:
                _k.new(digest_bits=256, data=data).digest()
                count += 1
            elapsed = time.monotonic() - start
            rate = count / elapsed
            cores = os.cpu_count() or 1
            print(f"    Python (pycryptodome) 单核: {rate:,.0f} H/s")
            print(f"    预估全部 {cores} 核: {rate * cores:,.0f} H/s")
            print(f"    [提示] 安装 C 扩展可再提升 5-10 倍!")
        except Exception:
            print("    [跳过] 无法进行性能测试")
except Exception as e:
    print(f"    [跳过] 测试出错: {e}")
print()

print("=" * 60)
print("  诊断完成")
print("=" * 60)
print()
input("按回车键退出...")
