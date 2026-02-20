@echo off
setlocal

echo ============================================
echo  Kokoro TTS MCP - Virtual Environment Setup
echo ============================================
echo.

:: Check Python is available
python --version >nul 2>&1
if errorlevel 1 (
	echo ERROR: Python not found. Install Python 3.10+ and add it to PATH.
	pause
	exit /b 1
)

:: Create venv (remove existing one first)
if exist ".venv" (
	echo Removing existing virtual environment...
	rmdir /s /q .venv
	echo Done.
)
echo Creating virtual environment...
python -m venv .venv
echo Done.
echo.

:: Activate venv
call .venv\Scripts\activate.bat

:: Install PyTorch with CUDA (Windows-specific, from custom index)
echo Installing PyTorch with CUDA 12.6 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
echo.

:: Install cross-platform dependencies from requirements.txt
echo Installing remaining dependencies...
pip install -r requirements.txt
echo.

echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Register with Claude Code:
echo      claude mcp add-json kokoro-tts "{\"type\":\"stdio\",\"command\":\"%cd%\\.venv\\Scripts\\python.exe\",\"args\":[\"%cd%\\server.py\"]}" --scope user
echo.
echo   2. Restart Claude Code.
echo.
pause
