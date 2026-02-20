#!/usr/bin/env bash
set -e

echo "============================================"
echo " Kokoro TTS MCP - Virtual Environment Setup"
echo "============================================"
echo

# Find a compatible Python (3.10 – 3.12). kokoro requires Python <3.13.
find_python() {
	for cmd in python3.12 python3.11 python3.10 python3 python; do
		if command -v "$cmd" &>/dev/null; then
			local ver
			ver=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
			local major=${ver%%.*}
			local minor=${ver##*.}
			if [[ "$major" -eq 3 && "$minor" -ge 10 && "$minor" -le 12 ]]; then
				echo "$cmd"
				return
			fi
		fi
	done
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
	echo "ERROR: No compatible Python found. Install Python 3.10–3.12 and add it to PATH."
	echo "       (kokoro requires Python <3.13)"
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

# Install cross-platform dependencies from requirements.txt
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
	claude mcp remove kokoro-tts --scope user 2>/dev/null || true
	claude mcp add-json kokoro-tts "{\"type\":\"stdio\",\"command\":\"$(pwd)/run.sh\"}" --scope user
	echo "Registered."
else
	echo "Claude Code CLI not found. Register manually:"
	echo "  claude mcp add-json kokoro-tts '{\"type\":\"stdio\",\"command\":\"$(pwd)/run.sh\"}' --scope user"
fi
echo
echo "Restart Claude Code to start using Kokoro TTS."
echo
