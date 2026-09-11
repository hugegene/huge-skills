# huge-skills

Public, self-contained skills for Codex and Claude Code. Clone this repository
and link the same skill folders into either or both agents. The installer needs
Bash and standard macOS/Linux utilities; each skill documents its own runtime dependencies.

## Install

```bash
git clone https://github.com/hugegene/huge-skills.git
cd huge-skills
./install.sh --agent both
```

Choose the agent you use. With no arguments, the installer keeps its original
behavior: install all skills for Codex in `$HOME/.agents/skills`.

| Agent option | User directory | With `--project DIR` | Invoke the first skill |
| --- | --- | --- | --- |
| `--agent codex` | `~/.agents/skills` | `DIR/.agents/skills` | `$github-doc` |
| `--agent claude` | `~/.claude/skills` | `DIR/.claude/skills` | `/github-doc` |
| `--agent both` | Both directories above | Both directories above | Either agent |

Both agents support symlinked skill folders
([Codex documentation](https://learn.chatgpt.com/docs/build-skills),
[Claude Code documentation](https://code.claude.com/docs/en/skills)). Each link
points to the same `skills/<name>` folder: one prompt and one set of helpers
serve both agents.

```bash
# Install for one agent.
./install.sh --agent codex
./install.sh --agent claude

# Preview or select one skill for both agents.
./install.sh --agent both --dry-run
./install.sh --agent both --skill github-doc

# Install into an existing project (absolute or relative path).
./install.sh --agent both --project /absolute/path/to/project

# Custom destinations, including older Codex setups.
./install.sh --target "${CODEX_HOME:-$HOME/.codex}/skills"
```

`--target` takes the exact skill directory and cannot be combined with
`--agent` or `--project`. `--project` defaults to Codex if `--agent` is omitted;
it requires an existing directory to avoid creating a project at a mistyped path.
Project links contain absolute local paths: rerun setup in each clone or cloud
environment instead of committing those links for other machines.

Use the directory supported by your agent/version. Avoid installing the same
skill into several directories scanned by the same agent. Restart the agent
if it does not pick up a newly installed skill.

The installer works from any current directory and supports paths containing
spaces. It creates one absolute symlink per skill and makes no changes to
existing files, directories, or links belonging to another checkout. An
installation conflict in either agent's destination fails before any selected
skills are linked. Rerunning is safe and does not prompt. Dependency installation
and credentials are separate.

Keep the checkout in place while using the skills. To update, run `git pull
--ff-only` in the checkout and rerun the installer to discover newly added
skills. To move the checkout, uninstall its links first and reinstall from
the new location.

```bash
./install.sh --agent both --uninstall --dry-run
./install.sh --agent both --uninstall
# Remove just Claude Code's links, leaving Codex installed.
./install.sh --agent claude --skill github-doc --uninstall
# Include the same --project or --target if you installed elsewhere.
```

Uninstall removes only links pointing to this checkout, including links for
skills removed by an update. It preserves the checkout and unrelated skills.

## Skills

| Skill | Purpose | Runtime |
| --- | --- | --- |
| [github-doc](skills/github-doc/SKILL.md) | Preview and publish Markdown to GitHub, with a README link | Python 3.10+, requests |

The first skill adapts the prompt from Lily's `.claude/skills/github-doc/SKILL.md`
and the implementation from `github/api.py` and `github/push_doc.py`. It has no
dependency on a Lily checkout or personal repository defaults.

Install its Python dependencies in an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r skills/github-doc/requirements.txt
.venv/bin/python skills/github-doc/scripts/push_doc.py --help
```

When invoking the skill, tell the agent the absolute path to this environment's
Python, or activate the environment before starting the agent. Export a token
as `MCP_GIT_PAT`, `GH_TOKEN`, or `GITHUB_TOKEN` using your secret manager or shell.
The script does not automatically load `.env` or read GitHub CLI credentials.

After setup, start your client and invoke the skill with a preview request:

```text
Codex:       $github-doc Preview publishing /path/to/note.md to OWNER/REPO.
Claude Code: /github-doc Preview publishing /path/to/note.md to OWNER/REPO.
```

Both clients can also select it automatically for a matching document-publishing
request. For a discovery check that needs no GitHub token, ask the skill to
explain its prerequisites without running commands or publishing anything.

```bash
# Preview only; requires a token for GitHub reads.
.venv/bin/python skills/github-doc/scripts/push_doc.py /path/to/note.md \
  --repo OWNER/REPO --path notes/note.md --readme-section "## Notes"
# Add --push to publish authorized changes.
```

The helper uses GitHub's [Contents API](https://docs.github.com/en/rest/repos/contents).
Document and README updates are separate commits. If the second fails, inspect
the first commit and rerun a preview; unchanged files are skipped.

## Cloud task setup

Run setup before starting the agent, as the same user that will run it. Clone
into a path that remains available throughout the task. This example installs
for both agents; use `--agent codex` or `--agent claude` for a single-client task:

```bash
set -eu
skills_checkout="$HOME/huge-skills"
git clone https://github.com/hugegene/huge-skills.git "$skills_checkout"
# For reproducible tasks, check out a reviewed commit before installing:
# git -C "$skills_checkout" checkout --detach FULL_COMMIT_SHA
bash "$skills_checkout/install.sh" --agent both
python3 -m venv "$skills_checkout/.venv"
"$skills_checkout/.venv/bin/python" -m pip install \
  -r "$skills_checkout/skills/github-doc/requirements.txt"
export PATH="$skills_checkout/.venv/bin:$PATH"
```

For a project-scoped cloud task, use `--agent both --project /workspace/project`
instead, replacing the path with the existing task checkout. Skills installed
on your laptop do not automatically transfer into hosted sessions. Run this
setup inside the execution environment before client startup; hosted products
that do not expose filesystem setup need their own skill distribution mechanism.

Supply the GitHub token through the cloud runner's secret environment for the
task execution phase. The public clone and symlink installation require no
GitHub credentials. Setup needs network access to GitHub and the Python package
index; publishing needs access to `api.github.com`. If setup and task execution
use different containers, preserve the checkout, skill links, and Python
environment at the same paths, or recreate them in the task container. If PATH
changes do not persist between phases, configure the absolute Python path.

## Add a skill and validate

Create `skills/<lowercase-hyphenated-name>/SKILL.md` with YAML `name` and
`description` fields. Keep the prompt focused on its workflow. Put executable
helpers in `scripts/` and declare dependencies within that skill. References
and scripts must work from the cloned skill folder without personal paths or
external local projects. Never commit tokens, `.env` files, or virtual environments.

```bash
python3 -m pip install -r skills/github-doc/requirements.txt
python3 -m unittest discover -s tests -v
bash -n install.sh
```

CI runs the tests on Linux and macOS. Tests use temporary directories and
mocked GitHub responses; they do not publish documents or change installed skills.

Licensed under [MIT](LICENSE).
