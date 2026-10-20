"""Safety contract tests; never starts Docker or connects to a real database."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import tarfile
import unittest
import zipfile
from unittest.mock import patch

import manage
import package


class PackageTests(unittest.TestCase):
    def test_all_model_template_defaults_match_current_model(self):
        defaults = {
            ".env.example": "OLLAMA_MODEL=gemma4:26b",
            "deployment/.env.example": "OLLAMA_MODEL=gemma4:26b",
            "docker-compose.yml": "OLLAMA_MODEL: ${OLLAMA_MODEL:-gemma4:26b}",
            "deployment/compose.yml": "OLLAMA_MODEL: ${OLLAMA_MODEL:-gemma4:26b}",
            "deployment/compose.vm.override.yml": "OLLAMA_MODEL: ${OLLAMA_MODEL:-gemma4:26b}",
            "backend/app/core/config.py": 'ollama_model: str = Field(default="gemma4:26b", min_length=1)',
        }
        for name, value in defaults.items():
            with self.subTest(name=name):
                content = (package.ROOT / name).read_text(encoding="utf-8")
                self.assertIn(value, content)
                self.assertNotIn("qwen3:4b", content)
                self.assertNotIn("qwen3.6:35b", content)

    def test_osm_templates_use_non_demo_initial_scores(self):
        self.assertIn("OSM_SAFETY_SCORE_MODE=uniform", (package.ROOT / ".env.example").read_text(encoding="utf-8"))
        compose = (package.ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("OSM_SAFETY_SCORE_MODE: ${OSM_SAFETY_SCORE_MODE:-uniform}", compose)
        self.assertNotIn("OSM_SAFETY_SCORE_MODE:-demo", compose)

    def test_frontend_image_normalizes_public_asset_permissions(self):
        dockerfile = (package.ROOT / 'frontend' / 'Dockerfile').read_text(encoding='utf-8')
        copy = dockerfile.index('COPY --from=build /app/dist /usr/share/nginx/html')
        self.assertGreater(dockerfile.index('find /usr/share/nginx/html -type d -exec chmod 755 {} +'), copy)
        self.assertGreater(dockerfile.index('find /usr/share/nginx/html -type f -exec chmod 644 {} +'), copy)
        self.assertNotIn('chmod 777', dockerfile)

    def test_private_paths_excluded(self):
        for path in (".env", "deployment/.env", "backend/.env.prod", "frontend/node_modules/a.js",
                     "data_pipeline/raw/source.json", "backend/key.pem", "backend/data.dump",
                     "../backend/app.py", "output/deck.pptx", "/backend/app.py"):
            with self.subTest(path=path):
                self.assertFalse(package.allowed(path))

    def test_required_source_allowed(self):
        for path in ("backend/app/main.py", "frontend/package-lock.json", "deployment/.env.example",
                     "database/init/001_extensions.sql", "deployment/compose.yml",
                     "docker-compose.yml", "deployment/compose.vm.override.yml", ".env.example", "NOTICE.md"):
            self.assertTrue(package.allowed(path))

    def test_package_reads_pinned_git_content_not_dirty_files(self):
        commit = "a" * 40
        names = ["backend/Dockerfile", "frontend/Dockerfile", "data_pipeline/Dockerfile",
                 "database/init/001_extensions.sql", ".env.example", "NOTICE.md",
                 "frontend/src/components/ExamplePicker.tsx", *package.DEPLOY_FILES, ".env"]

        def git(*args):
            if args[0] == "rev-parse": return commit.encode()
            if args[0] == "ls-tree": return "\0".join(names).encode()
            if args[0] == "status": return b" M frontend/src/components/ExamplePicker.tsx\n"
            if args[0] == "show": return b"committed source bytes\n"
            self.fail(f"Unexpected git call: {args}")

        for suffix in (".zip", ".tar.gz"):
          with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as folder, patch.object(package, "git", side_effect=git):
            output = Path(folder) / ("deploy" + suffix)
            package.build_package(output, "main")
            opener = tarfile.open if suffix == ".tar.gz" else zipfile.ZipFile
            with opener(output) as archive:
                read = (lambda name: archive.extractfile(name).read()) if suffix == ".tar.gz" else archive.read
                archive_names = archive.getnames() if suffix == ".tar.gz" else archive.namelist()
                self.assertNotIn("SafeAlley/.env", archive_names)
                self.assertEqual(read("SafeAlley/frontend/src/components/ExamplePicker.tsx"), b"committed source bytes\n")
                manifest = json.loads(read("SafeAlley/release.json"))
                self.assertEqual(manifest["base_commit"], commit)
                self.assertFalse(manifest["working_tree_changes"])
                self.assertTrue(manifest["local_working_tree_changes_present"])
                self.assertEqual(manifest["source_mode"], "git-commit")
            self.assertEqual(output.with_suffix(output.suffix + ".sha256").read_text().strip(), hashlib.sha256(output.read_bytes()).hexdigest())

    def test_package_refuses_missing_committed_deployment_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(package, "git", side_effect=[b"a" * 40, b"frontend/Dockerfile"]):
            output = Path(folder) / "deploy.zip"
            with self.assertRaisesRegex(ValueError, "Missing required committed file"):
                package.build_package(output)
            self.assertFalse(output.exists())

    def test_secret_detection_reports_filename_only(self):
        with self.assertRaises(ValueError) as context:
            package.check_content("test.txt", b"-----BEGIN " + b"PRIVATE KEY-----")
        self.assertNotIn("BEGIN", str(context.exception))
        self.assertIn("test.txt", str(context.exception))


class OperationTests(unittest.TestCase):
    def test_heatmap_is_an_explicit_one_shot_operation(self):
        with patch("sys.argv", ["manage.py", "heatmap"]), patch.object(manage, "validate", return_value={}), patch.object(manage, "run") as run:
            manage.main()
        self.assertEqual(run.call_args.args[0], manage.compose("run", "--rm", "--no-deps", "heatmap"))

    def test_verify_checks_heatmap_manifest(self):
        config = {"services": {"frontend": {"ports": [{"published": "8080", "host_ip": "127.0.0.1"}]}}}
        with patch.object(manage, "run"), patch.object(manage.urllib.request, "urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            manage.verify(config)
        self.assertIn("http://127.0.0.1:8080/api/streetlight-heatmap/manifest", [call.args[0] for call in urlopen.call_args_list])

    def test_separate_project(self):
        self.assertIn("safealley-deploy", manage.compose("status"))
        self.assertNotIn("safealley-deploy", manage.compose("status", source=True))

    def test_refuse_overwriting_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "db.dump"
            target.write_bytes(b"existing")
            with patch.object(manage, "run") as run, self.assertRaises(ValueError):
                manage.backup(target)
            run.assert_not_called()
            self.assertEqual(target.read_bytes(), b"existing")

    def test_restore_requires_confirmation(self):
        with patch.object(manage, "run") as run, self.assertRaises(ValueError):
            manage.restore(Path("absent"), None)
        run.assert_not_called()

    def test_refuse_nonempty_database(self):
        with patch.object(manage, "run", return_value=subprocess.CompletedProcess([], 0, stdout="12\n")), self.assertRaises(ValueError):
            manage.assert_empty_database()

    def test_restore_checksums_and_live_services(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "db.dump"
            target.write_bytes(b"PGDMP-test")
            with patch.object(manage, "run") as run, self.assertRaises(ValueError):
                manage.restore(target, "safealley-deploy")
            run.assert_not_called()
            target.with_suffix(".dump.sha256").write_text(hashlib.sha256(target.read_bytes()).hexdigest())
            with patch.object(manage, "run", return_value=subprocess.CompletedProcess([], 0, stdout="database\nbackend\n")) as run, self.assertRaises(ValueError):
                manage.restore(target, "safealley-deploy")
            self.assertEqual(run.call_count, 1)

    def test_restore_is_atomic_and_has_no_clean(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "db.dump"
            target.write_bytes(b"PGDMP-test")
            target.with_suffix(".dump.sha256").write_text(hashlib.sha256(target.read_bytes()).hexdigest())
            with patch.object(manage, "run", side_effect=[
                subprocess.CompletedProcess([], 0, stdout="database\n"),
                subprocess.CompletedProcess([], 0, stdout="0\n"),
                subprocess.CompletedProcess([], 0),
            ]) as run:
                manage.restore(target, "safealley-deploy")
            command = run.call_args_list[-1].args[0]
            self.assertIn("--single-transaction", command)
            self.assertNotIn("--clean", command)

    def test_validation_rejects_weak_password(self):
        config = {"services": {"database": {"environment": {"POSTGRES_PASSWORD": "short"}}}}
        with patch.object(Path, "is_file", return_value=True), patch.object(manage, "run", return_value=subprocess.CompletedProcess([], 0, stdout=json.dumps(config))), self.assertRaises(ValueError):
            manage.validate()


if __name__ == "__main__":
    unittest.main()
