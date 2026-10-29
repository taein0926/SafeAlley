"""Updater safety tests: no network, Docker daemon, real secrets, or production DB."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import vm_update as updater


FILES = {
    "docker-compose.yml": b"services: {}\n",
    "frontend/nginx.conf": b"server { listen 80; }\n",
    "backend/Dockerfile": b"FROM python:3.12-slim\n",
    "frontend/Dockerfile": b"FROM nginx:1.27-alpine\n",
    "data_pipeline/Dockerfile": b"FROM python:3.12-slim\n",
    "database/init/001_extensions.sql": b"CREATE EXTENSION IF NOT EXISTS postgis;\n",
    "backend/alembic/versions/0016.py": b"revision='0016'\n",
}


def make_archive(folder, payload=None, extra=None):
    payload = FILES if payload is None else payload
    archive = folder / "release.tar.gz"
    manifest = {"format": "safealley-source-deployment-v1", "base_commit": "a" * 40,
                "sha256": {k: hashlib.sha256(v).hexdigest() for k, v in payload.items()}}
    with tarfile.open(archive, "w:gz") as tar:
        for name, value in {**payload, "release.json": json.dumps(manifest).encode()}.items():
            info = tarfile.TarInfo("SafeAlley/" + name)
            info.size = len(value)
            tar.addfile(info, io.BytesIO(value))
        if extra:
            info, data = extra
            tar.addfile(info, io.BytesIO(data) if data is not None else None)
    Path(str(archive) + ".sha256").write_text(updater.sha(archive) + "\n")
    return archive, manifest


class ModelProbeTests(unittest.TestCase):
    def probe(self, device='cpu', checkpoint='expected', ready=True):
        connection = MagicMock()
        connection.getresponse.return_value.status = 302
        connection.getresponse.return_value.getheader.return_value = 'https://ltmetric-pms.synology.me:21802/'
        env = {'OLLAMA_BASE_URL': 'http://gemma', 'OLLAMA_MODEL': 'gemma4:e2b-it-qat',
               'STT_REMOTE_URL': 'http://whisper', 'INTENT_PREVIEW_PROVIDER': 'laya',
               'LAYA_PREVIEW_URL': 'http://laya', 'LAYA_CHECKPOINT_SHA256': 'expected'}
        responses = {'http://gemma/api/tags': {'models': [{'name': env['OLLAMA_MODEL']}]},
                     'http://whisper/health': {'ready': ready, 'device': device},
                     'http://laya/health': {'ready': True, 'checkpoint_sha256': checkpoint}}
        def run(args):
            if args[0] == 'curl':
                return '<script src="/assets/app.js"></script>' if args[-1].endswith('/') else 'ok'
            with patch.dict(os.environ, env, clear=True), patch('urllib.request.urlopen',
                    side_effect=lambda url, **kw: io.StringIO(json.dumps(responses[url]))):
                exec(args[-1], {})
            return 'MODEL_ENDPOINTS_OK'
        with patch.object(updater.http.client, 'HTTPConnection', return_value=connection), patch.object(updater, 'run', side_effect=run):
            updater.VM('/unused').probe_connections()

    def test_cpu_and_cuda_workers_are_supported(self):
        for device in ('cpu', 'cuda'):
            with self.subTest(device=device): self.probe(device=device)

    def test_unready_or_unexpected_model_is_rejected(self):
        for options in ({'ready': False}, {'device': 'unknown'}, {'checkpoint': 'wrong'}):
            with self.subTest(options=options), self.assertRaises(AssertionError): self.probe(**options)


class ArchiveTests(unittest.TestCase):
    def test_valid_archive_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive, expected = make_archive(root)
            dest = root / "source"; dest.mkdir()
            self.assertEqual(updater.unpack(archive, dest), expected)
            self.assertEqual((dest / "backend/Dockerfile").read_bytes(), FILES["backend/Dockerfile"])

    def test_checksum_accepts_hash_only_and_standard_sha256sum(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "source.tar.gz"; p.write_bytes(b"test")
            for suffix in ["\n", "  source.tar.gz\n", " *source.tar.gz\n"]:
                Path(str(p) + ".sha256").write_text(updater.sha(p) + suffix)
                self.assertEqual(updater.checksum(p), updater.sha(p))

    def test_wrong_checksum_rejected_before_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, _ = make_archive(Path(tmp))
            Path(str(p) + ".sha256").write_text("0" * 64)
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                updater.checksum(p)

    def test_unsafe_names(self):
        for name in ["../escape", "/absolute", "a/../b", "a\\b", "backend/.env", "private/x", "backend/key.pem", "a//b"]:
            with self.subTest(name=name): self.assertFalse(updater.source_name(name))
        self.assertTrue(updater.source_name(".env.example"))

    def test_special_or_traversal_tar_members_rejected(self):
        for name, kind in [("SafeAlley/../escape", tarfile.REGTYPE),
                           ("SafeAlley/link", tarfile.SYMTYPE), ("SafeAlley/device", tarfile.CHRTYPE)]:
            with self.subTest(name=name, kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); info = tarfile.TarInfo(name); info.type = kind; info.linkname = "/etc/passwd"
                p, _ = make_archive(root, extra=(info, None))
                dest = root / "source"; dest.mkdir()
                with self.assertRaises(RuntimeError): updater.unpack(p, dest)

    def test_duplicate_members_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); info = tarfile.TarInfo("SafeAlley/backend/Dockerfile"); info.size = 1
            p, _ = make_archive(root, extra=(info, b"x"))
            dest = root / "source"; dest.mkdir()
            with self.assertRaisesRegex(RuntimeError, "duplicate"): updater.unpack(p, dest)

    def test_unlisted_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); info = tarfile.TarInfo("SafeAlley/extra.txt"); info.size = 1
            p, _ = make_archive(root, extra=(info, b"x"))
            dest = root / "source"; dest.mkdir()
            with self.assertRaisesRegex(RuntimeError, "differ from manifest"): updater.unpack(p, dest)

    def test_extraction_size_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p, _ = make_archive(root)
            dest = root / "source"; dest.mkdir()
            with patch.object(updater, "MAX_SOURCE_BYTES", 1), self.assertRaisesRegex(RuntimeError, "safety limit"):
                updater.unpack(p, dest)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.old = {k: hashlib.sha256(v).hexdigest() for k, v in FILES.items()}

    def test_unchanged_contract_allowed(self):
        self.assertFalse(updater.check_contract(self.old, self.old))

    def test_app_change_allowed(self):
        new = {**self.old, "backend/app/example.py": "b" * 64}
        self.assertFalse(updater.check_contract(self.old, new))

    def reviewed_hashes(self):
        before, after = next(iter(updater.REVIEWED_COMPOSE_TRANSITIONS))
        return {**self.old, "docker-compose.yml": before}, {**self.old, "docker-compose.yml": after}

    def test_reviewed_tools_default_change_allowed_for_fixed_four_services(self):
        old, new = self.reviewed_hashes()
        self.assertFalse(updater.check_contract(old, new, runtime_services=updater.SERVICES))

    def test_review_requires_explicit_fixed_runtime_without_pipeline(self):
        old, new = self.reviewed_hashes()
        for services in [None, ("backend",), (*updater.SERVICES, "pipeline"), (*updater.SERVICES, "ollama")]:
            with self.subTest(services=services), self.assertRaises(RuntimeError):
                updater.check_contract(old, new, runtime_services=services)

    def test_review_does_not_allow_other_protected_changes(self):
        old, new = self.reviewed_hashes()
        for name in ["frontend/nginx.conf", "database/init/001_extensions.sql"]:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                updater.check_contract(old, {**new, name: "c" * 64}, runtime_services=updater.SERVICES)

    def test_review_does_not_allow_reverse_or_unknown_compose_hash(self):
        old, new = self.reviewed_hashes()
        for before, after in [(new, old), (old, {**new, "docker-compose.yml": "c" * 64})]:
            with self.assertRaises(RuntimeError):
                updater.check_contract(before, after, runtime_services=updater.SERVICES)

    def test_reviewed_pair_matches_exactly_one_pipeline_default_line(self):
        root = Path(__file__).resolve().parents[1]
        current = (root / "docker-compose.yml").read_text(encoding="utf-8")
        line = "OSM_SAFETY_SCORE_MODE: ${OSM_SAFETY_SCORE_MODE:-uniform}"
        self.assertEqual(current.count(line), 1)
        previous = current.replace(line, "OSM_SAFETY_SCORE_MODE: ${OSM_SAFETY_SCORE_MODE:-demo}")
        pair = (hashlib.sha256(previous.encode()).hexdigest(), hashlib.sha256(current.encode()).hexdigest())
        self.assertIn(pair, updater.REVIEWED_COMPOSE_TRANSITIONS)

    def test_runtime_changes_require_manual_review(self):
        for name in ["docker-compose.yml", "frontend/nginx.conf", "database/init/001_extensions.sql"]:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                updater.check_contract(self.old, {**self.old, name: "b" * 64})

    def test_added_migration_requires_opt_in(self):
        new = {**self.old, "backend/alembic/versions/0017.py": "b" * 64}
        with self.assertRaisesRegex(RuntimeError, "allow-migration"):
            updater.check_contract(self.old, new)
        self.assertTrue(updater.check_contract(self.old, new, True))

    def test_old_migration_cannot_be_rewritten_even_with_opt_in(self):
        with self.assertRaisesRegex(RuntimeError, "history"):
            updater.check_contract(self.old, {**self.old, "backend/alembic/versions/0016.py": "b" * 64}, True)

    def test_stopped_container_reference_blocks_cleanup(self):
        target = Path("/release")
        container = {"State": {"Running": False}, "Config": {"Labels": {}},
                     "Mounts": [{"Source": "/release/database/init"}]}
        with self.assertRaisesRegex(RuntimeError, "references"):
            updater.assert_unreferenced([target], [container])


class UpdateTests(unittest.TestCase):
    def setUp(self):
        images = patch.object(updater.VM, "images", return_value=[])
        images.start()
        self.addCleanup(images.stop)
        disk = patch.object(updater.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 20 * 1024 ** 3})())
        disk.start()
        self.addCleanup(disk.stop)

    def setup_vm(self, root):
        vm = updater.VM(root)
        vm.runtime.mkdir(); vm.private.mkdir(); vm.packages.mkdir()
        (vm.private / "build-args.json").write_text("{}")
        old_hashes = {k: hashlib.sha256(v).hexdigest() for k, v in FILES.items()}
        state = {"commit": "b" * 40, "hashes": old_hashes, "package": str(vm.packages / "old.tar.gz")}
        model = {"services": {s: {"image": "old-" + s} for s in updater.SERVICES}}
        updater.write_json(vm.state, state); updater.write_json(vm.config, model)
        folder = vm.private / "updates/update-20261020T110000123456Z"; folder.mkdir(parents=True)
        updater.write_json(folder / "checkpoint.json", {"revision": "0016"})
        updater.write_json(folder / "compose.json", model); updater.write_json(folder / "state.json", state)
        return vm, folder, model

    def test_build_failure_does_not_replace_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, model = self.setup_vm(root)
            payload = {**FILES, "frontend/src/example.ts": b"updated"}
            p, _ = make_archive(root, payload)
            with patch.object(vm, "verify"), patch.object(vm, "live", return_value={}), patch.object(vm, "backup", return_value=folder), \
                 patch.object(vm, "recreate") as recreate, patch.object(updater, "run", side_effect=RuntimeError("build failed")):
                with self.assertRaisesRegex(RuntimeError, "build failed"): vm.update(p)
            self.assertEqual(updater.load(vm.config), model)
            recreate.assert_not_called()
            self.assertFalse((vm.runtime / "pending.json").exists())

    def test_same_commit_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, model = self.setup_vm(root)
            p, manifest = make_archive(root)
            state = updater.load(vm.state); state['commit'] = manifest['base_commit']; updater.write_json(vm.state, state)
            with patch.object(vm, "verify"), patch.object(vm, "live"), patch.object(vm, "backup") as backup, \
                 patch.object(vm, "auto_clean_images") as cleanup:
                vm.update(p)
            backup.assert_not_called()
            cleanup.assert_called_once()

    def test_replacement_failure_restores_previous_config_without_db_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, model = self.setup_vm(root)
            p, _ = make_archive(root, {**FILES, "frontend/src/example.ts": b"new"})
            with patch.object(vm, "verify"), patch.object(vm, "live", return_value={}), patch.object(vm, "backup", return_value=folder), \
                 patch.object(vm, "database_revision", return_value="0016"), patch.object(vm, "recreate", side_effect=[RuntimeError("replace failed"), None]) as recreate, \
                 patch.object(updater, "run") as command:
                with self.assertRaisesRegex(RuntimeError, "replace failed"): vm.update(p)
            self.assertEqual(updater.load(vm.config), model)
            self.assertEqual(recreate.call_count, 2)
            self.assertFalse((vm.runtime / "pending.json").exists())
            self.assertFalse(any('pg_restore' in call.args[0] for call in command.call_args_list))

    def test_schema_change_failure_does_not_restart_old_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, model = self.setup_vm(root)
            p, _ = make_archive(root, {**FILES, "backend/alembic/versions/0017.py": b"new"})
            with patch.object(vm, "verify"), patch.object(vm, "live", return_value={}), patch.object(vm, "backup", return_value=folder), \
                 patch.object(vm, "database_revision", side_effect=["0016", "0017"]), patch.object(vm, "recreate", side_effect=RuntimeError("failed")) as recreate, \
                 patch.object(updater, "run"):
                with self.assertRaisesRegex(RuntimeError, "failed"): vm.update(p, allow_migration=True)
            self.assertEqual(recreate.call_count, 1)
            self.assertTrue((vm.runtime / "pending.json").exists())

    def test_pending_operation_blocks_next_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, _, _ = self.setup_vm(root)
            updater.write_json(vm.runtime / "pending.json", {})
            with self.assertRaisesRegex(RuntimeError, "Unresolved"): vm.update(root / "not-opened.tar.gz")

    def test_fixed_compose_command_never_builds_from_release_folder(self):
        vm = updater.VM(Path('/example'))
        command = vm.compose('up', '-d', '--no-build', '--no-deps', 'frontend')
        self.assertIn(str(vm.runtime), command)
        self.assertIn(str(vm.config), command)
        self.assertNotIn('down', command)

    def test_success_advances_state_keeps_database_and_removes_temp_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, model = self.setup_vm(root)
            p, manifest = make_archive(root, {**FILES, "frontend/src/example.ts": b"new"})
            with patch.object(vm, "verify"), patch.object(vm, "live", return_value={}), patch.object(vm, "backup", return_value=folder), \
                 patch.object(vm, "database_revision", return_value="0016"), patch.object(vm, "recreate") as recreate, \
                 patch.object(vm, "prune"), patch.object(vm, "auto_clean_images") as cleanup, patch.object(updater, "run") as command:
                vm.update(p)
            cleanup.assert_called_once()
            state = updater.load(vm.state)
            self.assertEqual(state['commit'], manifest['base_commit'])
            self.assertEqual(state['previous']['commit'], 'b' * 40)
            self.assertEqual(updater.load(vm.config)['services']['database'], model['services']['database'])
            self.assertEqual(recreate.call_args.args[0], ['frontend'])
            build_command = next(c.args[0] for c in command.call_args_list if c.args[0][:2] == ['docker', 'build'])
            self.assertIn('safealley-release/frontend:20261020-200000-aaaaaaa', build_command)
            self.assertFalse(Path(build_command[-1]).exists())
            self.assertFalse((vm.runtime / 'pending.json').exists())

    def test_new_packaging_timestamp_for_same_source_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, _, _ = self.setup_vm(root)
            p, manifest = make_archive(root)
            retained = vm.save_package(p, manifest)
            first_hash = updater.sha(retained)
            payload = copy.deepcopy(manifest)
            payload['created_utc'] = 'different timestamp'
            with tarfile.open(p, 'w:gz') as tar:
                for name, value in {**FILES, 'release.json': json.dumps(payload).encode()}.items():
                    info = tarfile.TarInfo('SafeAlley/' + name); info.size = len(value)
                    tar.addfile(info, io.BytesIO(value))
            Path(str(p) + '.sha256').write_text(updater.sha(p))
            self.assertEqual(vm.save_package(p, manifest), retained)
            self.assertEqual(updater.sha(retained), first_hash)
            updater.checksum(retained)

    def test_pruning_only_owns_canonical_packages_and_completed_update_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, _ = self.setup_vm(root)
            current = vm.packages / ('SafeAlley-' + 'a' * 40 + '.tar.gz')
            previous = vm.packages / ('SafeAlley-' + 'b' * 40 + '.tar.gz')
            obsolete = vm.packages / ('SafeAlley-' + 'c' * 40 + '.tar.gz')
            unrelated = vm.packages / 'manual-archive.tar.gz'
            for p in [current, previous, obsolete, unrelated]: p.write_bytes(b'test')
            preserved = vm.private / 'tls-f6b47f3'; preserved.mkdir(); (preserved/'safealley.key').write_bytes(b'protected')
            state = {'package': str(current), 'checkpoint': str(folder), 'previous': {'package': str(previous), 'checkpoint': str(folder)}}
            with patch.object(vm, 'live', return_value=[]): vm.prune(state)
            self.assertFalse(obsolete.exists())
            for p in [current, previous, unrelated, preserved/'safealley.key']: self.assertTrue(p.exists())

    def test_existing_release_tag_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, folder, model = self.setup_vm(root)
            p, _ = make_archive(root, {**FILES, "frontend/src/example.ts": b"new"})
            existing = image_fixture("c", "safealley-release/frontend:20261020-200000-aaaaaaa")
            with patch.object(vm, "verify"), patch.object(vm, "live", return_value={}), \
                 patch.object(vm, "backup", return_value=folder), patch.object(vm, "images", return_value=[existing]), \
                 patch.object(updater, "run") as command:
                with self.assertRaisesRegex(RuntimeError, "덮어쓰지"): vm.update(p)
            command.assert_not_called()
            self.assertEqual(updater.load(vm.config), model)
            self.assertFalse((vm.runtime / "pending.json").exists())

    @unittest.skipUnless(os.name == 'posix', 'Linux flock test runs on the VM')
    def test_concurrent_update_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, _, _ = self.setup_vm(root)
            with vm.lock():
                with self.assertRaisesRegex(RuntimeError, 'Another deployment'):
                    with vm.lock(): pass


def image_fixture(letter, *tags, digests=()):
    return {"Id": "sha256:" + letter * 64, "RepoTags": list(tags), "RepoDigests": list(digests)}


class ImageCleanupTests(unittest.TestCase):
    def setUp(self):
        self.old = image_fixture("a", "safealley-vm/backend:old")

    def test_only_explicit_owned_repositories_are_candidates(self):
        images = [self.old, image_fixture("b", "workhub-server/workhub:old"),
                  image_fixture("c", "safealley-unknown:old"), image_fixture("d")]
        self.assertEqual(updater.image_cleanup_plan(images, [], []), {"safealley-vm/backend:old": self.old["Id"]})

    def test_release_namespace_cleanup_and_shared_alias_protection(self):
        release = image_fixture("b", "safealley-release/backend:20261020-144545-9babb6f")
        shared = image_fixture("c", "safealley-release/frontend:old", "workhub-release/frontend:old")
        self.assertEqual(updater.image_cleanup_plan([release, shared], [], []),
                         {release["RepoTags"][0]: release["Id"]})
        self.assertEqual(updater.image_cleanup_plan([release], [], [release["Id"]]), {})

    def test_release_database_current_id_is_protected(self):
        database = image_fixture("d", "safealley-release/database:postgres17-postgis3.5")
        self.assertEqual(updater.image_cleanup_plan([database], [], [database["Id"]]), {})
        self.assertEqual(updater.image_cleanup_plan([database], [{"Image": database["Id"]}], []), {})
        self.assertEqual(updater.image_cleanup_plan([database], [], []),
                         {database["RepoTags"][0]: database["Id"]})

    def test_current_and_previous_ids_protected_with_all_aliases(self):
        previous = image_fixture("b", "safealley-vm/frontend:previous", "safealley-frontend:alias")
        self.assertEqual(updater.image_cleanup_plan([self.old, previous], [], [self.old["Id"], previous["Id"]]), {})

    def test_stopped_other_container_protects_owned_image(self):
        stopped = {"Id": "other", "Image": self.old["Id"], "State": {"Running": False}}
        self.assertEqual(updater.image_cleanup_plan([self.old], [stopped], []), {})

    def test_shared_foreign_tag_protects_entire_image(self):
        shared = image_fixture("a", "safealley-vm/backend:old", "workhub-server/workhub:backup")
        self.assertEqual(updater.image_cleanup_plan([shared], [], []), {})

    def test_shared_foreign_digest_protects_entire_image(self):
        shared = image_fixture("a", "safealley-vm/backend:old", digests=["workhub-server/workhub@sha256:" + "a"*64])
        self.assertEqual(updater.image_cleanup_plan([shared], [], []), {})

    def test_owned_digests_are_explicit_candidates(self):
        image = image_fixture("a", "safealley-vm/backend:old", digests=["safealley-vm/backend@sha256:" + "a"*64])
        self.assertEqual(set(updater.image_cleanup_plan([image], [], [])), set(updater.image_refs(image)))

    def setup_cleanup(self, root):
        vm, folder, model = UpdateTests().setup_vm(root)
        keep = image_fixture("b", "safealley-vm/backend:current")
        state = updater.load(vm.state); state["checkpoint"] = str(folder)
        updater.write_json(vm.state, state)
        return vm, folder, keep

    def test_dry_run_never_removes_images_or_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, folder, keep = self.setup_cleanup(Path(tmp))
            with patch.object(vm, "retained_images", return_value={"current": keep["Id"]}), \
                 patch.object(vm, "images", return_value=[self.old, keep]), patch.object(vm, "live", return_value=[]), \
                 patch.object(updater, "run") as command:
                self.assertEqual(vm.clean_images(True)["planned_images"], 1)
            command.assert_not_called()
            self.assertFalse(list(folder.glob("image-cleanup-*")))

    def test_cleanup_removes_exact_tag_without_force_or_parent_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, folder, keep = self.setup_cleanup(Path(tmp))
            foreign = image_fixture("c", "workhub-server/workhub:old")
            container = {"Id": "workhub", "Image": foreign["Id"]}
            with patch.object(vm, "retained_images", return_value={"current": keep["Id"]}), \
                 patch.object(vm, "images", side_effect=[[self.old, keep, foreign], [self.old, keep, foreign], [keep, foreign]]), \
                 patch.object(vm, "live", return_value=[container]), patch.object(updater, "run") as command:
                result = vm.clean_images()
            command.assert_called_once_with(["docker", "image", "rm", "--no-prune", "safealley-vm/backend:old"])
            self.assertTrue(result["complete"])
            self.assertEqual(result["removed_images"], 1)
            self.assertTrue(list(folder.glob("image-cleanup-*")))

    def test_new_container_reference_prevents_previously_planned_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, keep = self.setup_cleanup(Path(tmp))
            with patch.object(vm, "retained_images", return_value={"current": keep["Id"]}), \
                 patch.object(vm, "images", return_value=[self.old, keep]), \
                 patch.object(vm, "live", side_effect=[[], [{"Id": "new", "Image": self.old["Id"]}], []]), \
                 patch.object(updater, "run") as command:
                result = vm.clean_images()
            command.assert_not_called()
            self.assertEqual(result["removed_images"], 0)

    def test_retagged_candidate_is_not_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, keep = self.setup_cleanup(Path(tmp))
            replacement = image_fixture("c", "safealley-vm/backend:old")
            with patch.object(vm, "retained_images", return_value={"current": keep["Id"]}), \
                 patch.object(vm, "images", side_effect=[[self.old, keep], [replacement, keep], [replacement, keep]]), \
                 patch.object(vm, "live", return_value=[]), patch.object(updater, "run") as command:
                vm.clean_images()
            command.assert_not_called()

    def test_missing_previous_checkpoint_refuses_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, _ = self.setup_cleanup(Path(tmp))
            state = updater.load(vm.state)
            state["previous"] = {"commit": "c"*40, "checkpoint": str(vm.private / "updates/missing")}
            with self.assertRaises(OSError): vm.retained_images(state)

    def test_pending_update_refuses_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, _ = self.setup_cleanup(Path(tmp))
            updater.write_json(vm.runtime / "pending.json", {})
            with self.assertRaisesRegex(RuntimeError, "미완료"): vm.retained_images(updater.load(vm.state))

    def test_current_and_previous_compose_references_are_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, folder, _ = self.setup_cleanup(Path(tmp))
            state = updater.load(vm.state)
            state["previous"] = {"commit": state["commit"], "checkpoint": str(folder)}
            current = {"services": {s: {"image": "safealley-vm/backend:current-" + s} for s in updater.SERVICES}}
            updater.write_json(vm.config, current)
            with patch.object(updater, "run", return_value=json.dumps([{"Id": self.old["Id"]}])) as command:
                retained = vm.retained_images(state)
            self.assertEqual(len(retained), 8)
            self.assertEqual(command.call_count, 8)

    def test_missing_retained_docker_image_stops_before_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, _ = self.setup_cleanup(Path(tmp))
            with patch.object(updater, "run", side_effect=RuntimeError("missing image")) as command:
                with self.assertRaisesRegex(RuntimeError, "missing image"): vm.clean_images()
            self.assertEqual(command.call_args.args[0][:3], ["docker", "image", "inspect"])

    def test_docker_removal_failure_stops_without_force_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, keep = self.setup_cleanup(Path(tmp))
            with patch.object(vm, "retained_images", return_value={"current": keep["Id"]}), \
                 patch.object(vm, "images", return_value=[self.old, keep]), patch.object(vm, "live", return_value=[]), \
                 patch.object(updater, "run", side_effect=RuntimeError("in use")) as command:
                with self.assertRaisesRegex(RuntimeError, "in use"): vm.clean_images()
            command.assert_called_once_with(["docker", "image", "rm", "--no-prune", "safealley-vm/backend:old"])

    def test_foreign_reference_postcheck_detects_unexpected_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            vm, _, keep = self.setup_cleanup(Path(tmp))
            foreign = image_fixture("c", "workhub-server/workhub:old")
            with patch.object(vm, "retained_images", return_value={"current": keep["Id"]}), \
                 patch.object(vm, "images", side_effect=[[keep, foreign], [keep]]), \
                 patch.object(vm, "live", return_value=[]), patch.object(updater, "run") as command:
                with self.assertRaisesRegex(RuntimeError, "다른 프로젝트"): vm.clean_images()
            command.assert_not_called()

    def test_cleanup_failure_does_not_fail_successful_deployment(self):
        vm = updater.VM("/unused")
        with patch.object(vm, "clean_images", side_effect=RuntimeError("blocked")):
            vm.auto_clean_images()


class ReleaseImageTagTests(unittest.TestCase):
    def test_korean_time_and_short_commit(self):
        self.assertEqual(updater.release_image_tag("backend", "9babb6f" + "0" * 33, "20261020T054545935592Z"),
                         "safealley-release/backend:20261020-144545-9babb6f")

    def test_date_rollover_is_korean_time(self):
        self.assertEqual(updater.release_image_tag("weather", "a" * 40, "20261020T160000000000Z"),
                         "safealley-release/weather:20261021-010000-aaaaaaa")

    def test_database_is_not_retagged(self):
        with self.assertRaisesRegex(RuntimeError, "서비스"):
            updater.release_image_tag("database", "a" * 40, "20261020T054545935592Z")

    def test_invalid_commit_and_timestamp_are_rejected(self):
        for commit, stamp in [("bad", "20261020T054545935592Z"), ("a" * 40, "20261020")]:
            with self.assertRaises(RuntimeError): updater.release_image_tag("frontend", commit, stamp)


if __name__ == '__main__':
    unittest.main()
