---
model: sonnet
description: Checkpoint + handoff before closing, compacting or running out of tokens
argument-hint: "[ID]"
---
Task: ${ARGUMENTS:-$UAK_TASK}.
1. Commit and push everything that builds and passes (`git push -u origin HEAD`). Commit anything that doesn't pass as `wip: <what fails>`.
2. `bash .uak/bin/uak checkpoint ID --done "<green criteria>" --decision "<key decision or ->" --why "<why>" --fails "<what fails + exact error, or ->" --commands "<verify commands>" --next "<exact action: file, function or command>"`.
3. `bash .uak/bin/uak handoff ID`.
4. Low on tokens, or not coming back: `bash .uak/bin/uak release ID`. The task becomes AVAILABLE with your summary, and the next claim inherits it. Then `uak msg all --kind info "ID released with summary; next: <step>"`.
5. Black box: if the kit or protocol slowed you this session (a retry, a workaround, a missing feature), add 1–3 lines with `bash .uak/bin/uak bb add bug|friction|need|idea "what" --fix "idea"`. If nothing did, skip it.
6. Tell the human in 3 lines or fewer: state, exact next step, blockers.
