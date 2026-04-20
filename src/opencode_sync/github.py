"""GitHub repo creation via gh CLI, with manual fallback."""

import json
import shutil
import subprocess
from typing import Optional


def gh_available() -> bool:
    return shutil.which("gh") is not None


def gh_authenticated() -> bool:
    if not gh_available():
        return False
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
    )
    return result.returncode == 0


def gh_username() -> Optional[str]:
    result = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def create_private_repo(name: str = "opencode-config") -> tuple[Optional[str], Optional[str]]:
    """Create a private GitHub repo and return its SSH URL and error message."""
    result = subprocess.run(
        ["gh", "repo", "create", name, "--private"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None, result.stderr.strip()
    username = gh_username()
    if username:
        return f"git@github.com:{username}/{name}.git", None
    # Parse URL from output as fallback
    url = result.stdout.strip()
    if url.startswith("https://github.com/"):
        parts = url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) == 2:
            return f"git@github.com:{parts[0]}/{parts[1]}.git", None
    return None, "Could not determine repo URL"


def manual_instructions() -> str:
    return (
        "\nGitHub CLI (gh) not found or not authenticated.\n"
        "To auto-create a private repo, install and authenticate gh:\n"
        "  brew install gh && gh auth login\n"
        "Then run: ocs init\n\n"
        "Or create the repo manually:\n"
        "  1. Go to https://github.com/new\n"
        "  2. Name it 'opencode-config', set to Private\n"
        "  3. Do NOT initialize with README\n"
        "  4. Copy the SSH URL (git@github.com:user/opencode-config.git)\n"
        "  5. Run: ocs init --repo <SSH_URL>\n"
    )
