@echo off
chcp 65001 > nul
echo ================================================
echo   SnapFloat 截图工具 - Windows 一键打包脚本
echo ================================================
echo.

REM 检查 Python
python --version > nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] 安装依赖库...
pip install PyQt5 pywin32 Pillow pyinstaller --quiet
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)

echo [2/4] 生成软件图标...
python make_icon.py
if errorlevel 1 (
    echo [错误] 图标生成失败
    pause
    exit /b 1
)

echo [3/4] 编译打包中（请稍候约1-2分钟）...
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "SnapFloat截图工具" ^
    --icon app.ico ^
    --hidden-import win32api ^
    --hidden-import win32con ^
    --hidden-import win32event ^
    --hidden-import winerror ^
    --hidden-import winreg ^
    --add-data "snapfloat.py;." ^
    snapfloat.py

if errorlevel 1 (
    echo [错误] 打包失败，请查看上方错误信息
    pause
    exit /b 1
)

echo [4/4] 完成！
echo.
echo ================================================
echo   程序已生成：dist\SnapFloat截图工具.exe
echo ================================================
echo.
echo 使用说明：
echo   - 双击 .exe 即可运行，程序会出现在系统托盘
echo   - 首次运行自动设置开机自启动
echo   - 快捷键：Ctrl+Alt+A 局部截图，Ctrl+Alt+F 全屏截图
echo   - 右键托盘图标 → 退出程序
echo.
pause
