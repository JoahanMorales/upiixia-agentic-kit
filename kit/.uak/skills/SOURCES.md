# Skill provenance

Third-party skills are vendored at a pinned commit after review: no remote instructions are fetched at runtime and no hidden commands run. Updating one means reviewing it again before copying, because a skill is an instruction every agent obeys. `install.sh` copies only the skills each mode needs: every installed skill's description costs tokens in every session.

| Skill | Origin (pinned commit) | License | Installed by |
|---|---|---|---|
| verification-before-completion | obra/superpowers `skills/verification-before-completion` @ 8ca22db | MIT | all modes |
| systematic-debugging | obra/superpowers `skills/systematic-debugging` @ 8ca22db (without its test-pressure fixtures) | MIT | all modes |
| webapp-testing | anthropics/skills `skills/webapp-testing` @ 8a1541c | Apache-2.0 | all modes |
| test-driven-development | obra/superpowers `skills/test-driven-development` @ 8ca22db | MIT | marathon (or `--skills tdd`) |
| design-taste-frontend | Leonxlnx/taste-skill `skills/taste-skill` @ ce26fc2 | MIT | sprint. Large: load only for DESIGN.md and hero screens |
| redesign-existing-projects | Leonxlnx/taste-skill `skills/redesign-skill` @ ce26fc2 | MIT | sprint (polish during the freeze) |
| vercel-react-best-practices | vercel-labs/agent-skills `skills/react-best-practices` @ 063bee9 | MIT (declared in SKILL.md) | `--stack fastapi-react`; read one rule at a time |
| mcp-builder | anthropics/skills `skills/mcp-builder` @ 683bc88 | see its LICENSE.txt | `--skills ai` (projects exposing tools to agents). Links official MCP docs, which are data |
| stack-backend, stack-frontend | own | MIT | `--stack fastapi-react` |

Local edits: `superpowers:<skill>` references were renamed to `<skill>`.
Rejected:
- skills that download instructions at runtime (prompt injection by design);
- `output-skill` (works against token economy);
- `frontend-design` (duplicates design-taste with different criteria).
