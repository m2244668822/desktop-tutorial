import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def requirement_lines(name: str) -> set[str]:
    return {
        line.strip()
        for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


class DependencySecurityContractTests(unittest.TestCase):
    def test_core_runtimes_use_patched_security_dependencies(self):
        for manifest in ("requirements.txt", "requirements-agent-stack.txt"):
            requirements = requirement_lines(manifest)
            with self.subTest(manifest=manifest):
                self.assertIn("python-dotenv==1.2.3", requirements)
                self.assertIn("cryptography==50.0.0", requirements)

    def test_ci_lock_sources_use_patched_versions(self):
        requirements = requirement_lines("requirements-ci.txt")

        self.assertIn("requests==2.34.2", requirements)
        self.assertIn("cryptography==50.0.0", requirements)

    def test_cloud_first_runtime_excludes_retired_local_model_stack(self):
        blocked_packages = (
            "airllm",
            "chromadb",
            "torch",
            "transformers",
            "sentence-transformers",
        )
        for manifest in ("requirements.txt", "requirements-agent-stack.txt"):
            requirements = requirement_lines(manifest)
            with self.subTest(manifest=manifest):
                for package in blocked_packages:
                    self.assertFalse(
                        any(
                            requirement == package
                            or requirement.startswith(f"{package}==")
                            or requirement.startswith(f"{package}>=")
                            for requirement in requirements
                        ),
                        f"{package} must remain outside the Trevor cloud-first runtime",
                    )

        self.assertFalse((ROOT / "requirements-airllm.txt").exists())

    def test_chatgpt_server_loads_transformers_only_inside_optional_backend(self):
        source = (ROOT / 'chatgpt_server.py').read_text(encoding='utf-8')

        self.assertNotIn('from transformers import pipeline\n', source)
        self.assertIn("import_module('transformers')", source)

    def test_container_uses_the_supported_trevor_web_entrypoint(self):
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')

        self.assertIn('EXPOSE 5001', dockerfile)
        self.assertIn('"system_main.py", "web"', dockerfile)
        self.assertNotIn('gunicorn', dockerfile)
        self.assertNotIn('desktop_chat_app:app', dockerfile)

    def test_github_actions_use_node24_runtimes(self):
        workflow_sources = []
        for workflow in (ROOT / '.github' / 'workflows').glob('*.yml'):
            source = workflow.read_text(encoding='utf-8')
            workflow_sources.append(source)
            with self.subTest(workflow=workflow.name):
                self.assertNotIn('actions/checkout@v4', source)
                self.assertNotIn('actions/setup-python@v5', source)
                self.assertIn('actions/checkout@v7', source)
                self.assertIn('actions/setup-python@v7', source)
        combined = '\n'.join(workflow_sources)
        self.assertNotIn('actions/upload-artifact@v4', combined)
        self.assertIn('actions/upload-artifact@v7', combined)


if __name__ == "__main__":
    unittest.main()
