from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


JARVIS_PROJECT = Path(
    "/Users/mukhammadsultanjurabekov/Desktop/Projects/Chattingwebsite/untitled folder/jarvis-ai-assistant"
)
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}


def open_vscode(path: str | None = None) -> str:
    target = str(path or JARVIS_PROJECT)
    if not _open_editor(target, app_name="Visual Studio Code", cli_name="code"):
        return "VS Code is not available, sir."
    return "Opening VS Code, sir."


def open_antigravity(path: str | None = None) -> str:
    target = str(path or JARVIS_PROJECT)
    if not _open_editor(target, app_name="Antigravity", cli_name="antigravity"):
        return "Antigravity IDE is not available, sir."
    return "Opening Antigravity IDE, sir."


def open_file(filename: str) -> str:
    query = _normalize_filename(filename)
    if not query:
        return "Which file shall I open, sir?"

    match = _find_file(query)
    if match is None:
        return f"Could not locate {filename}, sir."

    if not _open_editor(str(match), app_name="Visual Studio Code", cli_name="code"):
        return "VS Code is not available, sir."
    return f"Opening {match.name}, sir."


def run_server() -> str:
    command = _server_command()
    subprocess.Popen(command, cwd=JARVIS_PROJECT)
    return "Starting the server, sir."


def find_file(filename: str) -> Path | None:
    return _find_file(_normalize_filename(filename))


def _find_file(query: str) -> Path | None:
    normalized_query = query.lower().replace(" ", "_")
    partial_query = query.lower().replace(" ", "")

    for root, dirs, files in os.walk(JARVIS_PROJECT):
        dirs[:] = [directory for directory in dirs if directory not in IGNORED_DIRS]
        for file_name in files:
            normalized_name = file_name.lower()
            compact_name = normalized_name.replace("_", "").replace("-", "")
            if (
                normalized_query in normalized_name
                or partial_query in compact_name
                or normalized_name.startswith(normalized_query)
            ):
                return Path(root) / file_name
    return None


def _normalize_filename(filename: str) -> str:
    clean = filename.strip().lower()
    for prefix in ("file ", "the file ", "the "):
        if clean.startswith(prefix):
            clean = clean.removeprefix(prefix).strip()
    aliases = {
        "tool router": "tool_router",
        "long term memory": "long_term_memory",
        "morning brief": "brief",
    }
    return aliases.get(clean, clean)


def _server_command() -> list[str]:
    uvicorn = shutil.which("uvicorn")
    if uvicorn:
        return [uvicorn, "app.main:app", "--reload-dir", "app"]
    return ["python", "-m", "uvicorn", "app.main:app", "--reload-dir", "app"]


def _has_command(command: str) -> bool:
    return shutil.which(command) is not None


def _open_editor(target: str, app_name: str, cli_name: str) -> bool:
    cli_path = shutil.which(cli_name)
    if cli_path:
        subprocess.Popen([cli_path, target])
        return True

    mac_open = shutil.which("open")
    if mac_open:
        subprocess.Popen([mac_open, "-a", app_name, target])
        return True
    return False
