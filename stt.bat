@echo off
chcp 65001 >nul
setlocal

rem 切到 bat 所在的專案目錄，讓 uv 與 .env 都能正確載入
rem 音檔路徑一律用 %~f1 展開成絕對路徑，所以音檔可以放在任何地方
cd /d "%~dp0"

if "%~1"=="" (
    echo 用法: 把音檔直接拖曳到 stt.bat 上面
    echo.
    pause
    exit /b 1
)

:next_file
if "%~1"=="" goto finished

echo.
echo === 以 stt 開啟 %~nx1 ===
echo 檔案路徑: %~f1
echo.

uv run stt "%~f1"
if errorlevel 1 echo [失敗] %~nx1

shift
goto next_file

:finished
echo.
echo 全部處理完畢
pause
