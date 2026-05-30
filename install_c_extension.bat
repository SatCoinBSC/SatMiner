@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1
title Satoshi Miner - C 扩展加速安装工具
cd /d "%~dp0"

echo.
echo ============================================================
echo   Satoshi Miner - C 扩展加速安装工具
echo   安装成功后挖矿速度提升 5-10 倍
echo ============================================================
echo.

REM === Step 1: 检查 Python ===
echo [步骤 1/4] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [错误] 未检测到 Python！
    echo   请先安装 Python 3.10+，安装时勾选 "Add Python to PATH"
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   Python 版本: %%v [OK]

REM 检测 Python 是 32 位还是 64 位
set "PY_ARCH=64"
python -c "import struct; print(struct.calcsize('P')*8)" 2>nul | findstr "32" >nul && set "PY_ARCH=32"
echo   Python 架构: !PY_ARCH! 位
echo.

REM === Step 2: 检查并加载 C 编译器 ===
echo [步骤 2/4] 检查 C 编译器...

REM 先检查 cl.exe 是否可用且架构匹配
where cl >nul 2>&1
if not errorlevel 1 (
    echo   [OK] cl.exe 已在 PATH 中
    goto :compiler_ready
)

echo   cl.exe 不在 PATH 中，正在搜索 Visual Studio 环境...

REM 根据 Python 架构选择 vcvars 脚本
if "!PY_ARCH!"=="64" (
    set "VCVARS_NAME=vcvars64.bat"
    set "VCVARS_FALLBACK=vcvarsamd64_x86.bat"
) else (
    set "VCVARS_NAME=vcvars32.bat"
    set "VCVARS_FALLBACK=vcvars32.bat"
)

set "FOUND_VS="

REM --- 搜索方法1: vswhere (最可靠) ---
for %%V in (
    "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    "C:\Program Files\Microsoft Visual Studio\Installer\vswhere.exe"
) do (
    if exist %%V (
        for /f "delims=" %%p in ('"%%~V" -latest -property installationPath 2^>nul') do (
            if exist "%%p\VC\Auxiliary\Build\!VCVARS_NAME!" (
                set "FOUND_VS=%%p\VC\Auxiliary\Build\!VCVARS_NAME!"
            ) else if exist "%%p\VC\Auxiliary\Build\vcvarsall.bat" (
                set "FOUND_VS=%%p\VC\Auxiliary\Build\vcvarsall.bat"
            )
        )
    )
)

REM --- 搜索方法2: 手动遍历常见路径 ---
if "!FOUND_VS!"=="" (
    for %%d in (
        "C:\Program Files\Microsoft Visual Studio"
        "C:\Program Files (x86)\Microsoft Visual Studio"
    ) do (
        for %%y in (2022 2019 2017) do (
            for %%e in (BuildTools Community Professional Enterprise) do (
                if "!FOUND_VS!"=="" (
                    set "BASE=%%~d\%%y\%%e\VC\Auxiliary\Build"
                    if exist "!BASE!\!VCVARS_NAME!" (
                        set "FOUND_VS=!BASE!\!VCVARS_NAME!"
                    ) else if exist "!BASE!\vcvarsall.bat" (
                        set "FOUND_VS=!BASE!\vcvarsall.bat"
                    )
                )
            )
        )
    )
)

if "!FOUND_VS!"=="" (
    echo.
    echo   [错误] 未找到 Visual Studio Build Tools
    echo   请安装后重启电脑再运行本脚本。
    echo   下载: https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

echo   [发现] !FOUND_VS!
echo   正在加载 !PY_ARCH! 位编译器环境...

REM 根据找到的是 vcvarsall 还是 vcvarsXX 来调用
echo "!FOUND_VS!" | findstr /i "vcvarsall" >nul
if not errorlevel 1 (
    if "!PY_ARCH!"=="64" (
        call "!FOUND_VS!" amd64 >nul 2>&1
    ) else (
        call "!FOUND_VS!" x86 >nul 2>&1
    )
) else (
    call "!FOUND_VS!" >nul 2>&1
)

where cl >nul 2>&1
if errorlevel 1 (
    echo   [失败] 加载编译器环境后仍找不到 cl.exe
    echo.
    echo   请从开始菜单搜索并打开:
    if "!PY_ARCH!"=="64" (
        echo     "x64 Native Tools Command Prompt for VS 2022"
    ) else (
        echo     "x86 Native Tools Command Prompt for VS 2022"
    )
    echo   然后在那个窗口中运行:
    echo     cd /d "%cd%"
    echo     python setup.py build_ext --inplace
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

echo   [OK] 编译器加载成功

REM 验证编译器架构
for /f "tokens=*" %%a in ('cl 2^>^&1 ^| findstr /i "x64 x86 amd64 ARM"') do echo   编译器信息: %%a

:compiler_ready
echo.

REM === Step 3: 安装 Python 依赖 ===
echo [步骤 3/4] 安装 Python 依赖...
python -m pip install setuptools wheel >nul 2>&1
echo   [OK]
echo.

REM === Step 4: 编译 C 扩展 ===
echo [步骤 4/4] 编译 keccak_pow C 扩展...
echo.

if not exist "setup.py" (
    echo   [错误] 找不到 setup.py！
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)
if not exist "keccak_pow.c" (
    echo   [错误] 找不到 keccak_pow.c！
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

python setup.py build_ext --inplace
if errorlevel 1 (
    echo.
    echo   [编译失败]
    echo   请从开始菜单搜索并打开:
    if "!PY_ARCH!"=="64" (
        echo     "x64 Native Tools Command Prompt for VS 2022"
    ) else (
        echo     "x86 Native Tools Command Prompt for VS 2022"
    )
    echo   然后运行:
    echo     cd /d "%cd%"
    echo     python setup.py build_ext --inplace
    echo.
    echo 按任意键退出...
    pause >nul
    exit /b 1
)

echo.
echo ============================================================
echo   [成功] C 扩展编译完成！
echo ============================================================
echo.
echo 正在验证...
python -c "import keccak_pow; print('  [验证通过] keccak_pow 模块加载成功！')" 2>nul
if errorlevel 1 (
    echo   [警告] 编译成功但加载失败，请检查 Python 版本。
) else (
    echo.
    echo   现在运行 satoshi_miner.py 即可享受 5-10 倍加速！
)

echo.
echo 按任意键退出...
pause >nul
