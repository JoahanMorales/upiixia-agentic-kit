# uak reminders (one per line: key: text). Edit freely; the hook reads this file.
# Injected by the PostToolUse hook at the moment of decision, as the newest context, each at most N times per session.
# Why: attention to the initial rules fades after ~15 tool calls (OpenDev, arXiv 2603.05344); event-driven, capped,
# specific reminders keep the agent on the harness without re-sending all the rules. MLB: 486 status/inbox/board/
# digest calls, 4 black box notes in 60 h, and the code map, `wait` and `learn` existed only in AGENTS.md.
card: UAK quick card — when this happens → run this (bash .uak/bin/uak …):
card: · learning the code, before opening files → map show · map find NAME · map callers NAME · map users FILE
card: · you change code another task uses → msg impact:ID --kind contract "what changed · what to do" (before pushing)
card: · waiting for a review, a dependency or a reply → wait ID --for approve|integrated|message (one call; never poll status)
card: · a trap the next agent will hit → learn "what bites · where · what to do"
card: · a criterion is green → commit, push, checkpoint ID … · the same failure twice → log ID --state BLOCKED "<error>"
card: · the kit itself got in your way → bb add friction "what happened" --fix "what would prevent it"
explore: UAK: {n} reads in a row. The code map answers structure questions without opening files: bash .uak/bin/uak map show (areas, hubs), map find NAME (file:line), map callers NAME, map users FILE.
poll: UAK: you checked status/inbox {n} times in {m} min. To wait for something, run it once: bash .uak/bin/uak wait {id}--for approve|integrated|message (returns when it happens; meanwhile no polling).
contract: UAK: you pushed changes to {files}, which other tasks import ({tasks}). Tell them before they build on the old shape: bash .uak/bin/uak msg impact:{id} --kind contract "what changed · what to do".
done: UAK: {id} is in review. Do not poll: bash .uak/bin/uak wait {id} --for approve (one call, returns on approve or reject). Meanwhile you may take other work with uak next.
friction: UAK: the same kit error came back. If the kit (not your code) made you retry or work around it, record one line: bash .uak/bin/uak bb add friction "what happened" --fix "what would prevent it".
checkpoint: UAK: {n} tool calls since your last checkpoint on {id}. Save the state the next session needs: bash .uak/bin/uak checkpoint {id} --done … --decision … --why … --fails … --commands … --next ….
