"""Explicit deployment operations; Python 3.10+, standard library only.

Never prints resolved Compose config or credentials. No volume deletion, reset,
in-place DB replacement, source-code execution, or automatic production rollback.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT = "safealley-deploy"


def run(args, **kwargs):
    # Do not echo commands: subsequent commands may contain sensitive values.
    return subprocess.run(args, check=True, **kwargs)


def compose(*args, source=False):
    if source:
        # Backup-only path: uses the EXISTING local project; never starts it.
        return ["docker", "compose", "--project-name", "safealley", "--env-file",
                str(ROOT / ".env"), "-f", str(ROOT / "docker-compose.yml"), *args]
    return ["docker", "compose", "--project-name", PROJECT, "--env-file",
            str(HERE / ".env"), "-f", str(HERE / "compose.yml"), *args]


def validate():
    if not (HERE / ".env").is_file():
        raise ValueError("Create deployment/.env from .env.example on the server first.")
    # Capture only in memory; never print/store the resolved secrets.
    result = run(compose("config", "--format", "json"), capture_output=True, text=True)
    config = json.loads(result.stdout)
    password = config["services"]["database"]["environment"]["POSTGRES_PASSWORD"]
    if len(password) < 24 or password.lower().startswith(("change", "example", "safealley")):
        raise ValueError("Use a unique, random DB password of at least 24 characters.")
    image = config["services"]["ollama"]["image"]
    if not re.fullmatch(r"ollama/ollama(?::[A-Za-z0-9_.-]+|@sha256:[a-f0-9]{64})", image) or image.endswith(":latest"):
        raise ValueError("OLLAMA_IMAGE must be an explicit official version tag/digest, not latest.")
    return config


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(path, source=False, exclude_feedback=False):
    path = path.resolve()
    if path.exists() or path.with_suffix(path.suffix + ".sha256").exists():
        raise ValueError("Backup target already exists; choose a new filename.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Binary stdout avoids PowerShell redirection corruption. Existing files are never overwritten.
    with path.open("xb") as stream:
        if os.name != "nt":
            path.chmod(0o600)
        dump = 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl'
        if exclude_feedback:
            dump += ''.join(' --exclude-table-data=public.' + name for name in (
                'route_recommendations', 'route_selection_events', 'user_route_preferences'))
        run(compose("exec", "-T", "database", "sh", "-c", dump,
                    source=source), stdout=stream, stderr=subprocess.PIPE)
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Invalid backup; do not transfer this file.")
    path.with_suffix(path.suffix + ".sha256").write_text(digest(path) + "\n", encoding="ascii")
    print(f"Backup complete: {path.name}. Feedback excluded: {exclude_feedback}. Transfer privately.")


def assert_empty_database():
    # Exclude objects owned by extensions, but refuse ANY existing user relation,
    # including alembic_version. Restore is only for a fresh deployment database.
    query = """SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname NOT IN ('pg_catalog','information_schema')
      AND n.nspname NOT LIKE 'pg_toast%' AND c.relkind IN ('r','p','v','m','S','f')
      AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass
        AND d.objid=c.oid AND d.deptype='e');"""
    result = run(compose("exec", "-T", "database", "psql", "-U", "safealley",
                         "-d", "safealley", "-At", "-v", "ON_ERROR_STOP=1", "-c", query),
                 capture_output=True, text=True)
    if result.stdout.strip() != "0":
        raise ValueError("Restore refused: destination is not empty. No data was replaced.")


def restore(path, confirmation):
    if confirmation != PROJECT:
        raise ValueError("Pass --confirm safealley-deploy after checking the target server.")
    path = path.resolve(strict=True)
    checksum = path.with_suffix(path.suffix + ".sha256")
    if not checksum.is_file() or checksum.read_text().strip() != digest(path):
        raise ValueError("Missing/mismatched .dump.sha256 checksum.")
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise ValueError("Only a trusted pg_dump custom-format backup is accepted.")
    active = run(compose("ps", "--services", "--status", "running"), capture_output=True, text=True)
    if set(active.stdout.split()) - {"database", "ollama"}:
        raise ValueError("Stop deployment app services before restore; do not restore into a live app.")
    assert_empty_database()
    with path.open("rb") as stream:
        run(compose("exec", "-T", "database", "pg_restore", "-U", "safealley", "-d", "safealley",
                    "--no-owner", "--no-acl", "--exit-on-error", "--single-transaction"),
            stdin=stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Restore complete. Existing data was not overwritten; run migrate next.")


def prepare_models(config):
    run(compose("up", "-d", "--wait", "--wait-timeout", "180", "ollama"))
    run(compose("exec", "-T", "ollama", "ollama", "pull",
                config["services"]["backend"]["environment"]["OLLAMA_MODEL"]))
    code = ("import os; from faster_whisper import WhisperModel; "
            "WhisperModel(os.environ['STT_MODEL'],device='cpu',compute_type='int8',"
            "download_root=os.environ['STT_MODEL_DIR']); print('STT model ready')")
    run(compose("run", "--rm", "--no-deps", "backend", "python", "-c", code))


def verify(config):
    run(compose("exec", "-T", "backend", "alembic", "current"))
    run(compose("exec", "-T", "backend", "alembic", "heads"))
    run(compose("exec", "-T", "backend", "python", "-c",
                "import urllib.request; urllib.request.urlopen('http://localhost:8000/health',timeout=5); print('DB/PostGIS/API healthy')"))
    run(compose("exec", "-T", "ollama", "nvidia-smi"))
    run(compose("exec", "-T", "ollama", "ollama", "list"))
    run(compose("exec", "-T", "ollama", "ollama", "ps"))
    port = config["services"]["frontend"]["ports"][0]
    host = port.get("host_ip", "127.0.0.1")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    for endpoint in ("/healthz", "/api/health", "/api/streetlight-heatmap/manifest"):
        with urllib.request.urlopen(f"http://{host}:{port['published']}{endpoint}", timeout=10) as response:
            if response.status != 200:
                raise ValueError("Frontend/API health check failed.")
    print("Basic checks passed. Still verify real routes, weather, microphone over HTTPS and GPU inference.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "build", "database", "models", "migrate", "heatmap", "start", "stop", "status", "verify", "backup", "restore"])
    parser.add_argument("--file", type=Path)
    parser.add_argument("--source-local", action="store_true", help="backup ONLY from existing laptop safealley project")
    parser.add_argument("--exclude-feedback", action="store_true", help="omit recommendation/selection/preference rows from backup")
    parser.add_argument("--confirm")
    args = parser.parse_args()
    if args.source_local and args.action != "backup":
        parser.error("--source-local is allowed only for backup")
    if args.exclude_feedback and args.action != "backup":
        parser.error("--exclude-feedback is allowed only for backup")
    if args.action in ("backup", "restore") and not args.file:
        parser.error("--file is required")
    config = None if args.source_local else validate()
    if args.action == "check":
        run(["docker", "info", "--format", "{{.OSType}}/{{.Architecture}}"])
        print("Compose settings valid. GPU support must be checked on the target server.")
    elif args.action == "build":
        run(compose("build", "backend", "frontend", "weather"))
        run(compose("pull", "database", "ollama"))
    elif args.action == "database":
        run(compose("up", "-d", "--wait", "--wait-timeout", "180", "database"))
    elif args.action == "models":
        prepare_models(config)
    elif args.action == "migrate":
        run(compose("run", "--rm", "--no-deps", "backend", "alembic", "upgrade", "head"))
    elif args.action == "heatmap":
        run(compose("run", "--rm", "--no-deps", "heatmap"))
    elif args.action == "start":
        run(compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "300"))
    elif args.action == "stop":
        run(compose("stop"))
    elif args.action == "status":
        run(compose("ps"))
    elif args.action == "verify":
        verify(config)
    elif args.action == "backup":
        backup(args.file, args.source_local, args.exclude_feedback)
    elif args.action == "restore":
        restore(args.file, args.confirm)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        # CalledProcessError repr/command/output could disclose connection settings.
        print(str(exc) if isinstance(exc, ValueError) else "Operation failed; stopped without automatic cleanup. Inspect locally; do not share secret-bearing logs.", file=sys.stderr)
        sys.exit(1)
