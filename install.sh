#!/usr/bin/env bash
# UPIIXIA Agentic Kit installer.
#   bash install.sh --mode sprint|marathon [--stack fastapi-react|nextjs|django|go|expo|python-data|ai-agent|spring-boot|none]
#                   [--harness claude,codex,cursor,gemini] [--skills ai,tdd] [--no-blackbox] [--no-mcp] [--solo] [--update] TARGET
# Never overwrites your files: if AGENTS.md, CLAUDE.md, settings.json… already exist and differ,
# the kit's version is written as <file>.uak-new for you to merge. A file that is an earlier kit version nobody
# edited (its hash is in .uak/settings/known-files.txt) is simply updated.
# --update replaces only the engine (.uak/bin, docs, modes, templates, tests, settings, stacks, skills)
# and keeps PROJECT.md, TASKS.md and OWNERS.md.
# Harnesses: Claude Code (.claude), Codex (.codex), Cursor (.cursor), Gemini CLI (.gemini) all get
# tiered subagents (fast / balanced / strong) and, where the harness has hooks, the same guard.
# --solo (one human on the repo): reviews happen on claims between agent identities (Review-Mode: claims), because GitHub
# never lets a PR's author approve it; in marathon the human still merges every PR.
# --no-mcp leaves out the optional MCP server config (.mcp.json, .cursor/mcp.json and the uak blocks of
# .codex/config.toml and .gemini/settings.json): agents use the uak CLI through Bash, which works the same.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
kit="$here/kit"
mode= stack=none extra= update=no target= blackbox=on mcp=on harness=claude,codex,cursor,gemini solo=no
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode) mode=${2:-}; shift 2;;
    --stack) stack=${2:-}; shift 2;;
    --skills) extra=${2:-}; shift 2;;
    --update) update=yes; shift;;
    --no-blackbox) blackbox=off; shift;;
    --no-mcp) mcp=off; shift;;
    --solo) solo=yes; shift;;
    --harness) harness=${2:-}; shift 2;;
    -h|--help) sed -n '2,15p' "$0"; exit 0;;
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
for h in $(printf '%s' "$harness" | tr ',' ' '); do case "$h" in claude|codex|cursor|gemini) ;; *) printf 'Unknown harness: %s (claude, codex, cursor, gemini)\n' "$h" >&2; exit 2;; esac; done
has() { case ",$harness," in *",$1,"*) return 0;; *) return 1;; esac; }
[ "$stack" = none ] || [ -d "$kit/.uak/stacks/$stack" ] || { printf 'Unknown stack: %s (available: %s)\n' "$stack" "$(ls "$kit/.uak/stacks" | tr '\n' ' ')" >&2; exit 2; }

say() { printf '%s\n' "$*"; }
# An earlier version the kit shipped, unedited. Why: an update from v5.0 left 16 .uak-new files nobody had touched,
# settings.json among them, so the new hooks never reached the project.
known() { [ -f "$1" ] && grep -qx "$(git hash-object -- "$1" 2>/dev/null)" "$kit/.uak/settings/known-files.txt" 2>/dev/null; }
put() { # put SRC DEST: copy if missing; an unedited earlier kit version is updated; edited by you: DEST.uak-new
  mkdir -p "$(dirname "$2")"
  if [ ! -e "$2" ]; then cp "$1" "$2"; say "  + ${2#$target/}"
  elif cmp -s "$1" "$2"; then :
  elif known "$2"; then cp "$1" "$2"; rm -f "$2.uak-new"; say "  ^ ${2#$target/} updated (an earlier kit version, unedited)"
  else cp "$1" "$2.uak-new"; say "  ~ ${2#$target/} exists: merge ${2#$target/}.uak-new"
  fi
}
drop() { # drop FILE...: the other mode's kit files, only when they are the kit's (yours stay)
  for f in "$@"; do
    if [ -f "$f" ] && { cmp -s "$kit/${f#$target/}" "$f" || known "$f"; }; then rm -f "$f"; fi
  done
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
# The project's own smoke adapter lives in .uak/bin but is project data: an --update keeps it.
# Why (MLB hackathon): an update deleted .uak/bin/smoke-project and its provenance; the team restored them by hand.
keep=$(mktemp -d)
trap 'rm -rf "$keep"' EXIT
for f in smoke-project .smoke-project.provenance; do [ ! -f "$target/.uak/bin/$f" ] || cp -p "$target/.uak/bin/$f" "$keep/$f"; done
for part in bin docs modes templates tests settings stacks skills; do
  rm -rf "$target/.uak/$part"
  cp -R "$kit/.uak/$part" "$target/.uak/$part"
done
for f in smoke-project .smoke-project.provenance; do [ ! -f "$keep/$f" ] || { cp -p "$keep/$f" "$target/.uak/bin/$f"; say "  = .uak/bin/$f kept (project adapter)"; }; done
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
if [ "$solo" = yes ] && grep -q '^Review-Mode: gh$' "$target/.uak/PROJECT.md"; then
  sed 's/^Review-Mode: gh$/Review-Mode: claims/' "$target/.uak/PROJECT.md" > "$target/.uak/PROJECT.md.tmp" && mv "$target/.uak/PROJECT.md.tmp" "$target/.uak/PROJECT.md"
  say "  + .uak/PROJECT.md: Review-Mode: claims (--solo: agents review each other on claims; GitHub never lets you approve your own PR)"
fi
grep -Eq "^Mode: $mode\$" "$target/.uak/PROJECT.md" || say "  ! .uak/PROJECT.md does not declare 'Mode: $mode' (left unchanged)"

put "$kit/AGENTS.md" "$target/AGENTS.md"
# CLAUDE.md lives in .claude/ (Claude Code reads ./.claude/CLAUDE.md), so the root keeps only AGENTS.md, the file every
# other agent reads there. A root CLAUDE.md that is the kit's own (an older install) moves; a customized one stays.
# Why: a team found the ~12 kit entries at the root invasive.
if has claude; then
  sed 's|^@AGENTS.md$|@../AGENTS.md|' "$kit/CLAUDE.md" > "$keep/CLAUDE.md"
  if [ -f "$target/CLAUDE.md" ] && { cmp -s "$kit/CLAUDE.md" "$target/CLAUDE.md" || known "$target/CLAUDE.md"; }; then
    rm -f "$target/CLAUDE.md"; say "  > CLAUDE.md moved to .claude/CLAUDE.md (the root keeps AGENTS.md)"
  fi
  if [ -f "$target/CLAUDE.md" ]; then say "  ~ CLAUDE.md is yours: kept at the root; the kit's text is in .claude/CLAUDE.md.uak-new"
    mkdir -p "$target/.claude"; cp "$keep/CLAUDE.md" "$target/.claude/CLAUDE.md.uak-new"
  else put "$keep/CLAUDE.md" "$target/.claude/CLAUDE.md"; fi
fi
put "$kit/.uak/settings/settings.$mode.json" "$target/.claude/settings.json"
putdir "$kit/.claude/commands" "$target/.claude/commands"
putdir "$kit/.claude/agents" "$target/.claude/agents"
case "$mode" in
  sprint) drop "$target/.claude/agents/security-reviewer.md" "$target/.claude/commands/uak-spec.md"
          skills="karpathy-guidelines verification-before-completion systematic-debugging webapp-testing design-taste-frontend redesign-existing-projects product-ui";;
  marathon) drop "$target/.claude/agents/design-critic.md" "$target/.claude/commands/uak-design-lock.md" "$target/.claude/commands/uak-demo.md"
          skills="karpathy-guidelines verification-before-completion systematic-debugging webapp-testing test-driven-development";;
esac
case ",$extra," in *,ai,*) skills="$skills mcp-builder";; esac
case ",$extra," in *,tdd,*) case " $skills " in *" test-driven-development "*) ;; *) skills="$skills test-driven-development";; esac;; esac
case "$stack" in fastapi-react|nextjs|expo) skills="$skills vercel-react-best-practices"; case " $skills " in *" product-ui "*) ;; *) skills="$skills product-ui";; esac;; esac
[ "$stack" != ai-agent ] || case " $skills " in *" mcp-builder "*) ;; *) skills="$skills mcp-builder";; esac
for s in $skills; do putdir "$kit/.uak/skills/$s" "$target/.claude/skills/$s"; done
if [ "$stack" != none ]; then
  putdir "$kit/.uak/stacks/$stack/skills" "$target/.claude/skills"
  [ ! -f "$kit/.uak/stacks/$stack/smoke-project.example" ] || put "$kit/.uak/stacks/$stack/smoke-project.example" "$target/.uak/bin/smoke-project.example"
fi
# Each harness's own directory only for the harnesses the team uses (--harness; all four by default). .claude/
# stays in every install: the skills and the /uak-* phase scripts there are read by every harness.
if has cursor; then
  put "$kit/.cursor/rules/uak.mdc" "$target/.cursor/rules/uak.mdc"
  put "$kit/.cursor/hooks.json" "$target/.cursor/hooks.json"
  [ "$mcp" != on ] || put "$kit/.cursor/mcp.json" "$target/.cursor/mcp.json"
fi
[ "$mcp" != on ] || ! has claude || put "$kit/.mcp.json" "$target/.mcp.json"
if has codex; then
  putmcp "$kit/.uak/settings/codex.$mode.toml" "$target/.codex/config.toml"
  put "$kit/.codex/hooks.json" "$target/.codex/hooks.json"
fi
! has gemini || putmcp "$kit/.gemini/settings.json" "$target/.gemini/settings.json"
case "$mode" in sprint) skip_agent=security-reviewer;; *) skip_agent=design-critic;; esac
for h in codex cursor gemini; do # the same subagents as .claude/agents, minus the other mode's
  has "$h" || continue
  for f in "$kit/.$h/agents/"*; do
    case "$(basename "$f")" in "$skip_agent".*) continue;; esac
    put "$f" "$target/.$h/agents/$(basename "$f")"
  done
done
for link in .agents/skills .cursor/skills; do # Codex, Cursor and others read the same skills
  case "$link" in .agents/*) has codex || continue;; .cursor/*) has cursor || continue;; esac
  mkdir -p "$target/$(dirname "$link")"
  [ -e "$target/$link" ] || [ -L "$target/$link" ] || { ln -s ../.claude/skills "$target/$link"; say "  + $link → .claude/skills"; }
done
# The pre-commit secret scanner lives in .uak/githooks (engine, refreshed by --update). An older install's
# .githooks/pre-commit that is the kit's own is removed; a changed one stays and keeps working until you move it.
# Why: an --update removed a pre-commit the team had extended (it still called secret-scan) with everything they added.
mkdir -p "$target/.uak/githooks"; cp "$kit/.githooks/pre-commit" "$target/.uak/githooks/pre-commit"
chmod +x "$target/.uak/githooks/pre-commit" 2>/dev/null || true
hooks_path=.uak/githooks
if [ -f "$target/.githooks/pre-commit" ]; then
  if { cmp -s "$kit/.githooks/pre-commit" "$target/.githooks/pre-commit" || known "$target/.githooks/pre-commit"; } &&
     [ -z "$(ls -A "$target/.githooks" 2>/dev/null | grep -v '^pre-commit$')" ]; then
    rm -rf "$target/.githooks"; say "  > .githooks moved to .uak/githooks"
  else hooks_path=.githooks; say "  ~ .githooks has your own hooks: kept (core.hooksPath stays .githooks)"; fi
fi
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
case "$stack" in spring-boot) # Maven/Gradle build output
  for line in target/ .gradle/ build/ '*.class'; do
    grep -qxF -- "$line" "$target/.gitignore" || { printf '%s\n' "$line" >> "$target/.gitignore"; say "  + .gitignore: $line"; }
  done;; esac
# Another hook manager (husky, lefthook, pre-commit) owns core.hooksPath: keep it and say how to add the scan.
# Why: the installer replaced a husky hooksPath, and every husky hook stopped running without a word.
cur_hooks=$(git -C "$target" config --get core.hooksPath 2>/dev/null || true)
case "$cur_hooks" in
  ''|.githooks|.githooks/|.uak/githooks|.uak/githooks/) git -C "$target" config core.hooksPath "$hooks_path";;
  *) say "  ~ core.hooksPath is $cur_hooks (another hook manager): kept. Add the secret scan to its pre-commit: bash .uak/githooks/pre-commit";;
esac

cat <<EOF

Done. Next:
  1. cd "$target" && bash .uak/bin/uak start   (each step to the first claim, in order; runs doctor; again after each fix)
  2. Open Claude Code (or Codex / Cursor / Gemini CLI) there and run /uak-setup
  3. /uak-plan → each agent: bash .uak/bin/wt new ID (reuses a free identity, or --agent NAME)
Files ending in .uak-new: merge them by hand; the kit never overwrites yours.
Codex: trust the project once so .codex/config.toml and .codex/hooks.json load (/hooks to review them).
MCP server: $mcp. $( [ "$mcp" = on ] && echo "Claude Code asks once to approve 'uak'; declining it is fine: the CLI does the same." || echo "Agents use the uak CLI; reinstall without --no-mcp to add the native tools.")
Black box: $blackbox. Agents record kit problems in claims:blackbox/ so the kit can be fixed
(no code, paths or identities). Turn off any time: 'Blackbox: off' in .uak/PROJECT.md.
EOF
