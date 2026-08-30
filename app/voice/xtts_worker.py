import argparse
import base64
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path


def disable_numba_disk_cache() -> None:
    try:
        import numba
    except Exception:
        return

    for name in ("jit", "njit", "vectorize", "guvectorize"):
        original = getattr(numba, name, None)
        if original is None:
            continue

        def without_cache(*args, _original=original, **kwargs):
            kwargs["cache"] = False
            return _original(*args, **kwargs)

        setattr(numba, name, without_cache)


def detect_device() -> str:
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


def prepare_environment() -> None:
    cache_home = Path(os.getenv("XDG_CACHE_HOME") or "/Volumes/USB/jarvis-cache")
    if cache_home.exists():
        os.environ.setdefault("XDG_CACHE_HOME", str(cache_home))
        os.environ.setdefault("HF_HOME", str(cache_home / "huggingface"))
        os.environ.setdefault("TORCH_HOME", str(cache_home / "torch"))
        os.environ.setdefault("TTS_HOME", str(cache_home / "tts-home"))
        os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_home / "numba"))
        os.environ.setdefault("MPLCONFIGDIR", str(cache_home / "matplotlib"))

    disable_numba_disk_cache()


def load_model(model_name: str):
    prepare_environment()

    from TTS.api import TTS

    return TTS(model_name).to(detect_device())


def synthesize_to_file(model, text: str, voice_path: str, output_path: str, language: str) -> None:
    model.tts_to_file(
        text=text,
        speaker_wav=voice_path,
        language=language,
        file_path=output_path,
    )


def run_once(args: argparse.Namespace) -> None:
    model = load_model(args.model_name)
    synthesize_to_file(model, args.text, args.voice_path, args.output_path, args.language)


def write_json(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def run_server(args: argparse.Namespace) -> None:
    try:
        with contextlib.redirect_stdout(sys.stderr):
            model = load_model(args.model_name)
        write_json({"type": "ready", "ok": True})
    except Exception as exc:
        write_json({"type": "ready", "ok": False, "error": str(exc)})
        return

    for line in sys.stdin:
        if not line.strip():
            continue

        output_path = ""
        try:
            request = json.loads(line)
            request_id = request.get("id")
            if request.get("type") == "shutdown":
                write_json({"id": request_id, "ok": True})
                return

            text = str(request["text"])
            voice_path = str(request["voice_path"])
            language = str(request.get("language") or args.language)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as output_file:
                output_path = output_file.name

            with contextlib.redirect_stdout(sys.stderr):
                synthesize_to_file(model, text, voice_path, output_path, language)

            with open(output_path, "rb") as audio_file:
                audio_base64 = base64.b64encode(audio_file.read()).decode("ascii")
            write_json({"id": request_id, "ok": True, "audio_base64": audio_base64})
        except Exception as exc:
            write_json({"id": request.get("id") if "request" in locals() else None, "ok": False, "error": str(exc)})
        finally:
            if output_path:
                try:
                    os.remove(output_path)
                except OSError:
                    pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--text")
    parser.add_argument("--voice-path")
    parser.add_argument("--output-path")
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--language", default="en")
    args = parser.parse_args()

    if args.server:
        run_server(args)
        return

    missing = [
        name
        for name in ("text", "voice_path", "output_path")
        if getattr(args, name) is None
    ]
    if missing:
        parser.error(f"missing required arguments: {', '.join('--' + item.replace('_', '-') for item in missing)}")
    run_once(args)


if __name__ == "__main__":
    main()
