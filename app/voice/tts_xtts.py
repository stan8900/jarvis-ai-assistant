import base64
import json
import logging
import os
import subprocess
import tempfile
import threading
import uuid
from functools import cached_property
from pathlib import Path

from app.voice.tts_base import TextToSpeech


logger = logging.getLogger(__name__)


def build_worker_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("COQUI_TOS_AGREED", "1")
    cache_home = Path(env.get("XDG_CACHE_HOME") or "/Volumes/USB/jarvis-cache")
    if cache_home.exists():
        env.setdefault("XDG_CACHE_HOME", str(cache_home))
        env.setdefault("HF_HOME", str(cache_home / "huggingface"))
        env.setdefault("TORCH_HOME", str(cache_home / "torch"))
        env.setdefault("TTS_HOME", str(cache_home / "tts-home"))
        env.setdefault("NUMBA_CACHE_DIR", str(cache_home / "numba"))
        env.setdefault("MPLCONFIGDIR", str(cache_home / "matplotlib"))
    return env


class WarmXTTSWorker:
    def __init__(
        self,
        worker_python: str,
        model_name: str,
        language: str,
        timeout_seconds: float = 120,
    ) -> None:
        self.worker_python = worker_python
        self.model_name = model_name
        self.language = language
        self.timeout_seconds = timeout_seconds
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            return self._start_locked()

    def synthesize(self, text: str, voice_path: Path) -> bytes | None:
        with self._lock:
            if not self._start_locked():
                return None

            request_id = uuid.uuid4().hex
            payload = {
                "id": request_id,
                "text": text,
                "voice_path": str(voice_path),
                "language": self.language,
            }

            try:
                assert self._process is not None
                assert self._process.stdin is not None
                assert self._process.stdout is not None

                self._process.stdin.write(json.dumps(payload) + "\n")
                self._process.stdin.flush()
                line = self._process.stdout.readline()
                if not line:
                    logger.error("Warm XTTS worker exited without a response.")
                    self._stop_locked()
                    return None

                response = json.loads(line)
                if response.get("id") != request_id:
                    logger.error("Warm XTTS worker returned mismatched response id.")
                    return None
                if not response.get("ok"):
                    logger.error("Warm XTTS synthesis failed: %s", response.get("error"))
                    return None

                return base64.b64decode(response["audio_base64"])
            except Exception as exc:
                logger.error("Warm XTTS worker request failed: %s", exc)
                self._stop_locked()
                return None

    def close(self) -> None:
        with self._lock:
            self._stop_locked()

    def _start_locked(self) -> bool:
        if self._process is not None and self._process.poll() is None:
            return True

        env = build_worker_env()
        project_root = Path(__file__).resolve().parents[2]
        python_path = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(project_root)
            if not python_path
            else f"{project_root}{os.pathsep}{python_path}"
        )

        try:
            self._process = subprocess.Popen(
                [
                    self.worker_python,
                    "-m",
                    "app.voice.xtts_worker",
                    "--server",
                    "--model-name",
                    self.model_name,
                    "--language",
                    self.language,
                ],
                cwd=project_root,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            assert self._process.stdout is not None
            line = self._process.stdout.readline()
            if not line:
                logger.error("Warm XTTS worker exited before ready.")
                self._stop_locked()
                return False

            response = json.loads(line)
            if not response.get("ok"):
                logger.error("Warm XTTS worker failed to start: %s", response.get("error"))
                self._stop_locked()
                return False
            return True
        except Exception as exc:
            logger.error("Failed to start warm XTTS worker: %s", exc)
            self._stop_locked()
            return False

    def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return

        try:
            if process.poll() is None and process.stdin is not None:
                process.stdin.write(json.dumps({"type": "shutdown", "id": "shutdown"}) + "\n")
                process.stdin.flush()
                process.wait(timeout=5)
        except Exception:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


class XTTSVoice(TextToSpeech):
    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        voices_dir: str = "data/voices",
        language: str = "en",
        default_voice_id: str = "jarvis",
        warm_worker: bool = True,
        device: str | None = None,
        worker_python: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.voices_dir = Path(voices_dir)
        self.language = language
        self.default_voice_id = default_voice_id
        self.warm_worker = warm_worker
        self.device = device
        self.worker_python = worker_python or os.getenv("JARVIS_XTTS_PYTHON")
        self._warm_worker: WarmXTTSWorker | None = None

    @cached_property
    def _model(self):
        try:
            self._set_default_tts_home()
            from TTS.api import TTS
        except Exception as exc:
            logger.error("XTTS library is not available: %s", exc)
            return None

        try:
            model = TTS(self.model_name)
            device = self.device or self._detect_device()
            return model.to(device)
        except Exception as exc:
            logger.error("Failed to load XTTS model '%s': %s", self.model_name, exc)
            return None

    def synthesize(self, text: str, voice_id: str = "default") -> bytes | None:
        clean_text = text.strip()
        if not clean_text:
            logger.error("XTTS synthesis skipped: empty text.")
            return None

        resolved_voice_id = self.default_voice_id if voice_id == "default" else voice_id
        voice_path = self.voices_dir / f"{resolved_voice_id}_reference.wav"
        if not voice_path.exists() and resolved_voice_id.endswith("_reference"):
            voice_path = self.voices_dir / f"{resolved_voice_id}.wav"
        if not voice_path.exists() or voice_path.stat().st_size == 0:
            logger.error("XTTS voice reference not found or empty: %s", voice_path)
            return None

        if self.warm_worker and self.worker_python:
            audio = self._get_warm_worker().synthesize(clean_text, voice_path)
            if audio is not None:
                return audio
            logger.error("Warm XTTS worker unavailable; falling back to one-shot worker.")

        model = None if self.worker_python else self._model
        if model is None and self.worker_python:
            return self._synthesize_with_worker(clean_text, voice_path)
        if model is None:
            return None

        output_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output_file:
                output_path = output_file.name

            model.tts_to_file(
                text=clean_text,
                speaker_wav=str(voice_path),
                language=self.language,
                file_path=output_path,
            )
            with open(output_path, "rb") as audio_file:
                return audio_file.read()
        except Exception as exc:
            logger.error("XTTS synthesis failed: %s", exc)
            return None
        finally:
            if output_path:
                try:
                    os.remove(output_path)
                except OSError:
                    pass

    def warm_up(self) -> bool:
        if not self.warm_worker or not self.worker_python:
            return False
        return self._get_warm_worker().start()

    def close(self) -> None:
        if self._warm_worker is not None:
            self._warm_worker.close()

    def _get_warm_worker(self) -> WarmXTTSWorker:
        if self._warm_worker is None:
            assert self.worker_python is not None
            self._warm_worker = WarmXTTSWorker(
                worker_python=self.worker_python,
                model_name=self.model_name,
                language=self.language,
            )
        return self._warm_worker

    @staticmethod
    def _detect_device() -> str:
        configured_device = os.getenv("JARVIS_TTS_DEVICE")
        if configured_device:
            return configured_device

        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except Exception:
            pass
        return "cpu"

    @staticmethod
    def _set_default_tts_home() -> None:
        if os.getenv("TTS_HOME"):
            return

        cache_home = os.getenv("XDG_CACHE_HOME")
        if cache_home:
            os.environ["TTS_HOME"] = str(Path(cache_home) / "tts-home")

    def _synthesize_with_worker(self, text: str, voice_path: Path) -> bytes | None:
        output_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output_file:
                output_path = output_file.name

            env = build_worker_env()

            command = [
                self.worker_python,
                "-m",
                "app.voice.xtts_worker",
                "--text",
                text,
                "--voice-path",
                str(voice_path),
                "--output-path",
                output_path,
                "--model-name",
                self.model_name,
                "--language",
                self.language,
            ]
            result = subprocess.run(command, capture_output=True, text=True, env=env)
            if result.returncode != 0:
                logger.error(
                    "XTTS worker failed with exit code %s. stderr: %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return None
            with open(output_path, "rb") as audio_file:
                return audio_file.read()
        except Exception as exc:
            logger.error("XTTS worker synthesis failed: %s", exc)
            return None
        finally:
            if output_path:
                try:
                    os.remove(output_path)
                except OSError:
                    pass
