#!/usr/bin/env bash
set -e

echo "============================================"
echo " Kokoro TTS MCP - Virtual Environment Setup"
echo "============================================"
echo

# Find python
PYTHON=""
if command -v python3 &>/dev/null; then
	PYTHON="python3"
elif command -v python &>/dev/null; then
	PYTHON="python"
else
	echo "ERROR: Python not found. Install Python 3.10+ and add it to PATH."
	exit 1
fi
echo "Using: $PYTHON ($($PYTHON --version))"
echo

# Create venv (remove existing one first)
if [ -d ".venv" ]; then
	echo "Removing existing virtual environment..."
	rm -rf .venv
	echo "Done."
fi
echo "Creating virtual environment..."
$PYTHON -m venv .venv
echo "Done."
echo

# Activate venv
source .venv/bin/activate

# Install PyTorch with CUDA (Linux gets CUDA wheels, macOS gets default/MPS)
if [[ "$OSTYPE" == "darwin"* ]]; then
	echo "Installing PyTorch (macOS — MPS support)..."
	pip install torch torchvision torchaudio
else
	echo "Installing PyTorch with CUDA 12.6 support..."
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
fi
echo

# Install cross-platform dependencies from requirements.txt
echo "Installing remaining dependencies..."
pip install -r requirements.txt
echo

echo "============================================"
echo " Setup complete!"
echo "============================================"
echo
echo "Next steps:"
echo "  1. Register with Claude Code:"
echo "     claude mcp add-json kokoro-tts '{\"type\":\"stdio\",\"command\":\"'$(pwd)'/.venv/bin/python\",\"args\":[\"'$(pwd)'/server.py\"]}' --scope user"
echo
echo "  2. Restart Claude Code."
echo
