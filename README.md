# huge-skills

Public, self-contained agent skills. Clone this repository and symlink skills
into the directory your agent reads. The installer needs Bash and standard
macOS/Linux utilities; each skill documents its own runtime dependencies.

## Install

```bash
git clone https://github.com/hugegene/huge-skills.git
cd huge-skills
./install.sh
```

By default this links every `skills/*/SKILL.md` folder into
`$HOME/.agents/skills`. Codex supports user skills there and project skills
in `.agents/skills`, including symlinked folders
([official documentation](https://learn.chatgpt.com/docs/build-skills)).

```bash
# Preview or select one skill.
./install.sh --dry-run
./install.sh --skill github-doc

# Install into a specific project's skill directory.
./install.sh --target /absolute/path/to/project/.agents/skills

# Other agents or installations can use an explicit destination.
./install.sh --target "$HOME/.claude/skills"
./install.sh --target "${CODEX_HOME:-$HOME/.codex}/skills"
```

Use the directory supported by your agent/version. Avoid installing the same
skill into several directories scanned by the same agent. Restart the agent
if it does not pick up a newly installed skill.

The installer works from any current directory and supports paths containing
spaces. It creates one absolute symlink per skill and makes no changes to
existing files, directories, or links belonging to another checkout. An
installation conflict fails before any selected skills are linked. Rerunning
is safe and does not prompt. Dependency installation and credentials are separate.

Keep the checkout in place while using the skills. To update, run `git pull
--ff-only` in the checkout and rerun the installer to discover newly added
skills. To move the checkout, uninstall its links first and reinstall from
the new location.

```bash
./install.sh --uninstall --dry-run
./install.sh --uninstall
# Use the same --target if you installed elsewhere.
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
into a path that remains available throughout the task. A generic setup script:

```bash
set -eu
skills_checkout="$HOME/huge-skills"
git clone https://github.com/hugegene/huge-skills.git "$skills_checkout"
# For reproducible tasks, check out a reviewed commit before installing:
# git -C "$skills_checkout" checkout --detach FULL_COMMIT_SHA
bash "$skills_checkout/install.sh"
python3 -m venv "$skills_checkout/.venv"
"$skills_checkout/.venv/bin/python" -m pip install \
  -r "$skills_checkout/skills/github-doc/requirements.txt"
export PATH="$skills_checkout/.venv/bin:$PATH"
```

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
