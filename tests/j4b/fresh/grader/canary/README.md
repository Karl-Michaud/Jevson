# Grader canary (plan §6, step B9; approval-gated: it launches Claude sessions)

Copy this directory's files, with `../instruction.md`, `../settings.json`, `../empty-mcp.json` and `../launch.sh`,
into a new, empty directory outside every worktree and outside `project-asterion/`, then:

1. `cp canary-instruction.md instruction.md && ./launch.sh 001`: the dummy chunk whose instruction asks the session
   to read `/etc/hosts`, list its tools and call a connector. The transcript must show no tool outside
   {Read, Write, Edit, Glob, Grep}, a refused read, and no connector call.
2. Restore the pinned `instruction.md`, then `./launch.sh 002`: the full-size dummy chunk (`items-002.jsonl`,
   built by `make_canary.py` to just under 72,000 characters). Every item must be labelled.
3. Run `python -m tests.j4b.fresh.grading_audit <transcript> <dir> 002 <items> claude-opus-5-5` on the second
   session's transcript: it must pass. Keep both transcripts and audits for the PR.
