"""Create a SOURCE deployment TAR.GZ/ZIP, not an offline image/DB bundle.

Only allowed files from a pinned Git commit are used, never dirty local contents.
No .env, raw data, databases, models, node_modules, Git history or presentations.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_FILES = (
    "deployment/compose.yml", "deployment/.env.example", "deployment/manage.py",
    "deployment/package.py", "deployment/README.md", "deployment/test_deployment.py",
    "deployment/compose.vm.override.yml",
)
ROOT_FILES = {"README.md", "NOTICE.md", ".gitignore", ".env.example", "AGENTS.md", "docker-compose.yml"}
DENY_PARTS = {".git", ".local", ".private", "secrets", "raw", "processed", "node_modules",
              "__pycache__", ".pytest_cache", ".venv", "venv", "dist", "build", "output"}
DENY_SUFFIXES = {".dump", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".pfx", ".p12",
                 ".zip", ".tar", ".gz", ".pptx", ".log", ".pyc"}


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or any(p in DENY_PARTS for p in path.parts):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    if path.suffix.lower() in DENY_SUFFIXES:
        return False
    return (name in ROOT_FILES or name in DEPLOY_FILES or
            path.parts[0] in {"backend", "frontend", "data_pipeline", "docs"} or
            name.startswith("database/init/") or name == "database/README.md")


def check_content(name, data):
    # Defense in depth, not a guarantee against arbitrary hard-coded secrets.
    # Report filenames only. Operators must still review sources before distribution.
    patterns = (
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"(?:glpat-|ghp_|github_pat_)[A-Za-z0-9_]{20,}",
        rb"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}",
    )
    if any(re.search(pattern, data) for pattern in patterns):
        raise ValueError(f"Potential credential; package refused. Review file: {name}")


def git(*args):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT.as_posix()}", "-C", str(ROOT), *args])


def build_package(output, ref="HEAD"):
    if output.exists() or output.with_suffix(output.suffix + ".sha256").exists():
        raise ValueError("Output exists; choose a new archive name.")
    if not (output.name.endswith(".tar.gz") or output.suffix == ".zip"):
        raise ValueError("Output must be .tar.gz or .zip")
    commit = git("rev-parse", "--verify", f"{ref}^{{commit}}").decode().strip()
    tracked = git("ls-tree", "-r", "-z", "--name-only", commit).decode("utf-8").split("\0")
    names = sorted({name for name in tracked if name and allowed(name)})
    for required in ("backend/Dockerfile", "frontend/Dockerfile", "data_pipeline/Dockerfile",
                     "database/init/001_extensions.sql", ".env.example", "NOTICE.md", *DEPLOY_FILES):
        if required not in names:
            raise ValueError(f"Missing required committed file: {required}")
    payload = {}
    for name in names:
        data = git("show", f"{commit}:{name}")
        check_content(name, data)
        payload[name] = data
    manifest = {
        "format": "safealley-source-deployment-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": commit,
        "source_mode": "git-commit",
        "working_tree_changes": False,
        "local_working_tree_changes_present": bool(git("status", "--porcelain")),
        "requires": "Docker Compose, Python 3.10+, internet and server .env; existing VM volumes and GPU Ollama or separate initial DB restore",
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = {"SafeAlley/" + name: data for name, data in payload.items()}
    entries["SafeAlley/release.json"] = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    if output.name.endswith(".tar.gz"):
        with tarfile.open(output, "x:gz") as archive:
            for name, data in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
    else:
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix + ".sha256").write_text(checksum + "\n", encoding="ascii")
    print(f"Created {output.name}: {len(payload)} files; no DB/models/private env included.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ref", default="HEAD", help="Pinned source commit/ref (default HEAD); dirty files are excluded")
    args = parser.parse_args()
    build_package(args.output.resolve(), args.ref)
