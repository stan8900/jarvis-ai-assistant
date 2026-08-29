import argparse
import base64
import os
import subprocess
import tempfile
import time
import wave
from pathlib import Path

os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

import httpx
import numpy as np
import sounddevice as sd


DEFAULT_API_URL = "http://127.0.0.1:8000/api/chat/audio"
DEFAULT_SESSION_ID = "voice-cli"
DEFAULT_USER_ID = "sultan"
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
DEFAULT_BLOCK_MS = 50
DEFAULT_SILENCE_MS = 800
DEFAULT_START_THRESHOLD = 0.018
DEFAULT_STOP_THRESHOLD = 0.012
DEFAULT_MAX_SECONDS = 30
DEFAULT_API_TIMEOUT_SECONDS = 300


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local JARVIS voice loop.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--session-id", default=DEFAULT_SESSION_ID)
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    parser.add_argument("--block-ms", type=int, default=DEFAULT_BLOCK_MS)
    parser.add_argument("--silence-ms", type=int, default=DEFAULT_SILENCE_MS)
    parser.add_argument("--start-threshold", type=float, default=DEFAULT_START_THRESHOLD)
    parser.add_argument("--stop-threshold", type=float, default=DEFAULT_STOP_THRESHOLD)
    parser.add_argument("--max-seconds", type=float, default=DEFAULT_MAX_SECONDS)
    parser.add_argument("--api-timeout", type=float, default=DEFAULT_API_TIMEOUT_SECONDS)
    return parser.parse_args()


def record_until_silence(
    sample_rate: int,
    channels: int,
    block_ms: int,
    silence_ms: int,
    start_threshold: float,
    stop_threshold: float,
    max_seconds: float,
) -> np.ndarray:
    block_samples = max(1, int(sample_rate * block_ms / 1000))
    silence_blocks_needed = max(1, int(silence_ms / block_ms))
    max_blocks = max(1, int(max_seconds * 1000 / block_ms))

    frames: list[np.ndarray] = []
    started = False
    silent_blocks = 0

    with sd.InputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype="float32",
        blocksize=block_samples,
    ) as stream:
        print("Listening...")
        for _ in range(max_blocks):
            block, _ = stream.read(block_samples)
            rms = float(np.sqrt(np.mean(np.square(block))))

            if not started:
                if rms >= start_threshold:
                    started = True
                    frames.append(block.copy())
                    print("Heard you.")
                continue

            frames.append(block.copy())
            if rms < stop_threshold:
                silent_blocks += 1
            else:
                silent_blocks = 0

            if silent_blocks >= silence_blocks_needed:
                break

    if not frames:
        return np.empty((0, channels), dtype=np.float32)

    return np.concatenate(frames, axis=0)


def save_wav(audio: np.ndarray, sample_rate: int) -> str:
    pcm16 = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm16 * 32767).astype(np.int16)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        wav_path = temp_file.name

    with wave.open(wav_path, "wb") as wav_file:
        wav_file.setnchannels(1 if pcm16.ndim == 1 else pcm16.shape[1])
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())

    return wav_path


def post_audio(
    api_url: str,
    wav_path: str,
    session_id: str,
    user_id: str,
    timeout_seconds: float,
) -> dict:
    with open(wav_path, "rb") as audio_file:
        files = {"audio": ("speech.wav", audio_file, "audio/wav")}
        data = {"session_id": session_id, "user_id": user_id}
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(api_url, data=data, files=files)

    response.raise_for_status()
    return response.json()


def play_wav(audio_bytes: bytes) -> None:
    if not audio_bytes:
        return

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            temp_file.write(audio_bytes)
            wav_path = temp_file.name

        try:
            data, sample_rate = read_wav_for_playback(wav_path)
            sd.play(data, sample_rate)
            sd.wait()
        except Exception:
            subprocess.run(["afplay", wav_path], check=False)
    finally:
        try:
            Path(wav_path).unlink(missing_ok=True)
        except UnboundLocalError:
            pass


def read_wav_for_playback(wav_path: str) -> tuple[np.ndarray, int]:
    with wave.open(wav_path, "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_rate = wav_file.getframerate()
        sample_width = wav_file.getsampwidth()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels)
    return audio, sample_rate


def run_loop(args: argparse.Namespace) -> None:
    print("JARVIS voice loop online. Press Ctrl+C to stop.")
    while True:
        wav_path = ""
        try:
            audio = record_until_silence(
                sample_rate=args.sample_rate,
                channels=args.channels,
                block_ms=args.block_ms,
                silence_ms=args.silence_ms,
                start_threshold=args.start_threshold,
                stop_threshold=args.stop_threshold,
                max_seconds=args.max_seconds,
            )
            if audio.size == 0:
                continue

            wav_path = save_wav(audio, args.sample_rate)
            start = time.perf_counter()
            result = post_audio(
                args.api_url,
                wav_path,
                args.session_id,
                args.user_id,
                args.api_timeout,
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            transcript = result.get("transcript", "")
            response = result.get("response", "")
            print(f"\nTranscript: {transcript}")
            print(f"JARVIS: {response}")
            print(f"Latency: {latency_ms} ms\n")

            audio_base64 = result.get("audio_base64")
            if audio_base64:
                play_wav(base64.b64decode(audio_base64))
        except httpx.HTTPStatusError as exc:
            print(f"API error: {exc.response.status_code} {exc.response.text}")
        except httpx.HTTPError as exc:
            print(f"API connection error: {exc}")
        finally:
            if wav_path:
                Path(wav_path).unlink(missing_ok=True)


def main() -> None:
    try:
        run_loop(parse_args())
    except KeyboardInterrupt:
        print("\nJARVIS voice loop stopped.")


if __name__ == "__main__":
    main()
