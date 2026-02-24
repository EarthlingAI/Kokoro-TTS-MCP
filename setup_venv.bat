@echo off
setlocal

echo ============================================
echo  Speak TTS MCP - Virtual Environment Setup
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

:: Install PyTorch — auto-detect GPU
nvidia-smi >nul 2>&1
if errorlevel 1 (
	echo No NVIDIA GPU detected. Installing PyTorch (CPU^)...
	pip install torch torchvision torchaudio
) else (
	echo NVIDIA GPU detected. Installing PyTorch with CUDA 12.6...
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
)
echo.

:: Install dependencies (kokoro/misaki with --no-deps to bypass numpy==1.26.4 pin)
echo Installing kokoro and misaki (no-deps to avoid numpy conflict)...
pip install --no-deps kokoro==0.7.4 "misaki[en]==0.7.4"
echo Installing remaining dependencies...
pip install -r requirements.txt
echo.

echo ============================================
echo  Setup complete!
echo ============================================
echo.

:: Auto-register with Claude Code if CLI is available
where claude >nul 2>&1
if errorlevel 1 (
	echo Claude Code CLI not found. Register manually:
	echo   claude mcp add-json speak-tts "{\"type\":\"stdio\",\"command\":\"%cd%\\.venv\\Scripts\\python.exe\",\"args\":[\"%cd%\\server.py\"]}" --scope user
) else (
	echo Registering with Claude Code...
	claude mcp remove speak-tts --scope user >nul 2>&1
	claude mcp add-json speak-tts "{\"type\":\"stdio\",\"command\":\"%cd%\\.venv\\Scripts\\python.exe\",\"args\":[\"%cd%\\server.py\"]}" --scope user
	echo Registered.
)
echo.
echo Restart Claude Code to start using Speak TTS.
echo.
pause
