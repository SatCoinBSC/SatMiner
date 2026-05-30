# Satoshi (SAT) Miner - BSC PoW Mining Client

A desktop GUI application for mining the Satoshi (SAT) Proof-of-Work ERC20 token on BSC.

## Contract Info
- **Contract**: `0x14Dc4b4929c664534f1d4D64107d8F36CbF906a0`
- **Network**: BSC (Binance Smart Chain)
- **Total Supply**: 21,000,000 SAT
- **Decimals**: 8
- **Mining Reward**: 50 SAT (halves each era)

---

## How to Build the .exe on Windows

### Prerequisites
- **Python 3.10+** installed and added to PATH
  - Download: https://www.python.org/downloads/
  - During installation, check "Add Python to PATH"

### Steps
1. Download and extract this folder to your Windows PC
2. Double-click `build.bat`
3. Wait for the build to complete
4. Find `SatoshiMiner.exe` in the `dist/` folder
5. Copy `SatoshiMiner.exe` to any location and run it

### Manual Build (if .bat doesn't work)
```
pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed --name "SatoshiMiner" --collect-all web3 --collect-all eth_abi --collect-all eth_account --hidden-import eth_hash.auto --hidden-import eth_hash.backends.pycryptodome --hidden-import cytoolz satoshi_miner.py
```

---

## C 扩展加速安装指南 (重要! 提速 5-10 倍)

### 快速诊断
双击 `diagnose.bat`，查看你的环境状态和当前算力。

### 安装步骤

**第一步：安装 Visual Studio Build Tools (C 编译器)**

Windows 默认没有 C 编译器，需要装一个：

方法 A - 命令行安装 (推荐)：
1. 右键开始菜单 → "Windows Terminal (管理员)" 或 "PowerShell (管理员)"
2. 运行：`winget install Microsoft.VisualStudio.2022.BuildTools --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"`
3. 等待安装完成 (约 2-5GB 下载)
4. **重启电脑**

方法 B - 手动安装：
1. 打开 https://visualstudio.microsoft.com/visual-cpp-build-tools/
2. 下载 "Build Tools for Visual Studio 2022"
3. 安装时勾选 **"使用 C++ 的桌面开发"**
4. **重启电脑**

**第二步：编译 C 扩展**
双击 `install_c_extension.bat`，等待编译完成。

**第三步：验证**
双击 `diagnose.bat`，看到以下内容说明成功：
```
[3] keccak_pow C 扩展:
    [OK] C 扩展已加载 - 挖矿将使用 5-10 倍加速
```

### 常见问题

**Q: install_c_extension.bat 说找不到编译器？**
A: 从开始菜单找到 "x64 Native Tools Command Prompt for VS 2022"，在那个窗口里 cd 到矿机目录再运行脚本。

**Q: 装了 Build Tools 但还是不行？**
A: 重启电脑后重试。

**Q: 不想装 Build Tools 怎么办？**
A: 矿机仍然可以用，只是会用 pycryptodome 的 Python 版本，速度慢 5-10 倍。

---

## How to Use

1. **Launch** `SatoshiMiner.exe` (or run `python satoshi_miner.py`)
2. **Enter RPC URL** - Default is BSC mainnet. You can change to any BSC RPC:
   - `https://bsc-dataseed1.binance.org`
   - `https://bsc-dataseed2.binance.org`
   - `https://bsc-dataseed3.binance.org`
   - `https://bsc-dataseed4.binance.org`
   - Or your own private node
3. **Enter Private Key** - Your BSC wallet private key (needed to sign mint transactions)
4. Click **Connect**
5. Click **Start Mining**

### Features
- Real-time hashrate display
- BNB and SAT balance display
- Mining difficulty and reward info
- Mining history with TX hashes
- Configurable gas price and gas limit
- Auto-submit solutions to the blockchain

### Important Notes
- You need some BNB in your wallet to pay for gas fees when submitting mining solutions
- Mining is CPU-based (keccak256 hashing)
- Your private key is never saved to disk
- The gas price default is 5 Gwei (standard for BSC)
