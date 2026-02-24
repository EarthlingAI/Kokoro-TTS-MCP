#!/usr/bin/env bash
set -e

echo "============================================"
echo " Speak TTS MCP - Virtual Environment Setup"
echo "============================================"
echo

# Find a compatible Python (3.10+).
find_python() {
	for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
		if command -v "$cmd" &>/dev/null; then
			local ver
			ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
			local major=${ver%%.*}
			local minor=${ver##*.}
			if [[ "$major" -eq 3 && "$minor" -ge 10 ]]; then
				echo "$cmd"
				return
			fi
		fi
	done
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
	echo "ERROR: No compatible Python found. Install Python 3.10+ and add it to PATH."
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

# Install PyTorch — auto-detect GPU
if [[ "$OSTYPE" == "darwin"* ]]; then
	echo "Installing PyTorch (macOS — MPS support)..."
	pip install torch torchvision torchaudio
elif command -v nvidia-smi &>/dev/null; then
	echo "Installing PyTorch with CUDA 12.6..."
	pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
else
	echo "Installing PyTorch (CPU)..."
	pip install torch torchvision torchaudio
fi
echo

# Install dependencies (kokoro/misaki with --no-deps to bypass numpy==1.26.4 pin)
echo "Installing kokoro and misaki (no-deps to avoid numpy conflict)..."
pip install --no-deps kokoro==0.7.4 "misaki[en]==0.7.4"
echo "Installing remaining dependencies..."
pip install -r requirements.txt
echo

echo "============================================"
echo " Setup complete!"
echo "============================================"
echo

# Auto-register with Claude Code if CLI is available
if command -v claude &>/dev/null; then
	echo "Registering with Claude Code..."
	claude mcp remove speak-tts --scope user 2>/dev/null || true
	claude mcp add-json speak-tts "{\"type\":\"stdio\",\"command\":\"$(pwd)/.venv/bin/python\",\"args\":[\"$(pwd)/server.py\"]}" --scope user
	echo "Registered."
else
	echo "Claude Code CLI not found. Register manually:"
	echo "  claude mcp add-json speak-tts '{\"type\":\"stdio\",\"command\":\"$(pwd)/.venv/bin/python\",\"args\":[\"$(pwd)/server.py\"]}' --scope user"
fi
echo
echo "Restart Claude Code to start using Speak TTS."
echo
