#!/usr/bin/env python3
"""SafeAlley VM updater. Fixed Compose paths, disposable build sources, no CI required.

Server: python3 runtime/update.py update --archive packages/new.tar.gz
First adoption is explicit; never initializes/restores a database or touches GPU services.
"""
import argparse
import copy
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

SERVICES = ("database", "backend", "weather", "frontend")
APPS = ("backend", "weather", "frontend")
PREFIX = {"backend": "backend/", "weather": "data_pipeline/", "frontend": "frontend/"}
PROJECT = "safealley-deploy"
DEFAULT_BASE = Path("/home/ltmetric/safealley-deploy")
MAX_SOURCE_BYTES = 512 * 1024 * 1024
RELEASE_NAMESPACE = "safealley-release"
RELEASE_TIMEZONE = timezone(timedelta(hours=9))
# 검토 완료: tools 전용 pipeline의 OSM 초기 점수 기본값만 demo -> uniform.
# 고정 VM 구성에 pipeline/추가 서비스가 없을 때 이 정확한 원본 쌍만 허용한다.
REVIEWED_COMPOSE_TRANSITIONS = frozenset({(
    "03f96de9f0b783372f12c9ce81fe3074bf51ad5bc09410fa897e5c36deb863d2",
    "799ea0fda9304664370cab2b7ea47186081306ddf98effbeba4ab9ba6eb18c6d",
)})
# Deliberate allowlist: never infer ownership from a broad prefix on a shared host.
IMAGE_REPOSITORIES = frozenset({
    "safealley-backend", "safealley-frontend", "safealley-frontend-check",
    "safealley-deploy-backend", "safealley-deploy-frontend", "safealley-deploy-weather",
    "safealley-deploy-pipeline", "safealley-deploy/frontend",
    "safealley-rollback-backend", "safealley-rollback-frontend",
    "safealley-rollback-weather", "safealley-rollback-database",
    "safealley-vm/backend", "safealley-vm/frontend", "safealley-vm/weather",
    "safealley-release/backend", "safealley-release/frontend", "safealley-release/weather",
    "safealley-release/database",
})


def release_image_tag(service, commit, checkpoint_stamp):
    require(service in APPS, "배포 이미지 서비스 이름이 올바르지 않습니다.")
    require(re.fullmatch(r"[a-f0-9]{40}", commit), "배포 이미지 커밋 형식이 올바르지 않습니다.")
    require(re.fullmatch(r"[0-9]{8}T[0-9]{12}Z", checkpoint_stamp), "배포 이미지 시각 형식이 올바르지 않습니다.")
    instant = datetime.strptime(checkpoint_stamp, "%Y%m%dT%H%M%S%fZ").replace(tzinfo=timezone.utc)
    stamp = instant.astimezone(RELEASE_TIMEZONE).strftime("%Y%m%d-%H%M%S")
    return f"{RELEASE_NAMESPACE}/{service}:{stamp}-{commit[:7]}"


def image_repository(ref):
    return ref.split("@", 1)[0] if "@" in ref else ref.rsplit(":", 1)[0]


def image_refs(image):
    return (image.get("RepoTags") or []) + (image.get("RepoDigests") or [])


def image_cleanup_plan(images, containers, retained):
    protected = set(retained) | {c["Image"] for c in containers}
    result = {}
    for item in images:
        refs = image_refs(item)
        # Shared aliases/digests, unknown repositories and anonymous images are not ours to remove.
        if (item["Id"] in protected or not refs
                or any(image_repository(r) not in IMAGE_REPOSITORIES for r in refs)):
            continue
        require(re.fullmatch(r"sha256:[a-f0-9]{64}", item["Id"]), "이미지 ID 형식이 올바르지 않습니다.")
        for ref in refs:
            require(not ref.startswith("-") and not any(c.isspace() for c in ref), "이미지 참조 형식이 올바르지 않습니다.")
            result[ref] = item["Id"]
    return result


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(args, log=None, **kwargs):
    # Never expose environment/configuration/decoder output through error messages.
    if log:
        with Path(log).open("ab") as f:
            os.chmod(log, 0o600)
            result = subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, **kwargs)
        require(result.returncode == 0, "Command failed; private log: " + str(log))
        return ""
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    require(result.returncode == 0, "Command failed: " + " ".join(map(str, args[:3])) + "; output withheld.")
    return result.stdout.decode("utf-8")


def checksum(archive):
    archive = Path(archive)
    require(archive.is_file() and not archive.is_symlink(), "Archive must be a regular file.")
    side = Path(str(archive) + ".sha256")
    require(side.is_file() and not side.is_symlink(), "Upload the matching .sha256 alongside the archive.")
    value = side.read_text(encoding="utf-8-sig").strip()
    require(re.fullmatch(r"[a-fA-F0-9]{64}(?:[ \t]+\*?[^\r\n]+)?", value), "Invalid checksum format.")
    expected = value.split()[0].lower()
    require(sha(archive) == expected, "Archive checksum mismatch.")
    return expected


def source_name(name):
    p = PurePosixPath(name)
    return (not p.is_absolute() and str(p) == name and "\\" not in name
            and not any(part in {"..", ".git", "node_modules", "raw", "processed", "output", ".venv", "private", "runtime"}
                        for part in p.parts)
            and not (p.name.startswith(".env") and p.name != ".env.example")
            and p.suffix.lower() not in {".key", ".pem", ".pfx", ".p12", ".dump", ".log"})


def unpack(archive, destination):
    """Strict package format; no extractall, links, duplicate names or unlisted files."""
    checksum(archive)
    destination = Path(destination)
    require(not any(destination.iterdir()), "Extraction directory must be empty.")
    with tarfile.open(archive, "r:gz") as tar:
        entries = {}
        total = 0
        for item in tar:
            name = item.name
            require(name.startswith("SafeAlley/") and source_name(name), "Unsafe archive path.")
            if item.isdir():
                continue
            require(item.isfile() and name not in entries, "Archive contains duplicate or special entries.")
            total += item.size
            require(total <= MAX_SOURCE_BYTES and len(entries) < 20000, "Source archive exceeds safety limit.")
            entries[name] = item
        require("SafeAlley/release.json" in entries, "Missing release manifest.")
        manifest = json.load(tar.extractfile(entries["SafeAlley/release.json"]))
        require(manifest.get("format") == "safealley-source-deployment-v1", "Unsupported package format.")
        require(re.fullmatch(r"[a-f0-9]{40}", manifest.get("base_commit", "")), "Invalid source commit.")
        hashes = manifest.get("sha256", {})
        require(isinstance(hashes, dict) and hashes, "Manifest has no files.")
        require(set(entries) == {"SafeAlley/" + name for name in hashes} | {"SafeAlley/release.json"},
                "Archive files differ from manifest.")
        for name, expected in hashes.items():
            require(source_name(name) and re.fullmatch(r"[a-f0-9]{64}", expected), "Invalid manifest entry.")
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            require(path.resolve().is_relative_to(destination.resolve()), "Extraction path escaped its directory.")
            with tar.extractfile(entries["SafeAlley/" + name]) as src, path.open("xb") as dst:
                shutil.copyfileobj(src, dst)
            os.chmod(path, 0o644)
            require(sha(path) == expected, "Source checksum mismatch: " + name)
        write_json(destination / "release.json", manifest)
    for name in ("docker-compose.yml", "frontend/nginx.conf", "backend/Dockerfile", "frontend/Dockerfile",
                 "data_pipeline/Dockerfile", "database/init/001_extensions.sql"):
        require(name in hashes, "Required source file missing: " + name)
    return manifest


def subset(hashes, prefix):
    return {k: v for k, v in hashes.items() if k.startswith(prefix)}


def check_contract(old, new, allow_migration=False, runtime_services=None):
    name = "docker-compose.yml"
    if old.get(name) != new.get(name):
        require((old.get(name), new.get(name)) in REVIEWED_COMPOSE_TRANSITIONS
                and runtime_services is not None and set(runtime_services) == set(SERVICES),
                name + " changed; review fixed runtime configuration before updating.")
        print("검토된 Compose 변경 승인: 운영 VM에 없는 tools pipeline의 OSM 기본값만 변경. 고정 실행 설정은 유지합니다.", flush=True)
    name = "frontend/nginx.conf"
    require(old.get(name) == new.get(name), name + " changed; review fixed runtime configuration before updating.")
    require(subset(old, "database/init/") == subset(new, "database/init/"), "Database init files changed; manual review required.")
    old_migrations = subset(old, "backend/alembic/")
    new_migrations = subset(new, "backend/alembic/")
    changed = old_migrations != new_migrations
    if changed:
        require(allow_migration, "Alembic files changed. Review migrations, then explicitly pass --allow-migration.")
        require(all(new_migrations.get(k) == v for k, v in old_migrations.items()),
                "Existing Alembic history was modified/deleted; update refused.")
    return changed


def env_map(container):
    return dict(value.split("=", 1) for value in container["Config"].get("Env", []) if "=" in value)


def signature(container):
    return {"image": container["Image"],
            "env_hash": hashlib.sha256(json.dumps(env_map(container), sort_keys=True).encode()).hexdigest(),
            "ports": container["HostConfig"].get("PortBindings") or {},
            "networks": sorted(container["NetworkSettings"]["Networks"]),
            "extra_hosts": container["HostConfig"].get("ExtraHosts") or [],
            "mounts": sorted((m["Type"], m.get("Name", m["Source"]), m["Destination"], m["RW"])
                             for m in container["Mounts"])}


def assert_unreferenced(targets, containers):
    targets = [Path(t).resolve() for t in targets]
    for c in containers:
        labels = c["Config"].get("Labels") or {}
        paths = [m["Source"] for m in c.get("Mounts", [])]
        paths += [labels.get("com.docker.compose.project.working_dir", "")]
        paths += labels.get("com.docker.compose.project.config_files", "").split(",")
        for text in filter(None, paths):
            p = Path(text).resolve()
            require(not any(p == t or p.is_relative_to(t) for t in targets), "A container still references a cleanup target.")


class VM:
    def __init__(self, base):
        self.base = Path(base).absolute()
        self.runtime = self.base / "runtime"
        self.private = self.base / "private"
        self.packages = self.base / "packages"
        self.config = self.runtime / "compose.json"
        self.state = self.runtime / "state.json"

    @contextmanager
    def lock(self):
        import fcntl
        require(self.base.is_dir() and self.base.resolve() == self.base, "Deployment root is missing or symlinked.")
        require(self.private.is_dir() and self.private.resolve() == self.private, "Private directory missing/unsafe.")
        for p in (self.runtime, self.packages):
            require(not p.is_symlink() and p.resolve() == p, "Unsafe deployment directory.")
        with (self.private / "update.lock").open("a") as f:
            os.chmod(f.name, 0o600)
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("Another deployment is in progress.")
            yield

    def compose(self, *args):
        return ["docker", "compose", "--project-directory", str(self.runtime), "-p", PROJECT,
                "-f", str(self.config), *args]

    def live(self, all_containers=False):
        ids = run(["docker", "ps", "-aq"]).split() if all_containers else [PROJECT + "-" + s + "-1" for s in SERVICES]
        items = json.loads(run(["docker", "inspect", *ids])) if ids else []
        return items if all_containers else {x["Config"]["Labels"]["com.docker.compose.service"]: x for x in items}

    def images(self):
        ids = list(dict.fromkeys(run(["docker", "image", "ls", "--all", "--quiet", "--no-trunc"]).split()))
        return json.loads(run(["docker", "image", "inspect", *ids])) if ids else []

    def retained_images(self, state):
        require(not (self.runtime / "pending.json").exists(), "미완료 배포가 있어 이미지 정리를 중단합니다.")
        configs = [self.config]
        if state.get("previous"):
            checkpoint = Path(state["previous"]["checkpoint"])
            require(checkpoint.resolve() == checkpoint and checkpoint.parent == self.private / "updates",
                    "직전 복구 설정 경로가 안전하지 않습니다.")
            require(load(checkpoint / "state.json")["commit"] == state["previous"]["commit"],
                    "직전 복구 커밋과 설정이 일치하지 않습니다.")
            configs.append(checkpoint / "compose.json")
        refs = set()
        for config in configs:
            require(config.is_file() and not config.is_symlink(), "보존할 이미지 설정 파일이 없습니다.")
            model = load(config)["services"]
            require(set(model) == set(SERVICES), "보존할 서비스 구성이 예상과 다릅니다.")
            refs.update(model[s]["image"] for s in SERVICES)
        retained = {}
        for ref in sorted(refs):
            require(isinstance(ref, str) and not ref.startswith("-"), "보존할 이미지 참조가 올바르지 않습니다.")
            retained[ref] = json.loads(run(["docker", "image", "inspect", ref]))[0]["Id"]
        return retained

    def clean_images(self, dry_run=False):
        """Exact owned refs only, never force/prune or delete a container/volume/cache."""
        state = load(self.state)
        retained = self.retained_images(state)
        images = self.images()
        containers = self.live(all_containers=True)
        plan = image_cleanup_plan(images, containers, retained.values())
        tags = [r for r in plan if "@" not in r]
        print(f"SafeAlley 이미지 정리 대상: {len(set(plan.values()))}개 이미지 / {len(tags)}개 태그", flush=True)
        if dry_run:
            for ref in sorted(tags): print("정리 예정: " + ref, flush=True)
            return {"planned_images": len(set(plan.values())), "planned_tags": len(tags)}
        checkpoint = Path(state["checkpoint"])
        require(checkpoint.resolve() == checkpoint and checkpoint.parent == self.private / "updates"
                and checkpoint.is_dir(), "이미지 정리 기록 경로가 안전하지 않습니다.")
        # Keep protected snapshots in the existing recovery checkpoint, not a new release directory.
        report = {"planned": plan, "retained": retained, "removed": [], "skipped": [], "complete": False}
        report_path = checkpoint / ("image-cleanup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        write_json(report_path, report)
        foreign = {r: i["Id"] for i in images for r in image_refs(i)
                   if image_repository(r) not in IMAGE_REPOSITORIES}
        original_containers = {c["Id"]: c["Image"] for c in containers}
        # Tags first. Docker may also remove associated digests; absent refs are simply skipped.
        for ref in sorted(plan, key=lambda r: ("@" in r, r)):
            require(load(self.state) == state and self.retained_images(state) == retained,
                    "배포 상태 또는 복구 이미지가 변경되어 정리를 중단합니다.")
            fresh = image_cleanup_plan(self.images(), self.live(all_containers=True), retained.values())
            if fresh.get(ref) != plan[ref]:
                report["skipped"].append(ref)
                continue
            run(["docker", "image", "rm", "--no-prune", ref])
            report["removed"].append(ref)
            write_json(report_path, report)
        after = self.images()
        after_refs = {r: i["Id"] for i in after for r in image_refs(i)}
        require(all(after_refs.get(r) == image for r, image in foreign.items()),
                "다른 프로젝트 이미지 참조가 변경되었습니다. 정리 기록을 확인하세요.")
        after_containers = {c["Id"]: c["Image"] for c in self.live(all_containers=True)}
        require(all(after_containers.get(c) == image for c, image in original_containers.items()),
                "컨테이너 구성이 변경되었습니다. 정리 기록을 확인하세요.")
        require(self.retained_images(state) == retained, "현재·직전 복구 이미지 확인에 실패했습니다.")
        removed_ids = set(plan.values()) - {i["Id"] for i in after}
        report.update(complete=True, removed_images=len(removed_ids),
                      removed_tags=sum(r not in after_refs for r in tags))
        write_json(report_path, report)
        print(f"이미지 정리 완료: {report['removed_images']}개 이미지 / {report['removed_tags']}개 태그. "
              "현재·직전 복구 및 모든 컨테이너·다른 프로젝트 이미지 보존 확인.", flush=True)
        return report

    def auto_clean_images(self):
        try:
            self.clean_images()
        except (RuntimeError, OSError, ValueError, KeyError):
            print("주의: 배포는 성공했지만 이미지 자동 정리는 안전을 위해 중단했습니다. clean-images --dry-run으로 확인하세요.", flush=True)

    def recreate(self, services, folder):
        for service in services:
            print("Recreating " + service + " (existing volumes retained)", flush=True)
            run(self.compose("up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate",
                             "--wait", "--wait-timeout", "180", service), log=folder / (service + "-up.log"))

    def database_revision(self):
        value = run(["docker", "exec", PROJECT + "-database-1", "sh", "-c",
                     'exec psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT version_num FROM alembic_version ORDER BY version_num"']).strip()
        require(re.fullmatch(r"[a-zA-Z0-9_]+", value), "Expected one existing Alembic head.")
        return value

    def backup(self, kind):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder = self.private / "updates" / (kind + "-" + stamp)
        folder.mkdir(parents=True, mode=0o700)
        write_json(folder / "containers.json", self.live())
        if self.config.exists():
            write_json(folder / "compose.json", load(self.config))
        if self.state.exists():
            write_json(folder / "state.json", load(self.state))
        dump = folder / "database.dump"
        with dump.open("xb") as f:
            result = subprocess.run(["docker", "exec", PROJECT + "-database-1", "sh", "-c",
                                     'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom'],
                                    stdout=f, stderr=subprocess.PIPE)
        os.chmod(dump, 0o600)
        require(result.returncode == 0 and dump.stat().st_size, "Database backup failed; no containers replaced.")
        with dump.open("rb") as f:
            run(["docker", "exec", "-i", PROJECT + "-database-1", "pg_restore", "--list"], stdin=f)
        Path(str(dump) + ".sha256").write_text(sha(dump) + "\n", encoding="ascii")
        write_json(folder / "checkpoint.json", {"revision": self.database_revision(), "kind": kind})
        return folder

    def verify(self, before=None, adopt=False):
        model = load(self.config)
        for service, c in self.live().items():
            require(c["State"]["Running"] and c["State"].get("Health", {}).get("Status", "healthy") == "healthy",
                    service + " is not healthy.")
            labels = c["Config"]["Labels"]
            require(labels["com.docker.compose.project.working_dir"] == str(self.runtime)
                    and labels["com.docker.compose.project.config_files"] == str(self.config), "Compose paths are not fixed.")
            expected_image = json.loads(run(["docker", "image", "inspect", model["services"][service]["image"]]))[0]["Id"]
            require(c["Image"] == expected_image, service + " image does not match configuration.")
            if before:
                previous = signature(before[service])
                current = signature(c)
                if not adopt:
                    previous.pop("image"); current.pop("image")
                else:
                    previous["mounts"] = [(t, str(self.runtime / "database/init") if d == "/docker-entrypoint-initdb.d" else s, d, rw)
                                          for t, s, d, rw in previous["mounts"]]
                    previous["mounts"].sort()
                require(current == previous, service + " environment/network/volume/image changed unexpectedly.")
        self.probe_connections()

    def probe_connections(self):
        connection = http.client.HTTPConnection("127.0.0.1", 8081, timeout=15)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            require(response.status == 302 and response.getheader("Location") == "https://ltmetric-pms.synology.me:21802/",
                    "HTTP redirect check failed.")
        finally:
            connection.close()
        cert = self.private / "tls-f6b47f3/safealley.crt"
        def get(path):
            return run(["curl", "--noproxy", "*", "-fsS", "--max-time", "30", "--cacert", str(cert),
                        "--resolve", "ltmetric-pms.synology.me:8081:127.0.0.1",
                        "https://ltmetric-pms.synology.me:8081" + path])
        get("/api/health")
        html = get("/")
        assets = re.findall(r'(?:src|href)="(/assets/[^"<>]+\.(?:js|css))"', html)
        require(assets, "Frontend entry assets not found.")
        for asset in assets:
            require(".." not in asset, "Invalid frontend asset URL.")
            get(asset)
        probe = '''import os,json,urllib.request
base=os.environ['OLLAMA_BASE_URL'].rstrip('/')
tags=json.load(urllib.request.urlopen(base+'/api/tags',timeout=20))
assert os.environ['OLLAMA_MODEL'] in [m['name'] for m in tags['models']]
url=os.environ['STT_REMOTE_URL'].rstrip('/')
health=json.load(urllib.request.urlopen(url+'/health',timeout=20))
assert health.get('ready') and health.get('device') in {'cpu','cuda'}
if os.environ.get('INTENT_PREVIEW_PROVIDER') == 'laya':
    preview=os.environ['LAYA_PREVIEW_URL'].rstrip('/')
    laya=json.load(urllib.request.urlopen(preview+'/health',timeout=20))
    assert laya.get('ready')
    assert laya.get('checkpoint_sha256') == os.environ['LAYA_CHECKPOINT_SHA256']
print('MODEL_ENDPOINTS_OK')'''
        require(run(["docker", "exec", PROJECT + "-backend-1", "python", "-c", probe]).strip() == "MODEL_ENDPOINTS_OK",
                "Ollama/Whisper/Laya 모델 연결 확인에 실패했습니다.")
        print("검증 완료: HTTPS, 리다이렉트, 프런트엔드 파일, DB 및 모델 연결.", flush=True)

    def save_package(self, archive, manifest):
        self.packages.mkdir(mode=0o700, exist_ok=True)
        destination = self.packages / ("SafeAlley-" + manifest["base_commit"] + ".tar.gz")
        digest = checksum(archive)
        if destination.exists():
            if sha(destination) != digest:
                # Packaging timestamps can differ for the same pinned source commit.
                with tempfile.TemporaryDirectory(prefix="safealley-compare-") as temp:
                    previous = unpack(destination, Path(temp))
                require(previous["base_commit"] == manifest["base_commit"] and previous["sha256"] == manifest["sha256"],
                        "Different source already exists for this commit.")
                digest = sha(destination)
        else:
            temporary = destination.with_name(destination.name + ".tmp")
            require(not temporary.exists(), "Incomplete package copy exists; review it first.")
            shutil.copyfile(archive, temporary)
            os.chmod(temporary, 0o600)
            require(sha(temporary) == digest, "Package copy checksum mismatch.")
            temporary.replace(destination)
        Path(str(destination) + ".sha256").write_text(digest + "\n", encoding="ascii")
        return destination

    def consume_upload(self, archive, state):
        archive = Path(archive)
        retained = {Path(state["package"])}
        if state.get("previous"):
            retained.add(Path(state["previous"]["package"]))
        if archive.parent == self.packages and archive not in retained:
            require(archive.resolve() == archive and archive.is_file() and not archive.is_symlink(), "Unsafe upload cleanup path.")
            checksum(archive)
            assert_unreferenced([archive], self.live(all_containers=True))
            archive.unlink()
            Path(str(archive) + ".sha256").unlink()

    def adopt(self, release):
        release = Path(release).absolute()
        require(release.parent == self.base and release.resolve() == release and release.is_dir(), "Unsafe legacy release.")
        require(not self.runtime.exists(), "runtime already exists; use status/update, not adopt.")
        old = self.live()
        for c in old.values():
            require(c["Config"]["Labels"]["com.docker.compose.project.working_dir"] == str(release), "Legacy folders are not unified.")
        source_manifest = load(release / "release.json")
        for name, expected in source_manifest["sha256"].items():
            require(source_name(name) and sha(release / name) == expected, "Legacy source differs from manifest: " + name)
        archive = self.base / ("SafeAlley-main-" + source_manifest["base_commit"][:7] + ".tar.gz")
        with tempfile.TemporaryDirectory(prefix="safealley-adopt-") as temp:
            manifest = unpack(archive, Path(temp))
        require(manifest["base_commit"] == source_manifest["base_commit"], "Archive/release mismatch.")
        legacy_cmd = ["docker", "compose", "--env-file", str(release / ".env"), "--project-directory", str(release), "-p", PROJECT]
        for name in ("docker-compose.yml", "vm.override.yml", "https.override.json"):
            legacy_cmd += ["-f", str(release / name)]
        model = json.loads(run(legacy_cmd + ["config", "--format", "json"]))
        self.probe_connections()
        checkpoint = self.backup("adopt")
        legacy_backup = checkpoint / "legacy-release.tar.gz"
        with tarfile.open(legacy_backup, "x:gz") as tar:
            tar.add(release, arcname=release.name, recursive=True)
        os.chmod(legacy_backup, 0o600)
        with tarfile.open(legacy_backup, "r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile():
                    with tar.extractfile(member) as f:
                        require(hashlib.sha256(f.read()).hexdigest() == sha(self.base / member.name), "Legacy backup validation failed.")
        env_dir = self.private / "service-env"
        require(not env_dir.exists(), "service-env already exists; review prior adoption.")
        env_dir.mkdir(mode=0o700)
        self.runtime.mkdir(mode=0o700)
        shutil.copytree(release / "database/init", self.runtime / "database/init")
        build_args = model["services"]["frontend"].get("build", {}).get("args", {})
        write_json(self.private / "build-args.json", build_args)
        output = {"name": PROJECT, "services": {}, "networks": {}, "volumes": {}}
        for section in ("networks", "volumes"):
            output[section] = {key: {"external": True, "name": value["name"]} for key, value in model[section].items()}
        for service in SERVICES:
            definition = copy.deepcopy(model["services"][service])
            definition.pop("build", None)
            environment = definition.pop("environment", {})
            actual = env_map(old[service])
            require(all(actual.get(k) == str(v) for k, v in environment.items()), "Effective environment mismatch.")
            env_path = env_dir / (service + ".env")
            with env_path.open("x", encoding="utf-8") as f:
                for key, value in sorted(environment.items()):
                    require(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and "\n" not in str(value) and "\r" not in str(value), "Unsupported environment value.")
                    f.write(key + "=" + str(value) + "\n")
            os.chmod(env_path, 0o600)
            definition["env_file"] = [{"path": str(env_path), "format": "raw"}]
            if service == "database":
                definition["image"] = old[service]["Image"]
            else:
                tag = "safealley-vm/" + service + ":adopt-" + old[service]["Image"].split(":")[-1][:20]
                run(["docker", "image", "tag", old[service]["Image"], tag])
                definition["image"] = tag
            for mount in definition.get("volumes", []):
                if mount["target"] == "/docker-entrypoint-initdb.d":
                    mount["source"] = str(self.runtime / "database/init")
                    mount["bind"] = {"create_host_path": False}
            output["services"][service] = definition
        write_json(self.config, output)
        run(self.compose("config", "--quiet"))
        package = self.save_package(archive, manifest)
        new_state = {"commit": manifest["base_commit"], "hashes": manifest["sha256"], "package": str(package),
                     "checkpoint": str(checkpoint), "previous": None, "database_revision": self.database_revision()}
        try:
            self.recreate(SERVICES, checkpoint)
            self.verify(old, adopt=True)
        except Exception:
            print("Adoption failed; restoring original Compose configuration.", flush=True)
            for service in SERVICES:
                run(legacy_cmd + ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", service],
                    log=checkpoint / (service + "-restore.log"))
            raise
        write_json(self.state, new_state)
        shutil.copyfile(Path(__file__), self.runtime / "update.py")
        os.chmod(self.runtime / "update.py", 0o600)
        print("ADOPTED: fixed runtime paths. Run finalize explicitly after verification.", flush=True)

    def finalize(self):
        state = load(self.state)
        self.verify()
        legacy = self.base / ("main-" + state["commit"][:7])
        require(legacy.parent == self.base and legacy.resolve() == legacy and not legacy.is_symlink(), "Unsafe legacy directory.")
        if legacy.exists():
            require((Path(state["checkpoint"]) / "legacy-release.tar.gz").is_file(), "Missing adoption rollback archive.")
            assert_unreferenced([legacy], self.live(all_containers=True))
            for p in self.runtime.rglob("*"):
                if p.is_file():
                    require(str(legacy) not in p.read_text(errors="replace") or p.name == "state.json", "Runtime still references legacy source.")
            # Only this exact, verified old source tree is removed. Never delete volumes/private.
            shutil.rmtree(legacy)
        archive = self.base / ("SafeAlley-main-" + state["commit"][:7] + ".tar.gz")
        if archive.exists():
            require(archive.resolve() == archive and sha(archive) == sha(Path(state["package"])), "Legacy archive differs from retained package.")
            archive.unlink(); Path(str(archive) + ".sha256").unlink()
        previous = self.private / "SafeAlley-main-ab1132a.tar.gz"
        if previous.exists():
            with tempfile.TemporaryDirectory(prefix="safealley-previous-") as temp:
                manifest = unpack(previous, Path(temp))
            self.save_package(previous, manifest)
            previous.unlink(); Path(str(previous) + ".sha256").unlink()
        print("FINALIZED: runtime/, private/, packages/; uncompressed release source removed.", flush=True)

    def update(self, archive, allow_migration=False, rebuild=False):
        require(not (self.runtime / "pending.json").exists(), "Unresolved deployment exists; review runtime/pending.json before retrying.")
        state = load(self.state)
        self.verify()
        before = self.live()
        with tempfile.TemporaryDirectory(prefix="safealley-build-") as temp:
            source = Path(temp)
            manifest = unpack(archive, source)
            migrations = check_contract(state["hashes"], manifest["sha256"], allow_migration,
                                        runtime_services=load(self.config)["services"])
            if manifest["base_commit"] == state["commit"] and not rebuild:
                require(manifest["sha256"] == state["hashes"], "Same commit with different source content refused.")
                self.consume_upload(archive, state)
                self.auto_clean_images()
                print("ALREADY CURRENT: no build or replacement performed."); return
            require(shutil.disk_usage(self.base).free >= 5 * 1024**3, "At least 5 GiB free space is required.")
            changed = [s for s in APPS if rebuild or subset(state["hashes"], PREFIX[s]) != subset(manifest["sha256"], PREFIX[s])]
            checkpoint = self.backup("update")
            old_model = load(self.config)
            model = copy.deepcopy(old_model)
            args = load(self.private / "build-args.json")
            # Never overwrite an existing release tag, including same-second rebuilds.
            tags = {s: release_image_tag(s, manifest["base_commit"], checkpoint.name.split("-", 1)[1]) for s in changed}
            existing = {r for image in self.images() for r in image_refs(image)} if changed else set()
            require(not (set(tags.values()) & existing), "같은 배포 이미지 이름이 이미 있습니다. 기존 이미지는 덮어쓰지 않습니다. 잠시 후 다시 실행하세요.")
            for service in changed:
                tag = tags[service]
                command = ["docker", "build", "--tag", tag]
                environment = os.environ.copy()
                if service == "frontend":
                    for key, value in args.items():
                        environment[key] = str(value)
                        command += ["--build-arg", key]
                command += [str(source / PREFIX[service].rstrip("/"))]
                print("Building " + service + "; private log: " + str(checkpoint / (service + "-build.log")), flush=True)
                run(command, log=checkpoint / (service + "-build.log"), env=environment)
                model["services"][service]["image"] = tag
            # Verify TLS configuration against the new frontend image before replacing anything.
            candidate = self.runtime / "candidate.compose.json"
            write_json(candidate, model)
            try:
                candidate_cmd = ["docker", "compose", "--project-directory", str(self.runtime), "-p", PROJECT, "-f", str(candidate)]
                run(candidate_cmd + ["config", "--quiet"])
                run(candidate_cmd + ["run", "--rm", "--no-deps", "--pull", "never", "frontend", "nginx", "-t"], log=checkpoint / "nginx-test.log")
            finally:
                candidate.unlink(missing_ok=True)
            package = self.save_package(archive, manifest)
            old_revision = self.database_revision()
            write_json(self.runtime / "pending.json", {"checkpoint": str(checkpoint), "target_commit": manifest["base_commit"]})
            try:
                write_json(self.config, model)
                self.recreate(changed, checkpoint)
                self.verify(before)
                revision = self.database_revision()
                require(migrations or revision == old_revision, "Unexpected database revision change.")
            except Exception:
                if migrations or self.database_revision() != old_revision:
                    print("STOP: migration was attempted or schema changed. No automatic DB restore/downgrade or old-backend restart. Backup: " + str(checkpoint), flush=True)
                    raise
                write_json(self.config, old_model)
                self.recreate(changed, checkpoint)
                self.verify(before)
                print("Previous app images restored. Database was not restored or deleted.", flush=True)
                (self.runtime / "pending.json").unlink()
                raise
            previous = {"commit": state["commit"], "package": state["package"], "checkpoint": str(checkpoint)}
            new_state = {"commit": manifest["base_commit"], "hashes": manifest["sha256"], "package": str(package),
                         "checkpoint": str(checkpoint), "previous": previous, "database_revision": revision}
            write_json(self.state, new_state)
            write_json(checkpoint / "complete.json", {"commit": new_state["commit"]})
            (self.runtime / "pending.json").unlink()
            if state["commit"] != new_state["commit"]:
                try:
                    self.prune(new_state)
                except (RuntimeError, OSError):
                    print("WARNING: update succeeded; old package/backup cleanup stopped for safety.", flush=True)
            self.consume_upload(archive, new_state)
            self.auto_clean_images()
        print("UPDATED " + new_state["commit"] + "; temporary source removed; previous images and DB checkpoint retained.", flush=True)

    def prune(self, state):
        """Only updater-owned packages and completed checkpoints; never generic Docker prune."""
        keep = {Path(state["package"])}
        if state.get("previous"):
            keep.add(Path(state["previous"]["package"]))
        for p in self.packages.iterdir():
            if re.fullmatch(r"SafeAlley-[a-f0-9]{40}\.tar\.gz", p.name) and p not in keep:
                require(p.resolve() == p and not p.is_symlink() and p.is_file(), "Unsafe package pruning target.")
                assert_unreferenced([p], self.live(all_containers=True))
                p.unlink()
                Path(str(p) + ".sha256").unlink(missing_ok=True)
        root = self.private / "updates"
        completed = sorted(p for p in root.iterdir() if re.fullmatch(r"update-[0-9]{8}T[0-9]{12}Z", p.name)
                           and (p / "complete.json").is_file())
        preserve = {Path(state["checkpoint"])}
        if state.get("previous"):
            preserve.add(Path(state["previous"]["checkpoint"]))
        for p in completed[:-2]:
            if p in preserve:
                continue
            require(p.resolve() == p and p.parent == root and not p.is_symlink(), "Unsafe backup pruning target.")
            assert_unreferenced([p], self.live(all_containers=True))
            shutil.rmtree(p)

    def rollback(self):
        require(not (self.runtime / "pending.json").exists(), "Unresolved deployment exists; review pending.json first.")
        state = load(self.state)
        require(state.get("previous"), "No application update rollback checkpoint yet.")
        checkpoint = Path(state["previous"]["checkpoint"])
        require(checkpoint.resolve().is_relative_to(self.private / "updates"), "Unsafe checkpoint path.")
        require(self.database_revision() == load(checkpoint / "checkpoint.json")["revision"],
                "Database schema changed; app-only rollback refused. Review DB compatibility manually.")
        before = self.live()
        old = load(checkpoint / "compose.json")
        self.backup("rollback")
        write_json(self.config, old)
        self.recreate(APPS, checkpoint)
        self.verify(before)
        previous_state = load(checkpoint / "state.json")
        previous_state["previous"] = None
        write_json(self.state, previous_state)
        print("ROLLED BACK application images only; DB/GPU/tunnels/certificates retained.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    sub = parser.add_subparsers(dest="command", required=True)
    adopt = sub.add_parser("adopt")
    adopt.add_argument("--release", type=Path, required=True)
    sub.add_parser("finalize")
    sub.add_parser("status")
    sub.add_parser("rollback")
    cleanup = sub.add_parser("clean-images", help="현재·직전 복구 이미지를 보존하고 오래된 SafeAlley 이미지만 정리합니다.")
    cleanup.add_argument("--dry-run", action="store_true", help="삭제하지 않고 정리 대상만 확인합니다.")
    update = sub.add_parser("update")
    update.add_argument("--archive", type=Path, required=True)
    update.add_argument("--allow-migration", action="store_true")
    update.add_argument("--rebuild", action="store_true", help="Rebuild all three application images, even for the same commit.")
    args = parser.parse_args()
    require(os.name == "posix" and sys.version_info >= (3, 10), "Run on Linux VM with Python 3.10+.")
    os.umask(0o077)
    vm = VM(args.base)
    with vm.lock():
        if args.command == "adopt": vm.adopt(args.release)
        elif args.command == "finalize": vm.finalize()
        elif args.command == "update": vm.update(args.archive.absolute(), args.allow_migration, args.rebuild)
        elif args.command == "rollback": vm.rollback()
        elif args.command == "clean-images":
            vm.verify()
            vm.clean_images(args.dry_run)
            vm.verify()
        else:
            vm.verify()
            state = load(vm.state)
            print("CURRENT " + state["commit"] + "\nPACKAGE " + state["package"])
            if (vm.runtime / "pending.json").exists():
                print("WARNING: unresolved deployment journal exists; do not run another update.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, tarfile.TarError) as error:
        print("STOP: " + str(error), file=sys.stderr)
        sys.exit(1)
