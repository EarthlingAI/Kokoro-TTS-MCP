#!/usr/bin/env python3
"""Kokoro TTS Coordinator — long-lived background process that owns all audio playback.

Accepts JSON commands over a Unix domain socket (macOS/Linux) or TCP localhost
(Windows). Auto-exits after an idle timeout. Spawned automatically by server.py
when needed.

Usage:
	python3 _coordinator.py [--socket PATH] [--pidfile PATH] [--idle-timeout SECS]
"""

import argparse
import atexit
import io
import json
import os
import queue
import signal
import socket
import sys
import tempfile
import threading
import time


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
	_TMP = tempfile.gettempdir()
	_DEFAULT_PORT_FILE = os.path.join(_TMP, "kokoro-tts.port")
	_DEFAULT_SOCKET = None  # TCP mode — port chosen dynamically
else:
	# Use /tmp explicitly — macOS's tempfile.gettempdir() returns per-user
	# sandbox dirs (/var/folders/...) that differ between contexts, which
	# would prevent the server.py client from finding the coordinator.
	_TMP = "/tmp"
	_DEFAULT_SOCKET = os.path.join(_TMP, "kokoro-tts.sock")

_DEFAULT_PID_FILE = os.path.join(_TMP, "kokoro-tts.pid")
_DEFAULT_IDLE_TIMEOUT = 60  # seconds


# ---------------------------------------------------------------------------
# Bootstrap venv (same as server.py — coordinator must run inside the venv)
# ---------------------------------------------------------------------------

def _bootstrap_venv():
	"""Re-exec under the .venv Python if we're not already in it."""
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

	venv_dir = os.path.dirname(os.path.dirname(venv_python))
	if sys.platform == "win32":
		already_in_venv = (
			os.path.realpath(sys.prefix).casefold()
			== os.path.realpath(venv_dir).casefold()
		)
	else:
		already_in_venv = os.path.realpath(sys.prefix) == os.path.realpath(venv_dir)

	if already_in_venv:
		return

	args = [venv_python, __file__] + sys.argv[1:]
	if sys.platform == "win32":
		import subprocess
		result = subprocess.run(args)
		sys.exit(result.returncode)
	else:
		os.execv(venv_python, args)


# ---------------------------------------------------------------------------
# Voices (duplicated from server.py — coordinator validates voice IDs)
# ---------------------------------------------------------------------------

ALL_VOICE_IDS = [
	# American English (Female)
	"af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
	"af_kore", "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
	# American English (Male)
	"am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam",
	"am_michael", "am_onyx", "am_puck", "am_santa",
	# British English (Female)
	"bf_alice", "bf_emma", "bf_isabella", "bf_lily",
	# British English (Male)
	"bm_daniel", "bm_fable", "bm_george", "bm_lewis",
	# Japanese (Female)
	"jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro",
	# Japanese (Male)
	"jm_kumo",
	# Mandarin Chinese (Female)
	"zf_xiaobei", "zf_xiaoni", "zf_xiaoyi",
	# Mandarin Chinese (Male)
	"zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
	# Spanish (Female)
	"ef_dora",
	# Spanish (Male)
	"em_alex", "em_santa",
	# French (Female)
	"ff_siwis",
	# Hindi (Female)
	"hf_alpha", "hf_beta",
	# Hindi (Male)
	"hm_omega", "hm_psi",
	# Italian (Female)
	"if_sara",
	# Italian (Male)
	"im_nicola",
	# Brazilian Portuguese (Female)
	"pf_dora",
	# Brazilian Portuguese (Male)
	"pm_alex", "pm_santa",
]


# ---------------------------------------------------------------------------
# Pipeline (same lazy-load pattern as server.py)
# ---------------------------------------------------------------------------

_pipeline = None


def _get_pipeline():
	"""Lazily initialize the Kokoro pipeline (downloads model on first call)."""
	global _pipeline
	if _pipeline is None:
		import torch
		from kokoro import KPipeline

		if torch.cuda.is_available():
			device = "cuda:1" if torch.cuda.device_count() > 1 else "cuda"
		else:
			device = "cpu"
		lang_code = "a"
		old_stdout = sys.stdout
		sys.stdout = io.StringIO()
		try:
			_pipeline = KPipeline(
				lang_code=lang_code, device=device,
			)
		finally:
			sys.stdout = old_stdout
		print(f"Kokoro pipeline loaded on {device}", file=sys.stderr)
	return _pipeline


# ---------------------------------------------------------------------------
# Audio worker
# ---------------------------------------------------------------------------

_speak_queue: queue.Queue = queue.Queue()
_generation: int = 0
_generation_lock = threading.Lock()
_SHUTDOWN = object()


def _speak_worker():
	"""Background worker — generates and plays queued speech sequentially."""
	import numpy as np
	import sounddevice as sd

	while True:
		item = _speak_queue.get()

		if item is _SHUTDOWN:
			_speak_queue.task_done()
			break

		text, voice, speed, gen = item

		with _generation_lock:
			current_gen = _generation

		if gen != current_gen:
			_speak_queue.task_done()
			continue

		try:
			pipeline = _get_pipeline()
			audio_chunks = []
			for _, _, chunk in pipeline(text, voice=voice, speed=speed):
				with _generation_lock:
					current_gen = _generation
				if gen != current_gen:
					break
				if chunk is not None:
					audio_chunks.append(chunk)

			with _generation_lock:
				current_gen = _generation

			if gen != current_gen or not audio_chunks:
				_speak_queue.task_done()
				continue

			audio = np.concatenate(audio_chunks)
			peak = np.max(np.abs(audio))
			if peak > 0:
				audio = audio / peak * 0.95

			sd.play(audio, samplerate=24000)
			sd.wait()

		except Exception as e:
			print(f"Speech error: {e}", file=sys.stderr)
		finally:
			_speak_queue.task_done()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _handle_speak(data: dict) -> dict:
	"""Queue a speak request."""
	text = data.get("text", "").strip()
	if not text:
		return {"status": "error", "message": "No text provided."}

	voice = data.get("voice", "af_nicole")
	if voice not in ALL_VOICE_IDS:
		return {"status": "error", "message": f"Unknown voice '{voice}'."}

	speed = float(data.get("speed", 1.0))
	speed = max(0.5, min(2.0, speed))

	with _generation_lock:
		gen = _generation

	_speak_queue.put((text, voice, speed, gen))
	return {"status": "ok", "message": f"Queued {len(text)} chars via '{voice}'"}


def _handle_stop() -> dict:
	"""Stop playback and clear the queue."""
	import sounddevice as sd

	global _generation
	with _generation_lock:
		_generation += 1

	sd.stop()

	while not _speak_queue.empty():
		try:
			_speak_queue.get_nowait()
			_speak_queue.task_done()
		except queue.Empty:
			break

	return {"status": "ok", "message": "Stopped"}


def _handle_ping() -> dict:
	return {"status": "ok", "message": "pong"}


# ---------------------------------------------------------------------------
# Socket server
# ---------------------------------------------------------------------------

class CoordinatorServer:
	"""Listens on a Unix socket (or TCP on Windows) and dispatches commands."""

	def __init__(self, socket_path: str | None, pid_file: str, idle_timeout: int):
		self._socket_path = socket_path
		self._pid_file = pid_file
		self._idle_timeout = idle_timeout
		self._server_sock: socket.socket | None = None
		self._last_activity = time.monotonic()
		self._activity_lock = threading.Lock()
		self._shutting_down = False
		self._port_file: str | None = None  # Windows TCP mode

	def _touch_activity(self):
		with self._activity_lock:
			self._last_activity = time.monotonic()

	def _idle_watchdog(self):
		"""Exits the process if idle for too long."""
		while not self._shutting_down:
			time.sleep(5)
			with self._activity_lock:
				elapsed = time.monotonic() - self._last_activity
			if elapsed >= self._idle_timeout:
				print(
					f"Idle for {self._idle_timeout}s — shutting down.",
					file=sys.stderr,
				)
				self._shutdown()
				return

	def _shutdown(self):
		"""Clean shutdown: stop audio, close socket, remove files."""
		if self._shutting_down:
			return
		self._shutting_down = True

		# Stop any playing audio
		try:
			_handle_stop()
		except Exception:
			pass

		# Tell the worker to exit
		_speak_queue.put(_SHUTDOWN)

		# Close the server socket to unblock accept()
		if self._server_sock:
			try:
				self._server_sock.close()
			except Exception:
				pass

		# Clean up files
		self._cleanup_files()

	def _cleanup_files(self):
		for path in (self._socket_path, self._pid_file, self._port_file):
			if path:
				try:
					os.unlink(path)
				except FileNotFoundError:
					pass
				except Exception as e:
					print(f"Cleanup error for {path}: {e}", file=sys.stderr)

	def _write_pid(self):
		with open(self._pid_file, "w") as f:
			f.write(str(os.getpid()))

	def _create_socket(self) -> socket.socket:
		if _IS_WINDOWS or self._socket_path is None:
			# TCP mode
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
			sock.bind(("127.0.0.1", 0))
			port = sock.getsockname()[1]

			# Write port to file so clients can find us
			self._port_file = _DEFAULT_PORT_FILE
			with open(self._port_file, "w") as f:
				f.write(str(port))
			print(f"Listening on TCP 127.0.0.1:{port}", file=sys.stderr)
		else:
			# Unix domain socket
			if os.path.exists(self._socket_path):
				os.unlink(self._socket_path)
			sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
			sock.bind(self._socket_path)
			print(f"Listening on {self._socket_path}", file=sys.stderr)

		sock.listen(8)
		sock.settimeout(2.0)  # So accept() doesn't block forever during shutdown
		return sock

	def _handle_connection(self, conn: socket.socket):
		"""Read one JSON line, dispatch, respond, close."""
		self._touch_activity()
		try:
			conn.settimeout(5.0)
			data = b""
			while b"\n" not in data:
				chunk = conn.recv(4096)
				if not chunk:
					break
				data += chunk

			if not data.strip():
				return

			request = json.loads(data.decode("utf-8"))
			cmd = request.get("cmd", "")

			if cmd == "speak":
				response = _handle_speak(request)
			elif cmd == "stop":
				response = _handle_stop()
			elif cmd == "ping":
				response = _handle_ping()
			elif cmd == "shutdown":
				response = {"status": "ok", "message": "Shutting down"}
				conn.sendall(json.dumps(response).encode("utf-8") + b"\n")
				conn.close()
				self._shutdown()
				return
			else:
				response = {"status": "error", "message": f"Unknown command '{cmd}'"}

			conn.sendall(json.dumps(response).encode("utf-8") + b"\n")

		except Exception as e:
			try:
				err = {"status": "error", "message": str(e)}
				conn.sendall(json.dumps(err).encode("utf-8") + b"\n")
			except Exception:
				pass
			print(f"Connection error: {e}", file=sys.stderr)
		finally:
			try:
				conn.close()
			except Exception:
				pass

	def run(self):
		"""Main loop: accept connections, dispatch to threads."""
		self._write_pid()
		atexit.register(self._cleanup_files)

		# Pre-load the model so it's ready for the first speak command.
		# This runs in the main thread before we start accepting connections.
		print("Loading Kokoro model...", file=sys.stderr)
		_get_pipeline()

		# Start the audio worker thread
		worker_thread = threading.Thread(target=_speak_worker, daemon=False)
		worker_thread.start()

		self._server_sock = self._create_socket()

		# Start the idle watchdog
		watchdog = threading.Thread(target=self._idle_watchdog, daemon=True)
		watchdog.start()

		# Handle SIGTERM/SIGINT gracefully
		def _signal_handler(signum, frame):
			print(f"Received signal {signum}, shutting down.", file=sys.stderr)
			self._shutdown()

		signal.signal(signal.SIGTERM, _signal_handler)
		signal.signal(signal.SIGINT, _signal_handler)

		print("Coordinator ready.", file=sys.stderr)

		while not self._shutting_down:
			try:
				conn, _ = self._server_sock.accept()
				t = threading.Thread(
					target=self._handle_connection, args=(conn,), daemon=True,
				)
				t.start()
			except socket.timeout:
				continue
			except OSError:
				# Socket closed during shutdown
				if not self._shutting_down:
					raise
				break

		# Wait for the worker to finish
		worker_thread.join(timeout=10)
		print("Coordinator exited.", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
	_bootstrap_venv()

	# SSL trust (same as server.py)
	try:
		import truststore
		truststore.inject_into_ssl()
	except ImportError:
		pass

	# Model cache
	server_dir = os.path.dirname(os.path.abspath(__file__))
	os.environ.setdefault("HF_HUB_CACHE", os.path.join(server_dir, ".models"))

	# espeak-ng
	import espeakng_loader
	os.environ.setdefault("PHONEMIZER_ESPEAK_LIBRARY", espeakng_loader.get_library_path())
	os.environ.setdefault("ESPEAK_DATA_PATH", espeakng_loader.get_data_path())

	parser = argparse.ArgumentParser(description="Kokoro TTS Coordinator")
	parser.add_argument(
		"--socket", default=_DEFAULT_SOCKET,
		help="Unix socket path (ignored on Windows)",
	)
	parser.add_argument("--pidfile", default=_DEFAULT_PID_FILE, help="PID file path")
	parser.add_argument(
		"--idle-timeout", type=int, default=_DEFAULT_IDLE_TIMEOUT,
		help="Seconds of inactivity before auto-exit",
	)
	args = parser.parse_args()

	server = CoordinatorServer(
		socket_path=args.socket,
		pid_file=args.pidfile,
		idle_timeout=args.idle_timeout,
	)
	server.run()


if __name__ == "__main__":
	main()
