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
from unittest.mock import patch

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
            with patch.object(vm, "verify"), patch.object(vm, "live"), patch.object(vm, "backup") as backup:
                vm.update(p)
            backup.assert_not_called()

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
                 patch.object(vm, "prune"), patch.object(updater, "run") as command:
                vm.update(p)
            state = updater.load(vm.state)
            self.assertEqual(state['commit'], manifest['base_commit'])
            self.assertEqual(state['previous']['commit'], 'b' * 40)
            self.assertEqual(updater.load(vm.config)['services']['database'], model['services']['database'])
            self.assertEqual(recreate.call_args.args[0], ['frontend'])
            build_command = next(c.args[0] for c in command.call_args_list if c.args[0][:2] == ['docker', 'build'])
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

    @unittest.skipUnless(os.name == 'posix', 'Linux flock test runs on the VM')
    def test_concurrent_update_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vm, _, _ = self.setup_vm(root)
            with vm.lock():
                with self.assertRaisesRegex(RuntimeError, 'Another deployment'):
                    with vm.lock(): pass


if __name__ == '__main__':
    unittest.main()
