---
name: github-doc
description: Publish a Markdown note or document to a specified GitHub repository and link it from the README using the Contents API. Use for document publishing without a local clone of the destination repository; previews changes unless --push is passed.
---

# Push a doc to GitHub + link it in README

Adds a Markdown file to a repo and inserts a link to it in the README. Adapted
from Lily's `github-doc` skill and `github/push_doc.py` CLI. The destination
repository must be supplied with `--repo owner/repo`.

**Preview first and inspect the document and README diffs. Use `--push` only
when the user has authorized publishing these changes.** An existing explicit
instruction to publish is sufficient; do not ask again for the same action.
Installation or a request to draft/preview does not authorize publishing.

## Prerequisites

- Python 3.10+ and the dependencies in [requirements.txt](requirements.txt).
- `MCP_GIT_PAT`, `GH_TOKEN`, or `GITHUB_TOKEN` (in that precedence order).
  For a fine-grained PAT, repository access must include the target repo with
  **Contents: Read and write** for publishing. Preview makes read-only GitHub
  requests and still requires a token. Branch protection rules still apply.
- Optional `MCP_GIT_AUTHOR_NAME` and `MCP_GIT_AUTHOR_EMAIL`, set together;
  otherwise GitHub uses the authenticated user's identity.

Use the Python environment in which the dependencies are installed. Inject
credentials as environment variables; the script does not load `.env` files.
For a custom trusted CA, set `REQUESTS_CA_BUNDLE` to its PEM file.

## Usage

Resolve `SKILL_DIR` to the directory containing this `SKILL.md` (including when
accessed through a symlink). The script can run from any working directory;
the local file argument is relative to that working directory.

```bash
# Preview; destination branch is auto-resolved and README link goes at EOF.
python "$SKILL_DIR/scripts/push_doc.py" path/to/local-note.md --repo OWNER/REPO

# Choose the target path and README section.
python "$SKILL_DIR/scripts/push_doc.py" local-note.md \
  --repo OWNER/REPO --path notes/example.md \
  --readme-section "## Notes" --link-text "My note"

# Publish the authorized changes using the same arguments.
python "$SKILL_DIR/scripts/push_doc.py" local-note.md \
  --repo OWNER/REPO --path notes/example.md \
  --readme-section "## Notes" --link-text "My note" --push
```

Behavior and defaults:
- `--branch` defaults to the repo's default branch. The CLI checks repo access
  first; a 404 may mean a missing repo or insufficient token access.
- `--path` defaults to the local file's basename.
- `--link-text` defaults to the first `# H1`, then the filename stem.
- `--readme-path` defaults to `README.md`. Links are relative to that README,
  with special path characters URL-encoded.
- `--readme-section` appends within that heading's section, or creates the
  section at EOF if missing. Without it, append the link at EOF.
- An existing inline link to the same generated target is left alone; it is
  not relabeled or moved. Unchanged documents are not recommitted.
- `--no-readme` skips README handling. `--message` sets the document commit message.

## Publishing and recovery

The Contents API writes one file per commit: normally the document, then the
README. This is **not atomic**; zero, one, or two commits may be needed. The
CLI prints completed commit URLs and reports partial success if a later write
fails. It sends the file SHA read during that run when updating, so a concurrent
change causes a conflict instead of being silently overwritten.

On a conflict, timeout, or partial failure, inspect the branch and preview
again. A timeout can occur after a commit has reached GitHub. Do not blindly
retry writes or bypass branch rules. Re-running skips an unchanged document
and can finish a missing README link. If atomic multi-file publishing is
required, this helper does not provide it.
