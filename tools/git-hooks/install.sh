#!/bin/sh
#
# Put the pre-commit hook in place.
#
# .git/hooks is not part of a repository, so every fresh clone starts without
# the guard that keeps family data out of the history. Run this once after
# cloning:
#
#     sh tools/git-hooks/install.sh
#
# A worktree has its own .git file rather than a folder, and its hooks live in
# the main checkout's .git/hooks - which `--git-path hooks` answers correctly
# and `$root/.git/hooks` does not.
#
here=$(cd "$(dirname "$0")" && pwd)
root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Kein git-Repository - nichts zu tun."
    exit 1
}
hooks=$(cd "$root" && git rev-parse --path-format=absolute --git-path hooks)
mkdir -p "$hooks"

cp "$here/pre-commit" "$hooks/pre-commit"
chmod +x "$hooks/pre-commit"
echo "pre-commit-Hook installiert: $hooks/pre-commit"
echo "Er bricht jeden Commit ab, der Familiendaten enthaelt."

# An older version of this installer also put a pre-push hook here, which read
# the trees and looked for real names inside the code. That check is gone: the
# separation of program and data is what protects the family, and no name is
# typed into the program in the first place. Remove the leftover so it does not
# keep running from an earlier install.
if [ -f "$hooks/pre-push" ]; then
    rm -f "$hooks/pre-push"
    echo "alter pre-push-Hook entfernt - der Namensabgleich ist abgeschafft."
fi
