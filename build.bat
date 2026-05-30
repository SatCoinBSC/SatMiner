@echo off
cd /d "%~dp0"
echo ==========================================
echo   Satoshi Miner v2.3.0 - Build Script
echo   (with C Extension Acceleration)
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

echo [1/4] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo [2/4] Building C extension (keccak_pow)...
echo        This provides 5-10x mining speedup.
python setup.py build_ext --inplace
if errorlevel 1 (
    echo [WARNING] C extension build failed. Mining will use Python fallback.
    echo          To enable C acceleration, install Visual Studio Build Tools.
    echo.
) else (
    echo [OK] C extension built successfully!
    echo.
)

echo [3/4] Building .exe with PyInstaller...
REM Check if keccak_pow.pyd exists and include it
set KECCAK_DATA=
if exist keccak_pow*.pyd (
    for %%f in (keccak_pow*.pyd) do set KECCAK_DATA=--add-binary "%%f;."
    echo        Including C extension in build...
)

python -m PyInstaller --noconfirm --onefile --windowed ^
    --name "SatoshiMiner" ^
    --icon "icon.ico" ^
    --add-data "icon_circle.png;." ^
    --add-data "icon.ico;." ^
    %KECCAK_DATA% ^
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
    --hidden-import "requests" ^
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
echo [4/4] Build complete!
echo.
echo ==========================================
echo   EXE file is at: dist\SatoshiMiner.exe
echo ==========================================
echo.
pause
