# Satoshi Miner v3.0 — 反应式挖矿版

整合了测试安装包的**全部挖矿规则**，带 GUI 桌面界面，支持一键编译为 Windows .exe 安装包。

## 核心挖矿规则 (全部来自测试安装包)

| 规则 | 说明 |
|------|------|
| **WebSocket Mint 事件订阅** | 零轮询检测新挑战号，对手一 mint 进块，推送瞬间拿到下一轮挑战号 |
| **CPU 常驻热池** | 多进程常驻预热，挑战号一变立刻切换，零冷启动 |
| **GPU OpenCL 求解器** | 高难度时 GPU 比 CPU 快得多，支持占用率控制 (温控) |
| **多 Relay 并行广播** | 同一签名交易并行发往 bloXroute / 48 Club 等直投验证者 |
| **Gas 跟网络地板价** | 不加价，与对手一致，省钱 |
| **自动 detect 模式** | 先试 logs-WS，连续失败自动退到 heads 模式 |
| **过期解自动丢弃** | 挑战号被新的取代时，旧解不发，省 gas |
| **DRY_RUN 试运行** | 只算解+计时不广播不花 gas，安全观察 |
| **离线签名+本地 nonce** | 无 RPC 往返，签名后直接广播 |
| **难度/gas 自动刷新** | 后台周期刷新 target/难度/gas，nonce 防漂移 |

## 文件清单

| 文件 | 作用 |
|------|------|
| `satoshi_miner.py` | 主程序 (GUI + 反应式挖矿引擎) |
| `gpu_miner.py` | GPU OpenCL 内核 (被主程序调用) |
| `config.yaml` | 配置文件 (**记得填私钥**) |
| `keccak_pow.c` + `setup.py` | C 加速扩展源码 |
| `requirements.txt` | Python 依赖清单 |
| `build.bat` | **一键编译 .exe** |
| `icon.ico` / `icon_circle.png` | 图标 |

## 编译 Windows .exe 安装包

### 前置条件
- Windows 10/11
- Python 3.10+ (64位)，安装时勾选 "Add Python to PATH"
- (可选) NVIDIA 显卡驱动 (GPU 模式需要)
- (可选) Visual Studio Build Tools (C 加速扩展需要)

### 一键编译

**双击 `build.bat`** 即可，它会自动：
1. 安装所有 Python 依赖
2. 编译 C 加速扩展 (失败不影响，自动退回 Python 模式)
3. 用 PyInstaller 打包为单个 `SatoshiMiner.exe`

编译完成后，`dist\SatoshiMiner.exe` 就是最终的安装包文件。

### 使用方法
1. 双击 `SatoshiMiner.exe` 直接运行
2. 在界面填写私钥，点击"连接钱包"
3. 切换到"挖矿"页，点击"开始挖矿"
4. 可以把 `SatoshiMiner.exe` 发给别人，直接安装直接使用

### 高级配置 (可选)

编辑 `config.yaml` 可调整：
- `solver`: `cpu` 或 `gpu` (默认 cpu)
- `gpu_util`: GPU 占用率 1-100 (默认 100)
- `gpu_batch_size`: GPU 每批 nonce 数 (3070 建议 8M-32M)
- `relay_urls`: 自定义 relay 节点
- `ws_urls`: 自定义 WebSocket 节点
- `detect_mode`: `auto` / `logs` / `heads`
- `dry_run`: `true` 试运行不花 gas
- `verbose_logs`: `true` 打印全部细节
