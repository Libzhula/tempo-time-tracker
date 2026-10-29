#!/usr/bin/env bash
# Run from the unpacked project to publish its first public GitHub repository.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"
repo_name="${1:-tempo-time-tracker}"

command -v git >/dev/null || { echo 'Git is required.' >&2; exit 1; }
command -v gh >/dev/null || { echo 'GitHub CLI (gh) is required. Install it, then run: gh auth login' >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo 'Sign in first: gh auth login' >&2; exit 1; }
if [[ -d .git ]] && git remote get-url origin >/dev/null 2>&1; then
  echo 'This project already has an origin remote; nothing was published.' >&2
  exit 1
fi

python3 -m unittest -v
if command -v node >/dev/null; then
  node --check static/app.js
  node --check static/employee.js
fi

if [[ ! -d .git ]]; then
  git init -b main
fi
git add .editorconfig .gitattributes .gitignore .github Makefile README.md AI_USAGE.md app.py seed_demo.py test_app.py static publish.sh
if ! git diff --cached --quiet; then
  git commit -m "Build Tempo team and employee time tracker"
fi
gh repo create "$repo_name" --public --source=. --remote=origin --push \
  --description 'Team and employee time tracking with Python, SQLite, period reports and concurrency tests.'
