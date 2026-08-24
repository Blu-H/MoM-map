#!/usr/bin/env bash
set -euo pipefail

git fetch --depth=1 origin gh-pages:refs/remotes/origin/gh-pages 2>/dev/null || true
if ! git rev-parse --verify origin/gh-pages >/dev/null 2>&1; then
  echo "No gh-pages branch yet; skipping cleanup."
  exit 0
fi

current_demos="$(mktemp)"
gh_pages_demos="$(mktemp)"

for d in sub_pages/demo_*/; do
  [ -d "$d" ] || continue
  basename "${d%/}"
done | sort -u > "$current_demos"

git ls-tree -d --name-only origin/gh-pages -- 'demo_*' | sort -u > "$gh_pages_demos"

stale="$(comm -23 "$gh_pages_demos" "$current_demos")"
if [ -z "$stale" ]; then
  echo "No stale demo pages to remove."
  exit 0
fi

echo "Removing stale demo pages from gh-pages: $stale"
git worktree add gh-pages-cleanup origin/gh-pages
(
  cd gh-pages-cleanup
  for d in $stale; do
    git rm -r --ignore-unmatch -- "$d"
  done
  git -c user.name="github-actions[bot]" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -m "Remove stale demo pages: $stale"
  git push "https://x-access-token:${DEPLOY_PAT}@github.com/${REPOSITORY}.git" HEAD:gh-pages
)
git worktree remove --force gh-pages-cleanup
