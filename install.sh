#!/usr/bin/env bash
# Link self-contained skills from this checkout. Compatible with Bash 3.2+.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [--agent codex|claude|both] [--project DIR] [--skill NAME]
                    [--dry-run] [--uninstall]
       ./install.sh --target DIR [--skill NAME] [--dry-run] [--uninstall]

Default: install all skills into $HOME/.agents/skills.
  --agent NAME   Install for codex (default), claude, or both.
  --project DIR  Install in an existing project's .agents/skills and/or
                 .claude/skills instead of your home directory.
  --skill NAME   Select one skill (may be repeated).
  --target DIR   Custom skill directory; cannot combine with --agent/--project.
  --dry-run      Show actions without changing the filesystem.
  --uninstall    Remove only links owned by this checkout.
  -h, --help     Show this help.

Keep the checkout in place while its skills are installed. Existing files,
directories, and links to other checkouts are never replaced.
EOF
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
agent=codex
agent_explicit=false
project=""
custom_target=""
dry_run=false
uninstall=false
selected=()
while (($#)); do
  case "$1" in
    --skill|--target|--agent|--project)
      (($# >= 2)) && [[ -n "$2" && "$2" != --* ]] || fail "$1 requires a value"
      case "$1" in
        --skill) selected+=("$2") ;;
        --target) custom_target="$2" ;;
        --agent) agent="$2"; agent_explicit=true ;;
        --project) project="$2" ;;
      esac
      shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --uninstall) uninstall=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done
case "$agent" in codex|claude|both) ;; *) fail "unknown agent: $agent (use codex, claude, or both)" ;; esac
targets=()
if [[ -n "$custom_target" ]]; then
  if $agent_explicit || [[ -n "$project" ]]; then
    fail '--target cannot be combined with --agent or --project'
  fi
  [[ "$custom_target" == /* ]] || custom_target="$PWD/$custom_target"
  while [[ "$custom_target" == */ ]]; do custom_target="${custom_target%/}"; done
  [[ -n "$custom_target" ]] || fail 'refusing to use / as the skill directory'
  targets=("$custom_target")
else
  if [[ -n "$project" ]]; then
    [[ -d "$project" ]] || fail "project directory does not exist: $project"
    scope_dir="$(cd -- "$project" && pwd -P)"
  else
    scope_dir="${HOME:?HOME must be set}"
  fi
  if [[ "$agent" == codex || "$agent" == both ]]; then targets+=("$scope_dir/.agents/skills"); fi
  if [[ "$agent" == claude || "$agent" == both ]]; then targets+=("$scope_dir/.claude/skills"); fi
fi
for name in "${selected[@]+${selected[@]}}"; do
  [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || fail "invalid skill name: $name"
done

names=()
add_name() {
  local existing
  for existing in "${names[@]+${names[@]}}"; do
    [[ "$existing" != "$1" ]] || return 0
  done
  names+=("$1")
}
if ((${#selected[@]})); then
  for name in "${selected[@]}"; do add_name "$name"; done
elif $uninstall; then
  # Include stale links for skills removed by a subsequent git pull.
  for target in "${targets[@]}"; do
    for dest in "$target"/*; do
      [[ -L "$dest" ]] || continue
      name="${dest##*/}"
      if [[ "$(readlink "$dest")" == "$repo_dir/skills/$name" ]]; then add_name "$name"; fi
    done
  done
else
  for source in "$repo_dir"/skills/*; do
    [[ -d "$source" && -f "$source/SKILL.md" ]] || continue
    names+=("${source##*/}")
  done
fi

# Preflight every agent's selection before creating directories or links.
for target in "${targets[@]}"; do
  # Detect an obstructed parent even when the skill itself does not exist yet.
  if ! $uninstall; then
    ancestor="$target"
    while [[ "$ancestor" != / && ! -d "$ancestor" ]]; do
      [[ ! -e "$ancestor" && ! -L "$ancestor" ]] || fail "destination parent is not a directory: $ancestor"
      ancestor="$(dirname -- "$ancestor")"
    done
  fi
  for name in "${names[@]+${names[@]}}"; do
    source="$repo_dir/skills/$name"
    dest="$target/$name"
    if ! $uninstall; then
      [[ -f "$source/SKILL.md" ]] || fail "skill not found: $name"
      if [[ -e "$dest" || -L "$dest" ]]; then
        [[ -L "$dest" && "$(readlink "$dest")" == "$source" ]] || fail "destination already exists: $dest"
      fi
    fi
  done
done

for target in "${targets[@]}"; do
  for name in "${names[@]+${names[@]}}"; do
    source="$repo_dir/skills/$name"
    dest="$target/$name"
    if $uninstall; then
      if [[ -L "$dest" && "$(readlink "$dest")" == "$source" ]]; then
        printf 'Unlink: %s\n' "$dest"
        if ! $dry_run; then rm -- "$dest"; fi
      else
        printf 'Keep: %s (not owned by this checkout)\n' "$dest"
      fi
    elif [[ -L "$dest" ]]; then
      printf 'Already linked: %s\n' "$dest"
    else
      printf 'Link: %s -> %s\n' "$dest" "$source"
      if ! $dry_run; then
        mkdir -p -- "$target"
        ln -s -- "$source" "$dest"
      fi
    fi
  done
done
if ((${#names[@]} == 0)); then printf 'No matching skills or owned links.\n'; fi
