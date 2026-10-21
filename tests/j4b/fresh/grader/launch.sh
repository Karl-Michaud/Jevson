#!/bin/sh
# Grade one chunk: run `launch.sh NNN` from the grading directory (design §3 step 4; plan §6).
# It refuses to run inside project-asterion/ or inside any git worktree, prints the exact command, then runs it.
set -eu
nnn="${1:?usage: launch.sh NNN}"
here="$(pwd -P)"
case "$here/" in
  */project-asterion/*) echo "refused: $here is inside project-asterion/" >&2; exit 2 ;;
esac
if git -C "$here" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "refused: $here is inside a git worktree" >&2; exit 2
fi
[ -f "items-$nnn.jsonl" ] || { echo "refused: no items-$nnn.jsonl in $here" >&2; exit 2; }
instruction="$(sed "s/NNN/$nnn/g" instruction.md)"
set -- claude -p --model claude-opus-5-5 --restricted --tools Read,Write,Edit,Glob,Grep --strict-mcp-config \
  --mcp-config empty-mcp.json --no-chrome --disable-slash-commands --settings settings.json \
  --permission-mode acceptEdits --permission-prompts none "$instruction"
printf '%s\n' "$*"
exec "$@"
