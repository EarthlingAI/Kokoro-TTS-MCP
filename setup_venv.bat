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

:: Create venv
if not exist ".venv" (
	echo Creating virtual environment...
	python -m venv .venv
	echo Done.
) else (
	echo Virtual environment already exists, skipping creation.
)
echo.

:: Activate venv
call .venv\Scripts\activate.bat

:: Install PyTorch with CUDA
echo Installing PyTorch with CUDA 12.6 support...
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
echo.

:: Install remaining dependencies
echo Installing remaining dependencies...
pip install kokoro>=0.9.4 soundfile sounddevice numpy "fastmcp>=2.0"
echo.

echo ============================================
echo  Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Install espeak-ng if you haven't already:
echo      winget install espeak-ng
echo.
echo   2. Register with Claude Code:
echo      claude mcp add-json kokoro-tts "{\"type\":\"stdio\",\"command\":\"%cd%\\.venv\\Scripts\\python.exe\",\"args\":[\"%cd%\\server.py\"]}" --scope user
echo.
echo   3. Restart Claude Code.
echo.
pause
