@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo ===================================================
echo     Nong Unjai - Background Channel Processor
echo ===================================================
echo.

:: กำหนด URL ผ่าน Command Line Argument หรือกรอกในช่องรับข้อมูล
set CHANNEL_URL=%~1

if "%CHANNEL_URL%"=="" (
    set /p "CHANNEL_URL=👉 ใส่ URL ของ YouTube Channel ที่นี่: "
)

if "%CHANNEL_URL%"=="" (
    echo ❌ ข้อผิดพลาด: ไม่ได้ระบุ URL ยกเลิกการทำงาน
    pause
    exit /b
)

echo.
echo ⏳ กำลังเริ่มการทำงาน...
echo โปรเซสนี้จะทำงานอยู่เบื้องหลังหลังจากหน้าต่างนี้ปิดลง
echo สามารถดูความคืบหน้าได้ในไฟล์: channel_process.log
echo.

:: Navigate to script directory
cd /d "%~dp0"

:: Activate virtual environment if it exists
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: Run script in background without showing the window
start "" /b pythonw process_channel.py "!CHANNEL_URL!" --max 0 > channel_process.log 2>&1

echo ✅ เริ่มทำงานใน Background แล้ว!
echo ท่านสามารถปิดหน้าต่างนี้ได้เลย
pause > nul
