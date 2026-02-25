#!/usr/bin/env python3
"""Speak TTS MCP Server - Enables Claude to speak aloud via Kokoro-82M.

This is a thin MCP client that validates inputs and routes audio commands to a
long-lived coordinator process (_coordinator.py). The coordinator is
auto-spawned on first use and owns all model loading and audio playback.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time


def _bootstrap_venv():
	"""Re-exec under the .venv Python if we're not already in it.

	This makes server.py self-bootstrapping: any system Python can launch it
	and it will automatically find and use the project's virtual environment.
	Eliminates the need for platform-specific launcher scripts (run.sh, run.cmd).
	"""
	server_dir = os.path.dirname(os.path.abspath(__file__))

	if sys.platform == "win32":
		venv_python = os.path.join(server_dir, ".venv", "Scripts", "python.exe")
	else:
		venv_python = os.path.join(server_dir, ".venv", "bin", "python")

	if not os.path.isfile(venv_python):
		print(
			f"Warning: venv not found at {venv_python} — running with current interpreter.",
			file=sys.stderr,
		)
		return

	# Check sys.prefix instead of comparing binary paths — on platforms where
	# the venv python is a symlink to the system binary, os.path.realpath()
	# resolves to the same path for both, defeating the detection.
	venv_dir = os.path.dirname(os.path.dirname(venv_python))  # .venv/
	if sys.platform == "win32":
		already_in_venv = os.path.realpath(sys.prefix).casefold() == os.path.realpath(venv_dir).casefold()
	else:
		already_in_venv = os.path.realpath(sys.prefix) == os.path.realpath(venv_dir)

	if already_in_venv:
		return

	# Re-exec with the venv Python
	args = [venv_python, __file__] + sys.argv[1:]
	if sys.platform == "win32":
		# os.execv on Windows doesn't truly replace the process (CPython spawns
		# a child and exits the parent), which breaks MCP stdio pipes. Use
		# subprocess.run instead: the parent stays alive, child inherits stdio.
		result = subprocess.run(args)
		sys.exit(result.returncode)
	else:
		os.execv(venv_python, args)


if __name__ == "__main__":
	_bootstrap_venv()

from fastmcp import FastMCP

mcp = FastMCP("speak-tts")

# ---------------------------------------------------------------------------
# Coordinator connection constants
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
	_TMP = tempfile.gettempdir()
	_SOCKET_PATH = None
	_PORT_FILE = os.path.join(_TMP, "kokoro-tts.port")
else:
	# Use /tmp explicitly — macOS's tempfile.gettempdir() returns per-user
	# sandbox dirs (/var/folders/...) that differ between contexts, which
	# would prevent finding the coordinator spawned by another process.
	_TMP = "/tmp"
	_SOCKET_PATH = os.path.join(_TMP, "kokoro-tts.sock")
	_PORT_FILE = None

_PID_FILE = os.path.join(_TMP, "kokoro-tts.pid")
_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
_COORDINATOR_SCRIPT = os.path.join(_SERVER_DIR, "_coordinator.py")

# ---------------------------------------------------------------------------
# Voices (authoritative list — coordinator has a copy for validation)
# ---------------------------------------------------------------------------

VOICES = {
	"American English (Female)": [
		"af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
		"af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
	],
	"American English (Male)": [
		"am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
		"am_michael", "am_onyx", "am_puck", "am_santa",
	],
	"British English (Female)": [
		"bf_alice", "bf_emma", "bf_isabella", "bf_lily",
	],
	"British English (Male)": [
		"bm_daniel", "bm_fable", "bm_george", "bm_lewis",
	],
	"Japanese (Female)": [
		"jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
	],
	"Japanese (Male)": [
		"jm_kumo",
	],
	"Mandarin Chinese (Female)": [
		"zf_xiaobei", "zf_xiaoni", "zf_xiaoyi",
	],
	"Mandarin Chinese (Male)": [
		"zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
	],
	"Spanish (Female)": [
		"ef_dora",
	],
	"Spanish (Male)": [
		"em_alex", "em_santa",
	],
	"French (Female)": [
		"ff_siwis",
	],
	"Hindi (Female)": [
		"hf_alpha", "hf_beta",
	],
	"Hindi (Male)": [
		"hm_omega", "hm_psi",
	],
	"Italian (Female)": [
		"if_sara",
	],
	"Italian (Male)": [
		"im_nicola",
	],
	"Brazilian Portuguese (Female)": [
		"pf_dora",
	],
	"Brazilian Portuguese (Male)": [
		"pm_alex", "pm_santa",
	],
}

ALL_VOICE_IDS = [v for voices in VOICES.values() for v in voices]


# ---------------------------------------------------------------------------
# Coordinator communication
# ---------------------------------------------------------------------------

def _connect_to_coordinator() -> socket.socket:
	"""Open a connection to the coordinator's socket."""
	if _IS_WINDOWS:
		# TCP mode — read port from file
		with open(_PORT_FILE, "r") as f:
			port = int(f.read().strip())
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(5.0)
		sock.connect(("127.0.0.1", port))
	else:
		# Unix domain socket
		sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		sock.settimeout(5.0)
		sock.connect(_SOCKET_PATH)
	return sock


def _send_to_socket(cmd: dict) -> dict:
	"""Connect, send a JSON command, read the JSON response, disconnect."""
	sock = _connect_to_coordinator()
	try:
		sock.sendall(json.dumps(cmd).encode("utf-8") + b"\n")
		data = b""
		while b"\n" not in data:
			chunk = sock.recv(4096)
			if not chunk:
				break
			data += chunk
		if not data.strip():
			return {"status": "error", "message": "Empty response from coordinator"}
		return json.loads(data.decode("utf-8"))
	finally:
		sock.close()


def _spawn_coordinator():
	"""Launch the coordinator as a detached background process."""
	# Find the venv Python (same logic as _bootstrap_venv)
	if _IS_WINDOWS:
		venv_python = os.path.join(_SERVER_DIR, ".venv", "Scripts", "python.exe")
	else:
		venv_python = os.path.join(_SERVER_DIR, ".venv", "bin", "python")

	# Fall back to current interpreter if venv not found
	if not os.path.isfile(venv_python):
		venv_python = sys.executable

	log_file = os.path.join(tempfile.gettempdir(), "kokoro-tts-coordinator.log")

	cmd = [venv_python, _COORDINATOR_SCRIPT]

	with open(log_file, "a") as log:
		if _IS_WINDOWS:
			# Windows: CREATE_NEW_PROCESS_GROUP + CREATE_NO_WINDOW
			# Note: DETACHED_PROCESS causes Intel Fortran runtime (used by
			# numpy/scipy BLAS) to abort with "forrtl: error (200): program
			# aborting due to window-CLOSE event". CREATE_NO_WINDOW avoids this.
			CREATE_NEW_PROCESS_GROUP = 0x00000200
			CREATE_NO_WINDOW = 0x08000000
			subprocess.Popen(
				cmd,
				stdout=log,
				stderr=log,
				stdin=subprocess.DEVNULL,
				creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
			)
		else:
			subprocess.Popen(
				cmd,
				stdout=log,
				stderr=log,
				stdin=subprocess.DEVNULL,
				start_new_session=True,
			)

	print(f"Spawned coordinator (log: {log_file})", file=sys.stderr)


def _wait_for_socket(timeout: float = 90.0):
	"""Poll until the coordinator's socket is connectable."""
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		try:
			sock = _connect_to_coordinator()
			sock.close()
			return
		except (ConnectionRefusedError, FileNotFoundError, OSError):
			time.sleep(0.25)
	raise TimeoutError(
		f"Coordinator did not become ready within {timeout}s. "
		f"Check log: {os.path.join(tempfile.gettempdir(), 'kokoro-tts-coordinator.log')}"
	)


def _coordinator_send(cmd: dict) -> dict:
	"""Send a command to the coordinator, auto-spawning it if needed.

	On first connection failure, spawns the coordinator and waits for it to
	be ready. On second failure, raises.
	"""
	for attempt in range(2):
		try:
			return _send_to_socket(cmd)
		except (ConnectionRefusedError, FileNotFoundError, OSError):
			if attempt == 0:
				_spawn_coordinator()
				_wait_for_socket(timeout=15)
			else:
				raise


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def speak(
	text: str,
	voice: str = "af_nicole",
	speed: float = 1.0,
) -> str:
	"""Speak text aloud using Kokoro TTS. Plays audio through the system speakers.
	Text must be in English. Non-Latin characters are not pronounced correctly.

	Args:
		text: The text to speak aloud. Must be in English.
		voice: Voice ID to use. Default is af_nicole (American English female).
		       Use list_voices() to see all available voices.
		speed: Speech speed multiplier. Default 1.0, range 0.5 to 2.0.
	"""
	if not text or not text.strip():
		return "Error: No text provided."

	if voice not in ALL_VOICE_IDS:
		return f"Error: Unknown voice '{voice}'. Use list_voices() to see available voices."

	speed = max(0.5, min(2.0, speed))

	try:
		result = _coordinator_send({
			"cmd": "speak",
			"text": text,
			"voice": voice,
			"speed": speed,
		})
	except Exception as e:
		return f"Error: Could not reach TTS coordinator: {e}"

	if result.get("status") == "ok":
		return f"Successfully queued {len(text)} chars via '{voice}'. User will hear the message shortly."
	else:
		return f"Error: {result.get('message', 'Unknown error')}"


@mcp.tool()
def stop_all_speech() -> str:
	"""Stop any currently playing speech and clear the speech queue.
	Only use when the user explicitly asks to stop speech.
	"""
	try:
		result = _coordinator_send({"cmd": "stop"})
	except Exception as e:
		return f"Error: Could not reach TTS coordinator: {e}"

	if result.get("status") == "ok":
		return "Stopped."
	else:
		return f"Error: {result.get('message', 'Unknown error')}"


@mcp.tool()
def list_voices() -> dict:
	"""List all available Kokoro TTS voices organized by language and gender.

	Returns a dictionary mapping language/gender categories to lists of voice IDs.
	The default voice is af_nicole (American English female).
	"""
	return VOICES


if __name__ == "__main__":
	mcp.run()
