#!/usr/bin/env bash
# Link self-contained skills from this checkout. Compatible with Bash 3.2+.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install.sh [--skill NAME] [--target DIR] [--dry-run] [--uninstall]

Default: install all skills into $HOME/.agents/skills.
  --skill NAME   Select one skill (may be repeated).
  --target DIR   Use a different skill directory (absolute or relative).
  --dry-run      Show actions without changing the filesystem.
  --uninstall    Remove only links owned by this checkout.
  -h, --help     Show this help.

Keep the checkout in place while its skills are installed. Existing files,
directories, and links to other checkouts are never replaced.
EOF
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
target="${HOME:?HOME must be set}/.agents/skills"
dry_run=false
uninstall=false
selected=()
while (($#)); do
  case "$1" in
    --skill|--target)
      (($# >= 2)) && [[ -n "$2" && "$2" != --* ]] || fail "$1 requires a value"
      if [[ "$1" == --skill ]]; then selected+=("$2"); else target="$2"; fi
      shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    --uninstall) uninstall=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done
[[ "$target" == /* ]] || target="$PWD/$target"
target="${target%/}"
[[ -n "$target" ]] || fail 'refusing to use / as the skill directory'
for name in "${selected[@]+${selected[@]}}"; do
  [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || fail "invalid skill name: $name"
done

names=()
if ((${#selected[@]})); then
  names=("${selected[@]}")
elif $uninstall; then
  # Include stale links for skills removed by a subsequent git pull.
  for dest in "$target"/*; do
    [[ -L "$dest" ]] || continue
    name="${dest##*/}"
    [[ "$(readlink "$dest")" == "$repo_dir/skills/$name" ]] && names+=("$name")
  done
else
  for source in "$repo_dir"/skills/*; do
    [[ -d "$source" && -f "$source/SKILL.md" ]] || continue
    names+=("${source##*/}")
  done
fi

# Preflight the entire selection before creating directories or links.
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
if ((${#names[@]} == 0)); then printf 'No matching skills or owned links.\n'; fi
