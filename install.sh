#!/usr/bin/env bash
# UPIIXIA Agentic Kit installer.
#   bash install.sh --mode sprint|marathon [--stack fastapi-react|nextjs|django|go|expo|python-data|ai-agent|none] [--skills ai,tdd] [--no-blackbox] [--no-mcp] [--update] TARGET
# Never overwrites your files: if AGENTS.md, CLAUDE.md, settings.json… already exist and differ,
# the kit's version is written as <file>.uak-new for you to merge.
# --update replaces only the engine (.uak/bin, docs, modes, templates, tests, settings, stacks, skills)
# and keeps PROJECT.md, TASKS.md and OWNERS.md.
# Harnesses: Claude Code (.claude), Codex (.codex), Cursor (.cursor), Gemini CLI (.gemini) all get
# tiered subagents (fast / balanced / strong) and, where the harness has hooks, the same guard.
# --no-mcp leaves out the optional MCP server config (.mcp.json, .cursor/mcp.json and the uak blocks of
# .codex/config.toml and .gemini/settings.json): agents use the uak CLI through Bash, which works the same.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
kit="$here/kit"
mode= stack=none extra= update=no target= blackbox=on mcp=on
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) mode=${2:-}; shift 2;;
    --stack) stack=${2:-}; shift 2;;
    --skills) extra=${2:-}; shift 2;;
    --update) update=yes; shift;;
    --no-blackbox) blackbox=off; shift;;
    --no-mcp) mcp=off; shift;;
    -h|--help) sed -n '2,11p' "$0"; exit 0;;
    -*) printf 'Unknown option: %s\n' "$1" >&2; exit 2;;
    *) target=$1; shift;;
  esac
done
case "$mode" in sprint|marathon) ;; *) printf '%s\n' 'Missing --mode sprint|marathon (the human chooses; there is no default):' \
  '  sprint   = hackathon, demo day or prototype with a deadline: speed, auto-merge after review, a stunning frontend' \
  '  marathon = real product with users after launch: specs, security reviews, human merges, CI' >&2; exit 2;; esac
[ -n "$target" ] || { printf '%s\n' 'Missing TARGET (root of a Git repository)' >&2; exit 2; }
target=$(cd "$target" && pwd)
git -C "$target" rev-parse --show-toplevel >/dev/null 2>&1 || { printf '%s\n' "$target is not a Git repository (git init first)" >&2; exit 2; }
[ "$stack" = none ] || [ -d "$kit/.uak/stacks/$stack" ] || { printf 'Unknown stack: %s (available: %s)\n' "$stack" "$(ls "$kit/.uak/stacks" | tr '\n' ' ')" >&2; exit 2; }

say() { printf '%s\n' "$*"; }
put() { # put SRC DEST: copy if missing; if it exists and differs, write DEST.uak-new
  mkdir -p "$(dirname "$2")"
  if [ ! -e "$2" ]; then cp "$1" "$2"; say "  + ${2#$target/}"
  elif ! cmp -s "$1" "$2"; then cp "$1" "$2.uak-new"; say "  ~ ${2#$target/} exists: merge ${2#$target/}.uak-new"
  fi
}
nomcp() { # nomcp SRC: SRC without its uak MCP server block (both blocks are last in their file)
  case "$1" in
    *.toml) awk '/^# The harness as native tools/{exit} {print}' "$1" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}';;
    *.json) awk '/^  "mcpServers": \{/{sub(/,$/, "", prev); print prev; print "}"; done=1; exit} NR>1{print prev} {prev=$0} END{if(!done)print prev}' "$1";;
  esac
}
putmcp() { # putmcp SRC DEST: put, minus the MCP server block with --no-mcp
  if [ "$mcp" = on ]; then put "$1" "$2"; return; fi
  t=$(mktemp); nomcp "$1" > "$t"; put "$t" "$2"; rm -f "$t"
}
putdir() { (cd "$1" && find . -type f) | while IFS= read -r f; do put "$1/${f#./}" "$2/${f#./}"; done; }

say "UPIIXIA Agentic Kit → $target (mode $mode, stack $stack${extra:+, skills $extra})"
if [ -d "$target/.uak/bin" ] && [ "$update" = no ]; then
  say "The target already has .uak/. Use --update to refresh the engine." >&2; exit 2
fi
mkdir -p "$target/.uak"
for part in bin docs modes templates tests settings stacks skills; do
  rm -rf "$target/.uak/$part"
  cp -R "$kit/.uak/$part" "$target/.uak/$part"
done
cp "$kit/.uak/VERSION" "$target/.uak/VERSION"
# Coach templates: copied on install; on --update they are refreshed too (they are engine text, not project data).
cp "$kit/.uak/reminders.md" "$target/.uak/reminders.md"
chmod +x "$target"/.uak/bin/* 2>/dev/null || true
say "  + .uak/ (engine, modes, templates, docs, tests, skill library)"
[ -f "$target/.uak/PROJECT.md" ] || { cp "$kit/.uak/templates/PROJECT.$mode.md" "$target/.uak/PROJECT.md"; say "  + .uak/PROJECT.md"; }
[ -f "$target/.uak/OWNERS.md" ] || { cp "$kit/.uak/templates/OWNERS.template.md" "$target/.uak/OWNERS.md"; say "  + .uak/OWNERS.md"; }
if [ "$blackbox" = off ] && grep -q '^Blackbox: on' "$target/.uak/PROJECT.md"; then
  sed 's/^Blackbox: on$/Blackbox: off/' "$target/.uak/PROJECT.md" > "$target/.uak/PROJECT.md.tmp" && mv "$target/.uak/PROJECT.md.tmp" "$target/.uak/PROJECT.md"
fi
grep -Eq "^Mode: $mode\$" "$target/.uak/PROJECT.md" || say "  ! .uak/PROJECT.md does not declare 'Mode: $mode' (left unchanged)"

put "$kit/AGENTS.md" "$target/AGENTS.md"
put "$kit/CLAUDE.md" "$target/CLAUDE.md"
put "$kit/.uak/settings/settings.$mode.json" "$target/.claude/settings.json"
putdir "$kit/.claude/commands" "$target/.claude/commands"
putdir "$kit/.claude/agents" "$target/.claude/agents"
case "$mode" in
  sprint) rm -f "$target/.claude/agents/security-reviewer.md" "$target/.claude/commands/uak-spec.md"
          skills="karpathy-guidelines verification-before-completion systematic-debugging webapp-testing design-taste-frontend redesign-existing-projects";;
  marathon) rm -f "$target/.claude/agents/design-critic.md" "$target/.claude/commands/uak-design-lock.md" "$target/.claude/commands/uak-demo.md"
          skills="karpathy-guidelines verification-before-completion systematic-debugging webapp-testing test-driven-development";;
esac
case ",$extra," in *,ai,*) skills="$skills mcp-builder";; esac
case ",$extra," in *,tdd,*) case " $skills " in *" test-driven-development "*) ;; *) skills="$skills test-driven-development";; esac;; esac
case "$stack" in fastapi-react|nextjs|expo) skills="$skills vercel-react-best-practices";; esac
[ "$stack" != ai-agent ] || case " $skills " in *" mcp-builder "*) ;; *) skills="$skills mcp-builder";; esac
for s in $skills; do putdir "$kit/.uak/skills/$s" "$target/.claude/skills/$s"; done
if [ "$stack" != none ]; then
  putdir "$kit/.uak/stacks/$stack/skills" "$target/.claude/skills"
  [ ! -f "$kit/.uak/stacks/$stack/smoke-project.example" ] || put "$kit/.uak/stacks/$stack/smoke-project.example" "$target/.uak/bin/smoke-project.example"
fi
put "$kit/.cursor/rules/uak.mdc" "$target/.cursor/rules/uak.mdc"
put "$kit/.cursor/hooks.json" "$target/.cursor/hooks.json"
if [ "$mcp" = on ]; then
  put "$kit/.cursor/mcp.json" "$target/.cursor/mcp.json"
  put "$kit/.mcp.json" "$target/.mcp.json"
fi
putmcp "$kit/.uak/settings/codex.$mode.toml" "$target/.codex/config.toml"
put "$kit/.codex/hooks.json" "$target/.codex/hooks.json"
putmcp "$kit/.gemini/settings.json" "$target/.gemini/settings.json"
case "$mode" in sprint) skip_agent=security-reviewer;; *) skip_agent=design-critic;; esac
for h in .codex .cursor .gemini; do # the same subagents as .claude/agents, minus the other mode's
  for f in "$kit/$h/agents/"*; do
    case "$(basename "$f")" in "$skip_agent".*) continue;; esac
    put "$f" "$target/$h/agents/$(basename "$f")"
  done
done
for link in .agents/skills .cursor/skills; do # Codex, Cursor and others read the same skills
  mkdir -p "$target/$(dirname "$link")"
  [ -e "$target/$link" ] || { ln -s ../.claude/skills "$target/$link"; say "  + $link → .claude/skills"; }
done
put "$kit/.githooks/pre-commit" "$target/.githooks/pre-commit"
chmod +x "$target/.githooks/pre-commit" 2>/dev/null || true
put "$kit/.github/pull_request_template.md" "$target/.github/pull_request_template.md"
put "$kit/.github/workflows/uak.yml" "$target/.github/workflows/uak.yml"
put "$kit/.github/workflows/uak-tick.yml.example" "$target/.github/workflows/uak-tick.yml.example"
[ "$mode" != marathon ] || put "$kit/.github/CODEOWNERS.example" "$target/.github/CODEOWNERS.example"

touch "$target/.gitignore"
# Generated files too: an agent's `git add -A` after running tests committed __pycache__ and the merge gate stopped
# on it (adoption eval, 2026-10). Common build/cache output of the supported stacks.
for line in .env '.env.*' '!.env.example' .uak-env .claude/settings.local.json __pycache__/ '*.pyc' .pytest_cache/ \
    .venv/ node_modules/ .next/ dist/ .DS_Store; do
  grep -qxF -- "$line" "$target/.gitignore" || { printf '%s\n' "$line" >> "$target/.gitignore"; say "  + .gitignore: $line"; }
done
git -C "$target" config core.hooksPath .githooks

cat <<EOF

Done. Next:
  1. cd "$target" && bash .uak/bin/doctor
  2. Open Claude Code (or Codex / Cursor / Gemini CLI) there and run /uak-setup
  3. /uak-plan → each agent: bash .uak/bin/wt new ID --agent NAME
Files ending in .uak-new: merge them by hand; the kit never overwrites yours.
Codex: trust the project once so .codex/config.toml and .codex/hooks.json load (/hooks to review them).
MCP server: $mcp. $( [ "$mcp" = on ] && echo "Claude Code asks once to approve 'uak'; declining it is fine: the CLI does the same." || echo "Agents use the uak CLI; reinstall without --no-mcp to add the native tools.")
Black box: $blackbox. Agents record kit problems in claims:blackbox/ so the kit can be fixed
(no code, paths or identities). Turn off any time: 'Blackbox: off' in .uak/PROJECT.md.
EOF
