@echo off
echo ==========================================
echo   Satoshi Miner - Build Script
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/3] Building .exe with PyInstaller...
python -m PyInstaller --noconfirm --onefile --windowed ^
    --name "SatoshiMiner" ^
    --icon "icon.ico" ^
    --add-data "icon_circle.png;." ^
    --add-data "icon.ico;." ^
    --hidden-import "web3" ^
    --hidden-import "eth_abi" ^
    --hidden-import "eth_abi.packed" ^
    --hidden-import "eth_account" ^
    --hidden-import "eth_utils" ^
    --hidden-import "eth_typing" ^
    --hidden-import "eth_hash.auto" ^
    --hidden-import "eth_hash.backends.pycryptodome" ^
    --hidden-import "Crypto.Hash.keccak" ^
    --hidden-import "Crypto.Hash" ^
    --hidden-import "cytoolz" ^
    --hidden-import "cytoolz.utils" ^
    --hidden-import "cytoolz._signatures" ^
    --hidden-import "PIL" ^
    --hidden-import "multiprocessing" ^
    --hidden-import "multiprocessing.pool" ^
    --collect-all "web3" ^
    --collect-all "eth_abi" ^
    --collect-all "eth_account" ^
    satoshi_miner.py

if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Build complete!
echo.
echo ==========================================
echo   EXE file is at: dist\SatoshiMiner.exe
echo ==========================================
echo.
pause
