import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools import verify_repo_and_db


def _run_git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


class VerifyRepoAndDatabaseTests(unittest.TestCase):
    def test_required_branches_accept_remote_tracking_refs(self):
        required_branches = ["main", "pre-trevor", "trevor/integration"]
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _run_git(root, "init", "--initial-branch=main")
            _run_git(root, "config", "user.email", "test@example.invalid")
            _run_git(root, "config", "user.name", "Trevor Tests")
            (root / ".gitignore").write_text(
                "\n".join(verify_repo_and_db.REQUIRED_GITIGNORE_PATTERNS) + "\n",
                encoding="utf-8",
            )
            _run_git(root, "add", ".gitignore")
            _run_git(root, "commit", "-m", "fixture")
            for branch in required_branches[1:]:
                _run_git(
                    root,
                    "update-ref",
                    f"refs/remotes/origin/{branch}",
                    "HEAD",
                )

            with patch.object(
                verify_repo_and_db,
                "REQUIRED_BRANCHES",
                required_branches,
            ):
                checks = verify_repo_and_db.check_local_repo(root)

        branch_check = next(
            item for item in checks if item.key == "local.required_branches"
        )
        self.assertTrue(branch_check.ok, branch_check.detail)

    def test_github_admin_checks_can_be_skipped_for_ci_token(self):
        repo_response = Mock(status_code=200)
        repo_response.json.return_value = {"private": True}
        collaborator_response = Mock(status_code=200)
        collaborator_response.json.return_value = [{"login": "owner"}]

        with patch.object(
            verify_repo_and_db,
            "github_get",
            side_effect=[repo_response, collaborator_response],
        ) as github_get:
            checks = verify_repo_and_db.check_github_repo(
                "owner/repository",
                "test-token",
                1,
                include_admin_checks=False,
            )

        self.assertEqual(2, github_get.call_count)
        self.assertNotIn(
            "github.actions_policy_restricted",
            {item.key for item in checks},
        )

    def test_public_repository_can_be_explicitly_allowed(self):
        repo_response = Mock(status_code=200)
        repo_response.json.return_value = {"private": False}
        collaborator_response = Mock(status_code=200)
        collaborator_response.json.return_value = [{"login": "owner"}]

        with patch.object(
            verify_repo_and_db,
            "github_get",
            side_effect=[repo_response, collaborator_response],
        ):
            checks = verify_repo_and_db.check_github_repo(
                "owner/repository",
                "test-token",
                1,
                include_admin_checks=False,
                require_private=False,
            )

        visibility_check = next(
            item for item in checks if item.key == "github.repo_private"
        )
        self.assertTrue(visibility_check.ok, visibility_check.detail)
        self.assertEqual(
            "public repository explicitly allowed",
            visibility_check.detail,
        )


if __name__ == "__main__":
    unittest.main()
