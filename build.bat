@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   Satoshi Miner v3.0 - 一键编译安装包
echo   (反应式挖矿 + GPU/CPU + 多 Relay)
echo ==========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装或未加入 PATH.
    echo 请安装 Python 3.10+ : https://www.python.org/downloads/
    echo 安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo [1/4] 安装依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败.
    pause
    exit /b 1
)

echo.
echo [2/4] 编译 C 加速扩展 (keccak_pow)...
echo        可提供 5-10 倍挖矿加速.
python setup.py build_ext --inplace
if errorlevel 1 (
    echo [提示] C 扩展编译失败, 不影响使用, 会自动退回 Python 模式.
    echo        如需加速, 请安装 Visual Studio Build Tools.
    echo.
) else (
    echo [OK] C 扩展编译成功!
    echo.
)

echo [3/4] 打包 .exe 安装文件...

REM 构建 PyInstaller 命令参数
set PYINST_ARGS=--noconfirm --onefile --windowed --name "SatoshiMiner" --icon "icon.ico"
set PYINST_ARGS=%PYINST_ARGS% --add-data "icon_circle.png;." --add-data "icon.ico;."

REM 检查 C 扩展
if exist keccak_pow*.pyd (
    for %%f in (keccak_pow*.pyd) do set PYINST_ARGS=%PYINST_ARGS% --add-binary "%%f;."
    echo        包含 C 加速扩展...
)

REM 检查 GPU 模块
if exist gpu_miner.py (
    set PYINST_ARGS=%PYINST_ARGS% --add-data "gpu_miner.py;."
    echo        包含 GPU 挖矿模块...
)

REM 检查 config.yaml
if exist config.yaml (
    set PYINST_ARGS=%PYINST_ARGS% --add-data "config.yaml;."
    echo        包含默认配置文件...
)

set PYINST_ARGS=%PYINST_ARGS% --hidden-import "web3" --hidden-import "eth_abi" --hidden-import "eth_abi.packed"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "eth_account" --hidden-import "eth_utils" --hidden-import "eth_typing"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "eth_hash.auto" --hidden-import "eth_hash.backends.pycryptodome"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "Crypto.Hash.keccak" --hidden-import "Crypto.Hash"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "cytoolz" --hidden-import "cytoolz.utils" --hidden-import "cytoolz._signatures"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "PIL" --hidden-import "multiprocessing" --hidden-import "multiprocessing.pool"
set PYINST_ARGS=%PYINST_ARGS% --hidden-import "requests" --hidden-import "yaml" --hidden-import "websockets" --hidden-import "asyncio"
set PYINST_ARGS=%PYINST_ARGS% --collect-all "web3" --collect-all "eth_abi" --collect-all "eth_account" --collect-all "websockets"

python -m PyInstaller %PYINST_ARGS% satoshi_miner.py

if errorlevel 1 (
    echo [错误] 打包失败.
    pause
    exit /b 1
)

echo.
echo [4/4] 打包完成!
echo.
echo ==========================================
echo   EXE 文件位置: dist\SatoshiMiner.exe
echo ==========================================
echo.
echo   使用方法:
echo   1. 双击 dist\SatoshiMiner.exe 即可运行
echo   2. 可以把 SatoshiMiner.exe 发给别人直接使用
echo   3. 首次运行需在界面填写私钥并连接钱包
echo   4. 如有 config.yaml 会自动读取配置
echo.
pause
