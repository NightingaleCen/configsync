# OpenCode Config Sync - Agent Instructions

## What This Is

CLI tool to sync OpenCode config files (`~/.config/opencode/`, `~/.agents/skills/`) across machines via private GitHub repo. Python 3.8+, distributed via `uvx`, SSH-only auth.

## Critical Constraints

- **Distribution**: `uvx` only — no long-running processes, no pip install workflows
- **Auth**: SSH keys only (user has them configured)
- **Conflicts**: Interactive resolution — never auto-merge, always prompt user
- **UI**: English only, use Rich for all output

## Architecture

OpenCode config files ↔ Local git repo (`~/.config/opencode-sync/repo/`) ↔ GitHub private repo (SSH)

## Project Structure

```
src/opencode_sync/
├── cli.py              # Click commands, routes to core
├── core.py             # Main orchestration (cmd_init, cmd_push, cmd_pull, etc.)
├── git_ops.py          # GitPython wrapper
├── conflict.py         # Interactive conflict resolution UI
├── config.py           # Tool config at ~/.config/opencode-sync/config.json
├── github.py           # gh CLI detection and repo creation
└── utils.py            # Path helpers, file copying
```

Entry points in `pyproject.toml`: both `opencode-sync` and `ocs` → `opencode_sync.cli:main`

## Tech Stack & Dependencies

**Core Dependencies** (declared in `pyproject.toml`):
- `gitpython>=3.1.0` - Git operations
- `click>=8.0.0` - CLI framework (modern, better than argparse)
- `rich>=13.0.0` - Beautiful terminal output (tables, colors, prompts)

**Why these choices**:
- GitPython: Most mature Python Git library, handles SSH automatically
- Click: Cleaner syntax than argparse, better help generation
- Rich: Makes CLI output professional and readable

**Standard library usage**:
- `pathlib` - Path manipulation
- `json` - Config file handling
- `subprocess` - For `gh` CLI detection
- `shutil` - File operations

## Synced Files (Default)

```
~/.config/opencode/opencode.json       # Main OpenCode config
~/.agents/skills/                      # Custom skills directory
~/.agents/.skill-lock.json            # Skills lock file
```

**Important**: Tool config stored separately at `~/.config/opencode-sync/config.json` to avoid circular sync.

## Commands Reference

```bash
# Initialize sync (first time setup)
ocs init

# Initialize with existing repo
ocs init --repo git@github.com:user/opencode-config.git

# Push local config to remote (auto-pulls first)
ocs push

# Pull remote config to local
ocs pull

# Show sync status
ocs status

# Show diff between local and remote
ocs diff
```

## GitHub Integration

### Auto-Creation (Preferred)

If `gh` CLI is installed and authenticated:
```bash
gh repo create opencode-config --private --source=. --push
```

### Manual Creation (Fallback)

If `gh` not available, show user:
```
GitHub CLI not found. Please choose:

[1] Install GitHub CLI (Recommended)
    macOS:  brew install gh
    Linux:  See https://cli.github.com/
    Then:   gh auth login
    Finally: Run 'ocs init' again

[2] Create repository manually
    1. Go to https://github.com/new
    2. Repository name: opencode-config
    3. Visibility: Private ✓
    4. Do NOT initialize with README
    5. Click "Create repository"
    6. Copy the SSH URL (git@github.com:...)
    7. Run: ocs init --repo <SSH_URL>

[3] Cancel
```

## Git Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/).

Format: `<type>[optional scope]: <description>`

Types:
- `feat`: New feature (triggers minor version bump)
- `fix`: Bug fix (triggers patch version bump)
- `docs`: Documentation only
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `test`: Adding or updating tests
- `chore`: Maintenance (deps, tooling, config)

Breaking changes: append `!` after type, e.g. `feat!: drop Python 3.8 support`

Examples:
```
feat: add interactive conflict resolution
fix(git_ops): handle detached HEAD state on pull
docs: update shell alias instructions in AGENTS.md
chore: bump gitpython to 3.1.46
```

## GitHub Integration

### Auto-Creation (Preferred)

If `gh` CLI is installed and authenticated:
```bash
gh repo create opencode-config --private --source=. --push
```

### Manual Creation (Fallback)

If `gh` not available, show user:
```
GitHub CLI not found. Please choose:

[1] Install GitHub CLI (Recommended)
    macOS:  brew install gh
    Linux:  See https://cli.github.com/
    Then:   gh auth login
    Finally: Run 'ocs init' again

[2] Create repository manually
    1. Go to https://github.com/new
    2. Repository name: opencode-config
    3. Visibility: Private ✓
    4. Do NOT initialize with README
    5. Click "Create repository"
    6. Copy the SSH URL (git@github.com:...)
    7. Run: ocs init --repo <SSH_URL>

[3] Cancel
```

## Conflict Resolution

### Detection

Conflicts occur when:
- Local and remote both modified since last sync
- Git merge fails (different changes to same file)

### Resolution Flow

```python
# Pseudo-code for conflict handling
if detect_conflict():
    show_conflict_info()  # timestamps, file names
    choice = prompt_user([
        "1. Keep local (push and overwrite remote)",
        "2. Use remote (discard local changes)", 
        "3. Show diff",
        "4. Backup local and use remote",
        "5. Cancel"
    ])
    
    if choice == 1:
        git_push_force()
    elif choice == 2:
        git_reset_hard_origin()
    elif choice == 3:
        show_diff()
        # Loop back to prompt
    elif choice == 4:
        backup_local()  # to ~/.config/opencode/backups/
        git_reset_hard_origin()
    else:
        abort()
```

### Backup Strategy

When overwriting local config:
- Create backup at `~/.config/opencode/backups/opencode.json.TIMESTAMP`
- Keep last 10 backups (configurable)
- Show backup location to user

## Configuration Management

### Tool Config Location

`~/.config/opencode-sync/config.json`

### Config Schema

```json
{
  "version": "1.0",
  "repo_url": "git@github.com:username/opencode-config.git",
  "sync_paths": [
    "~/.config/opencode/opencode.json",
    "~/.agents/skills/",
    "~/.agents/.skill-lock.json"
  ],
  "backup": {
    "enabled": true,
    "max_backups": 10,
    "location": "~/.config/opencode/backups/"
  },
  "git": {
    "user_name": "Auto-detected from git config",
    "user_email": "Auto-detected from git config"
  }
}
```

### Config Initialization

On first run:
1. Create `~/.config/opencode-sync/` directory
2. Auto-detect git user.name and user.email
3. Use default sync_paths
4. Save config

## Git Operations Details

### Repository Location

Local git repo: `~/.config/opencode-sync/repo/`

This is separate from OpenCode config to:
- Avoid polluting OpenCode config directory with `.git/`
- Allow clean file copying
- Simplify git operations

### Sync Process

**Push**:
```python
1. Copy files from OpenCode locations to repo/
2. git add .
3. git commit -m "Update config from {hostname} at {timestamp}"
4. git fetch origin
5. Check if remote has new commits
   - YES: Attempt merge, handle conflicts if any
   - NO: Proceed
6. git push origin main
```

**Pull**:
```python
1. git fetch origin
2. Check if local has uncommitted changes
   - YES: Stash or warn user
   - NO: Proceed
3. git pull origin main
4. Copy files from repo/ to OpenCode locations
5. Show what changed
```

### SSH Key Detection

Tool assumes SSH keys are already configured. If push/pull fails with auth error:
```
SSH authentication failed.

Please ensure:
1. You have an SSH key: ls ~/.ssh/id_*.pub
2. Your public key is added to GitHub:
   - Go to https://github.com/settings/keys
   - Click "New SSH key"
   - Paste contents of: cat ~/.ssh/id_ed25519.pub
3. Test connection: ssh -T git@github.com

For help: https://docs.github.com/en/authentication/connecting-to-github-with-ssh
```

## Common Pitfalls for Agents

### Path Handling

❌ **Wrong**: `os.path.join("~/.config", "opencode")`
✅ **Right**: `Path("~/.config/opencode").expanduser()`

Always use `pathlib.Path` and call `.expanduser()` for `~/` paths.

### Git Operations

❌ **Wrong**: `subprocess.run(["git", "push"])`
✅ **Right**: `repo.remote("origin").push()`

Use GitPython's API, not subprocess. It handles SSH keys automatically.

### Config File Paths

❌ **Wrong**: Hardcode `/Users/username/.config/`
✅ **Right**: Use `Path.home() / ".config"`

Never hardcode home directory paths.

### Error Messages

❌ **Wrong**: `print("Error: something failed")`
✅ **Right**: Use Rich console with proper formatting and actionable instructions

Always provide context and next steps in error messages.

### Testing Git Operations

❌ **Wrong**: Test against real GitHub repo
✅ **Right**: Mock GitPython objects or use temporary local repos

Never hit external services in tests.

## Development Guidelines

### Code Style

- Follow PEP 8
- Use type hints for all functions
- Docstrings for all public functions (Google style)
- Max line length: 100 characters

### Testing

- Use `pytest` for testing
- Mock git operations in tests (don't hit real GitHub)
- Test conflict resolution logic thoroughly
- Test path expansion (~/ handling)

---

**Last Updated**: 2026-04-20
**Project Status**: Phase 1 (MVP) - Implemented
