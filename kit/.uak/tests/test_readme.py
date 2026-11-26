#!/usr/bin/env python3
"""UAK-202: the README says what the kit is, readable by a person and by an agent, with a voice and without lies.

Why (the human, 2026-11-25): "every time it fills with more slop and buzzwords and it is not understandable for an
agent" (656 lines, 26 top-level sections, one appended per release); and on the first rewrite of 105 lines the same
day: "too short, lifeless, it does not help; as you defined the kit I would not feel like using it". So the README
may say where the kit is going, marked as an aim, and says what works today in sentences that are true today.

  readme_is_at_most_300_lines               the whole README fits in 300 lines
  top_has_banner_vision_and_badges          the banner, the title, the tagline with what the kit is not, one line with
                                            the vision (marked as the aim) and the
                                            badges (tests, license, runtime dependencies, coding tools, M8ven)
  first_screen_answers_the_four_questions   then, with nothing else before them: what it is, who it is for, what you
                                            have after ten minutes, the one command to start
  no_empty_words                            no word of EMPTY_WORDS in the README, llms.txt or the three docs it links,
                                            and no emoji in the README or llms.txt
  every_number_has_a_source                 a measurement in the README sits next to its source (a task, a run,
                                            `uak metrics` or docs/EVIDENCE.md)
  wins_name_their_event_and_source          each win: event, date, place, the entry's public repository (or "not
                                            public"), the kit version, and a source that says it
  comparison_rows_have_a_source_and_a_date  each tool beside the kit: a link to its own docs, the date it was checked,
                                            and where it does more than the kit
  every_command_exists                      every uak, wt, install.sh and slash command shown exists with the options
                                            shown, and the shell blocks paste as they are (no placeholders)
  llms_txt_agrees_with_the_readme           llms.txt is shorter, says the same things in the same order and claims
                                            nothing (command, link, number) the README does not
  every_old_section_has_a_home              each heading of the old README has a home in the README, docs/GUIDE.md,
                                            docs/REFERENCE.md or docs/EVIDENCE.md, or a "dropped: reason"
  sections_in_order_with_one_for_agents     the outline, and the section that tells an agent which file to read for what
  images_show_todays_product_with_alt_text  every image exists and has alt text saying what it shows

To ban one more word: add a line to EMPTY_WORDS. Standard library only.
Run: python3 kit/.uak/tests/test_readme.py [--case NAME]."""
import argparse
import re
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
README = REPO / "README.md"
LLMS = REPO / "llms.txt"
GUIDE = REPO / "docs" / "GUIDE.md"
REFERENCE = REPO / "docs" / "REFERENCE.md"
EVIDENCE = REPO / "docs" / "EVIDENCE.md"
COMMANDS = REPO / "kit" / ".uak" / "bin" / "lib" / "commands.tsv"
WT = REPO / "kit" / ".uak" / "bin" / "wt"
INSTALL = REPO / "install.sh"
SLASH = REPO / "kit" / ".claude" / "commands"
MAX_LINES = 300
SCREEN = 60   # "the first screen": the banner, the title and the badges, then what a laptop shows

# Empty words: they sell with nothing behind them. One pattern per line, case-insensitive; add a line to ban one more.
# They apply to the README, llms.txt and the three docs the README links. "No chaos" is allowed: it is the kit's aim,
# and the README marks it as an aim.
EMPTY_WORDS = [
    r"\bbattle[- ]tested\b",
    r"\bblazing(ly)?\b",
    r"\bseamless(ly)?\b",
    r"\bpowerful\b",
    r"\bsupercharg\w*",
    r"\bnext[- ]level\b",
    r"\bunlock\w*",
    r"\beffortless(ly)?\b",
    r"\brobust(ly|ness)?\b",
    r"\bcutting[- ]edge\b",
    r"\bgame[- ]chang\w*",
    r"\brevolution\w*",
    r"\bworld[- ]class\b",
    r"\bbest[- ]in[- ]class\b",
    r"\bstate[- ]of[- ]the[- ]art\b",
    r"\blightning\b",
    r"\bmagic(al|ally)?\b",
    r"\bstunning\b",
    r"\bwow\b",
    r"\bdelight\w*",
    r"\bultimate\b",
    r"\bunleash\w*",
    r"\bempower\w*",
    r"\bleverag\w*",
    r"\belevat\w*",
    r"\bstreamlin\w*",
    r"\bturbo\w*",
    r"\b10x\b",
    r"\bsuperpower\w*",
    r"\bsimply\b",
    r"\bjust works\b",
    r"\bawesome\b",
    r"\bamazing\b",
    r"\bincredibl[ey]\b",
    r"\bsleek\b",
    r"\bbeautiful(ly)?\b",
    r"\bhassle[- ]free\b",
    r"\bzero[- ]config\b",
    r"\bpainless\b",
    r"\bfrictionless\b",
    r"\bbulletproof\b",
    r"\brock[- ]solid\b",
    r"\bproduction[- ]ready\b",
    r"\benterprise[- ]grade\b",
    r"\bfirst[- ]class\b",
    r"\bin seconds\b",
    r"\bfor free\b",
    r"\bhit the wall\b",
    # superlatives
    r"\bbest\b",
    r"\bfastest\b",
    r"\beasiest\b",
    r"\bsimplest\b",
    r"\bsmartest\b",
    r"\bgreatest\b",
    r"\bfinest\b",
    r"\bsafest\b",
    r"\bcheapest\b",
    r"\bmost (powerful|advanced|complete|reliable|secure)\b",
    # flourishes ("not X but Y" and its cousins)
    r"\bnot (just|only|merely|simply)\b",
    r"\bisn't just\b",
    r"\bmore than just\b",
    r"\bnot [^.,;]{1,40}, but\b",
]
EMOJI = re.compile("[☀-➿■-◿\U0001f000-\U0001faff⭐⬆⬇⤴⤵]")

# What the first screen answers, in order. Each is a bold label at the start of a line: "**What it is.** ...".
LABELS = ["What it is", "Who it is for", "What you have after ten minutes", "Start"]
# Words a person outside the project does not know: the first sentence explains the kit without them.
JARGON = ["claim", "lease", "worktree", "harness", "sprint", "marathon", "uak", "protocol", "orchestrat", "swarm",
          "agentic"]

# The sections after the first screen, in this order (other sections may sit between them).
OUTLINE = ["Why it exists", "See it run", "Get started", "How it works", "What it has won", "How it compares",
           "What it does not do", "Where to read more", "For an agent reading this", "Contributing", "License"]
# The top of the README, before the four answers.
BANNER = "docs/media/banner.png"
TITLE = "# UPIIXIA Agentic Kit"
TAGLINE = "**The harness for multi-agent teams.**"   # the human's words (2026-11-26), right under the title
TAGLINE_TRUTH = "no model"   # and in the same line, what it is not: it runs no model, it coordinates your tools
VISION_MARK = "aim"   # the vision line says it is the aim, not a claim about today
BADGES = {   # what each badge is, and a piece of its image URL
    "tests": "actions/workflows/test.yml/badge.svg",
    "license": "img.shields.io/badge/license-",
    "runtime dependencies": "img.shields.io/badge/runtime_deps-",
    "coding tools": "img.shields.io/badge/agents-",
    "M8ven": "m8ven.ai/badge/",
}
# The wins (the human, 2026-11-25): each must be in the table with its proof.
WINS = ["Kavak", "Chilangatón", "HackADA", "Diablos Rojos"]
# The section for an agent names each file with what it is for.
AGENT_FILES = {"AGENTS.md": "rules", "CLI.md": "command", "WHY.md": "reason"}

# A number is a measurement unless it is one of these. A measurement needs its source in the same paragraph, list
# item or table row.
NOT_MEASUREMENTS = [
    r"\b(Bash|Python|Git|Node|bash|python|git)\s+\d+(\.\d+)*\+?",   # a required version
    r"\bv\d+(\.\d+)*\b",                                          # a release
    r"\b[A-Z][A-Z0-9]*-\d+\b",                                     # a task ID
    r"^\s*\d+\.\s",                                                # the number of a numbered list item
    r"\b\d{4}-\d\d-\d\d\b",                                         # a date
    r"\b20\d\d\b",                                                 # a year, as in an event's name
    r"\b[A-Za-z]+-\d+\.\d+\b",                                      # a license: Apache-2.0, AGPL-3.0
    r"Stuff\+ 2240",                                               # an entry's name
]
SOURCES = [
    r"\]\(docs/EVIDENCE\.md(#[^)]*)?\)",
    r"https://github\.com/JoahanMorales/upiixia-agentic-kit/actions/runs/\d+",
    r"\bUAK-\d+\b",
    r"`uak metrics`",
]

# Images retired from the README, with the reason.
RETIRED_IMAGES = {
    # the v6.8 banner ("No chaos" as a fact, "~2 s" and "144x" with no source) was redrawn by UAK-202 in the same file
}
BADGE_HOSTS = ("https://github.com/JoahanMorales/upiixia-agentic-kit/actions/", "https://img.shields.io/",
               "https://m8ven.ai/")

# Every heading of the README before UAK-202 (2026-11-25, 656 lines) and where its content lives now: (file, the
# heading there) or "dropped: reason".
OLD_SECTIONS = [
    ("UPIIXIA Agentic Kit", ("README.md", "# UPIIXIA Agentic Kit")),
    ("Ship with a team of AI coding agents, in parallel, without chaos.",
     "dropped: a slogan; the first screen now says what the kit is"),
    ("Try it in 30 seconds (no setup, no API key)", ("README.md", "## See it run")),
    ("Quick start", ("README.md", "## Get started")),
    ("Stuck before the first claim? `uak start`", ("docs/GUIDE.md", "## When nothing can be claimed yet")),
    ("Why", ("README.md", "## Why it exists")),
    ("Two modes, one engine", ("docs/REFERENCE.md", "## Modes")),
    ("How it works", ("README.md", "## How it works")),
    ("Subagent orchestration: fast swarms, a balanced lead, a strong advisor", ("docs/REFERENCE.md", "## Subagent tiers")),
    ("Plan pacing: spend the 5-hour window, don't hit the wall", ("docs/REFERENCE.md", "## Usage pacing")),
    ("Black box: the kit learns from every team that uses it", ("docs/GUIDE.md", "## The black box")),
    ("Loop engineering", ("docs/GUIDE.md", "## Bounded fix loops")),
    ("Graph engineering", ("docs/GUIDE.md", "## The task graph and the code map")),
    ("The harness is used when it matters", ("docs/GUIDE.md", "## How agents are reminded of the tools")),
    ("Frontends that don't look generated", ("docs/GUIDE.md", "## Screens and the design chain")),
    ("Deploy in one command: `uak deploy`", ("docs/GUIDE.md", "## Deploy")),
    ("See everything: `uak dash`", ("docs/GUIDE.md", "## Follow the work: board and dashboard")),
    ("Speed", ("docs/EVIDENCE.md", "## Speed of the commands")),
    ("Token economy", ("docs/REFERENCE.md", "## Token use")),
    ("Battle-tested: six team runs", ("README.md", "## What it has won")),
    ("Works with", ("docs/REFERENCE.md", "## Coding tools")),
    ("Commands", ("docs/REFERENCE.md", "## Commands")),
    ("What's inside", ("docs/REFERENCE.md", "## What the install adds")),
    ("How it compares", ("README.md", "## How it compares")),
    ("FAQ", ("README.md", "## What it does not do")),
    ("Contributing", ("README.md", "## Contributing")),
    ("License", ("README.md", "## License")),
]
NEW_DOCS = ("docs/GUIDE.md", "docs/REFERENCE.md", "docs/EVIDENCE.md")


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


def source_repository():
    return (REPO / "scripts" / "kit_lint.py").is_file() and INSTALL.is_file()


def read(path):
    expect(path.is_file(), "%s exists" % path.relative_to(REPO).as_posix())
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def split_code(text):
    """(prose lines with fenced code blanked, [(language, [code lines])]). Line numbers are kept."""
    prose, blocks, fence, cur = [], [], None, None
    for line in text.split("\n"):
        m = re.match(r"^\s*(```|~~~)(.*)$", line)
        if fence is None and m:
            fence, cur = m.group(1), (m.group(2).strip(), [])
            prose.append("")
        elif fence is not None and line.strip().startswith(fence):
            blocks.append(cur)
            fence, cur = None, None
            prose.append("")
        elif fence is not None:
            cur[1].append(line)
            prose.append("")
        else:
            prose.append(line)
    return prose, blocks


def inline_code(lines):
    return [c for line in lines for c in re.findall(r"`([^`\n]+)`", line)]


def plain(line):
    """The words a reader sees: no inline code, no link targets, no HTML tags (an image keeps its alt text)."""
    line = re.sub(r"<img\b[^>]*\balt=\"([^\"]*)\"[^>]*>", r" \1 ", line)
    line = re.sub(r"<[^>]+>", " ", line)
    line = re.sub(r"`[^`\n]*`", " ", line)
    line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)
    line = re.sub(r"https?://\S+", " ", line)
    return line


def units(lines):
    """Paragraphs, list items, table rows and headings: the place a number and its source must share."""
    out, cur = [], []
    for line in lines:
        starts = re.match(r"^\s*([-*]|\d+\.)\s", line) or line.lstrip().startswith("|") or line.startswith("#")
        if not line.strip() or starts:
            if cur:
                out.append(cur)
            cur = [line] if line.strip() else []
            if line.startswith("#"):
                out.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        out.append(cur)
    return [u for u in out if u]


def headings(text, level=None):
    prose, _ = split_code(text)
    found = []
    for line in prose:
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if m and (level is None or len(m.group(1)) == level):
            found.append(m.group(2))
    return found


def section(text, title):
    """The lines of the H2 section TITLE, up to the next H2."""
    lines, out, inside = text.split("\n"), [], False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip() == title
            continue
        if inside:
            out.append(line)
    return out


def label_lines(lines):
    """{label: index of its line} for the bold labels of the first screen."""
    at = {}
    for i, line in enumerate(lines):
        for label in LABELS:
            if line.startswith("**%s.**" % label) and label not in at:
                at[label] = i
    return at


def label_text(lines, start):
    """The paragraph of a label: its line and the lines up to the next blank one, without the label."""
    out = []
    for line in lines[start:]:
        if not line.strip():
            break
        out.append(line)
    return re.sub(r"^\*\*[^*]+\*\*\s*", "", " ".join(out)).strip()


# ---------------------------------------------------------------------------------------------------- the cases


def readme_is_at_most_300_lines():
    lines = read(README).rstrip("\n").split("\n")
    expect(len(lines) <= MAX_LINES, "README.md has %d lines, more than %d: move walkthroughs to docs/GUIDE.md, lists to "
                                    "docs/REFERENCE.md and measurements to docs/EVIDENCE.md" % (len(lines), MAX_LINES))
    return "%d lines" % len(lines)


def top_lines(lines):
    """The lines before the first of the four answers: the top block (banner, title, vision, badges)."""
    at = label_lines(lines)
    return lines[:at[LABELS[0]]] if LABELS[0] in at else lines[:SCREEN]


def top_has_banner_vision_and_badges():
    lines = read(README).split("\n")
    top = top_lines(lines)
    filled = [l.strip() for l in top if l.strip()]
    first_image = next((l for l in filled if "<img" in l or l.startswith("![")), "")
    expect(filled and (filled[0] == first_image or filled[0].startswith("<p") and first_image),
           "the README opens with the banner image, nothing before it: %r" % (filled[0] if filled else ""))
    expect(BANNER in first_image, "the first image is the banner %s: %r" % (BANNER, first_image))
    expect(TITLE in filled, "the title %r is in the top block" % TITLE)
    title_at = filled.index(TITLE)
    expect(filled.index(first_image) < title_at, "the banner comes before the title")
    after = filled[title_at + 1:]
    expect(after and after[0].startswith(TAGLINE) and TAGLINE_TRUTH in after[0].lower(),
           "right under the title, %s and, in the same line, that it runs %s: %r" % (TAGLINE, TAGLINE_TRUTH, after[:1]))
    after = after[1:]
    expect(after and VISION_MARK in plain(after[0]).lower(),
           "then one line says the vision and marks it as the %s: %r" % (VISION_MARK, after[:1]))
    expect(len(re.findall(r"[.!](\s|$)", plain(after[0]))) <= 3 and len(plain(after[0]).split()) <= 40,
           "the vision is one short line: %r" % after[0])
    block = "\n".join(top)
    for what, piece in BADGES.items():
        expect(piece in block, "the %s badge is in the top block (%s)" % (what, piece))
    others = [l for l in after[1:] if not re.search(r"!\[[^\]]*\]\(https://|</?(p|div)\b", l)]
    expect(not others, "the top block holds only the banner, the title, the vision and the badges: %r" % others[:3])
    return "banner, title, vision, %d badges" % len(BADGES)


def first_screen_answers_the_four_questions():
    text = read(README)
    lines = text.split("\n")
    at = label_lines(lines)
    for label in LABELS:
        expect(label in at, "the first screen has the line **%s.** ..." % label)
        expect(at[label] < SCREEN, "**%s.** is on the first screen (line %d, the screen is %d lines)"
               % (label, at[label] + 1, SCREEN))
    order = [at[l] for l in LABELS]
    expect(order == sorted(order), "the four answers come in this order: %s" % " · ".join(LABELS))
    between = [l for l in lines[at[LABELS[0]]:at["Start"]] if l.strip() and not any(l.startswith("**%s.**" % x) for x in LABELS)]
    expect(not [l for l in between if l.startswith("#") or "<img" in l or l.startswith("![")],
           "nothing but the answers between them: %r" % between[:3])
    what = label_text(lines, at[LABELS[0]])
    words = what.split()
    expect(len(re.findall(r"[.!?](\s|$)", what)) == 1 and what.endswith("."),
           "what it is is one sentence: %r" % what)
    expect(len(words) <= 50, "what it is fits in 50 words: %d" % len(words))
    low = what.lower()
    for word in JARGON:
        expect(word not in low, "what it is uses no word of the project (%r): %r" % (word, what))
    expect("coding agent" in low and "git" in low, "what it is says it is about coding agents and Git: %r" % what)
    for label in LABELS[1:3]:
        body = label_text(lines, at[label])
        expect(body and len(body.split()) <= 70, "**%s.** answers in at most 70 words: %r" % (label, body))
    # The one command: the first fenced block after **Start.**, on the first screen, one command line.
    rest = lines[at["Start"]:SCREEN]
    expect(any(l.strip().startswith("```") for l in rest), "a code block follows **Start.** on the first screen")
    _, blocks = split_code("\n".join(rest))
    expect(blocks, "the start command is in a fenced block")
    lang, code = blocks[0]
    commands = [l for l in code if l.strip() and not l.strip().startswith("#")]
    expect(lang in ("bash", "sh", "shell"), "the start block is marked bash: %r" % lang)
    expect(len(commands) == 1, "one command to start, on one line: %r" % commands)
    expect("install.sh" in commands[0], "the start command runs the installer: %r" % commands[0])
    return "start: " + commands[0]


def empty_word_hits(text):
    prose, _ = split_code(text)
    hits = []
    for n, line in enumerate(prose, 1):
        seen = plain(line)
        for pattern in EMPTY_WORDS:
            m = re.search(pattern, seen, re.I)
            if m:
                hits.append("line %d: %r (%s)" % (n, m.group(0), line.strip()[:100]))
    return hits


def no_empty_words():
    found = []
    for path in (README, LLMS, GUIDE, REFERENCE, EVIDENCE):
        found += ["%s %s" % (path.relative_to(REPO).as_posix(), h) for h in empty_word_hits(read(path))]
    expect(not found, "empty words: " + "; ".join(found[:12]))
    for path in (README, LLMS):
        for n, line in enumerate(read(path).split("\n"), 1):
            m = EMOJI.search(line)
            expect(not m, "%s line %d has an emoji or pictograph %r: %r" % (path.name, n, m and m.group(0), line[:80]))
    return "%d patterns, 5 files" % len(EMPTY_WORDS)


def table(lines):
    """[(header cells), [row cells]] of the first Markdown table in LINES."""
    rows = [l for l in lines if l.lstrip().startswith("|")]
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [c for c in cells if not all(re.match(r"^:?-{3,}:?$", x) for x in c if x)]
    return (cells[0], cells[1:]) if cells else ([], [])


def wins_name_their_event_and_source():
    readme = read(README)
    head, rows = table(section(readme, "What it has won"))
    expect(rows, "the section What it has won has a table")
    col = {name: next((i for i, h in enumerate(head) if name in h.lower()), None)
           for name in ("event", "date", "place", "entry", "kit", "source")}
    expect(all(v is not None for v in col.values()), "the wins table has the columns event, date, place, entry, kit, "
                                                      "source: %r" % head)
    changelog = read(REPO / "CHANGELOG.md")
    evidence = read(EVIDENCE)
    seen = []
    for r in rows:
        event = plain(r[col["event"]])
        seen.append(event)
        expect(re.search(r"\b\d{4}-\d\d-\d\d\b", r[col["date"]]), "%s: a date (YYYY-MM-DD): %r" % (event, r[col["date"]]))
        expect(plain(r[col["place"]]).strip(), "%s: the place obtained" % event)
        entry = r[col["entry"]]
        expect(re.search(r"\]\(https://github\.com/[\w.-]+/[\w.-]+\)", entry) or "not public" in entry,
               "%s: the entry's public repository, or \"not public\": %r" % (event, entry))
        expect(re.search(r"\bv\d+\.\d+\.\d+\b", r[col["kit"]]), "%s: the kit version it ran: %r" % (event, r[col["kit"]]))
        src = r[col["source"]]
        target = re.search(r"\]\(((CHANGELOG\.md|docs/EVIDENCE\.md)(#[^)]*)?|https?://[^)]+)\)", src)
        expect(target, "%s: a source (the CHANGELOG, the event's page or the statement in docs/EVIDENCE.md): %r"
               % (event, src))
        key = event.split()[0].lower()
        if target.group(2) == "CHANGELOG.md":
            low = changelog.lower()
            expect(key in low and plain(r[col["place"]]).strip().lower() in low,
                   "%s: CHANGELOG.md says the event and the place" % event)
        else:   # docs/EVIDENCE.md or a page: the dated record of the statement is in docs/EVIDENCE.md
            stated = [l for l in evidence.split("\n") if key in l.lower() and "statement" in l.lower()]
            expect(stated and re.search(r"\d{4}-\d\d-\d\d", stated[0]),
                   "%s: docs/EVIDENCE.md records the dated statement" % event)
    for win in WINS:
        expect(any(win.lower() in e.lower() for e in seen), "the win %r is in the table with its proof" % win)
    return "%d wins" % len(rows)


def comparison_rows_have_a_source_and_a_date():
    readme = read(README)
    head, rows = table(section(readme, "How it compares"))
    expect(rows, "the section How it compares has a table")
    src = next((i for i, h in enumerate(head) if "source" in h.lower()), None)
    more = next((i for i, h in enumerate(head) if "does more" in h.lower() or "better" in h.lower()), None)
    expect(src is not None and more is not None, "the table has a source column and one for where the other tool "
                                                 "does more: %r" % head)
    for r in rows:
        name = plain(r[0]).strip()
        expect(re.search(r"\]\(https?://[^)]+\)", r[src]), "%s: a link to its own docs or repository" % name)
        expect(re.search(r"\b\d{4}-\d\d-\d\d\b", r[src]), "%s: the date it was checked" % name)
        expect(plain(r[more]).strip() not in ("", "-", "—"), "%s: where it does more than the kit" % name)
    return "%d tools" % len(rows)


def unsourced_numbers(text):
    prose, _ = split_code(text)
    bad = []
    for unit in units(prose):
        raw = " ".join(unit)
        seen = " ".join(plain(l) for l in unit)
        for pattern in NOT_MEASUREMENTS:
            seen = re.sub(pattern, " ", seen, flags=re.M)
        numbers = re.findall(r"(?<![\w.])\d+(?:[.,]\d+)*", seen)
        if numbers and not any(re.search(s, raw) for s in SOURCES):
            bad.append("%s in %r" % (", ".join(numbers), raw.strip()[:120]))
    return bad


def every_number_has_a_source():
    bad = unsourced_numbers(read(README))
    expect(not bad, "numbers with no source next to them (a task, a run, `uak metrics` or docs/EVIDENCE.md): "
                    + " | ".join(bad[:6]))
    return "every number in the README is sourced"


def registry():
    usage = {}
    for line in read(COMMANDS).split("\n"):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        usage.setdefault(cols[0], []).append(cols[5] if len(cols) > 5 else "")
    return {name: " ".join(rows) for name, rows in usage.items()}


def has_option(usage, option):
    return re.search(re.escape(option) + r"(?![\w-])", usage) is not None


def command_text(text):
    """Every piece of code the README shows: the lines of its fenced blocks and its inline code spans."""
    prose, blocks = split_code(text)
    pieces = [l for _, code in blocks for l in code] + inline_code(prose)
    return [re.sub(r"\s#\s.*$", "", p) for p in pieces]   # a trailing comment is not part of the command


def problems_with_commands(text):
    reg = registry()
    wt_usage = read(WT).split("USAGE", 2)[1] if "USAGE" in read(WT) else read(WT)
    install_help = "\n".join(l for l in read(INSTALL).split("\n")[:40] if l.startswith("#"))
    bad, seen = [], []
    for piece in command_text(text):
        piece = re.sub(r"\"[^\"]*\"|'[^']*'", "\"\"", piece)   # a quoted argument is a value, not options of uak
        for part in re.split(r"\s*(?:&&|\|\||;|\|)\s*", piece):
            m = re.search(r"(?:^|[\s(])(?:bash\s+)?(?:\S*/)?uak\s+([a-z][\w-]*)(.*)$", part)
            if m and not re.search(r"\buak\s+[a-z][\w-]*@", part):
                name, rest = m.group(1), m.group(2)
                seen.append("uak " + name)
                if name not in reg:
                    bad.append("uak %s is not a command (commands.tsv): %r" % (name, part))
                    continue
                for opt in re.findall(r"(?<![\w-])--[a-z][\w-]*", rest):
                    if not has_option(reg[name], opt):
                        bad.append("uak %s has no option %s: %r" % (name, opt, part))
            m = re.search(r"(?:^|[\s(])(?:bash\s+)?(?:\S*/)?wt\s+([a-z]+)(.*)$", part)
            if m:
                sub, rest = m.group(1), m.group(2)
                seen.append("wt " + sub)
                lines = [l for l in wt_usage.split("\n") if l.startswith("wt %s" % sub)]
                if not lines:
                    bad.append("wt %s is not a wt command: %r" % (sub, part))
                    continue
                block = wt_usage.split("wt %s" % sub, 1)[1].split("\nwt ", 1)[0]
                for opt in re.findall(r"(?<![\w-])--[a-z][\w-]*", rest):
                    if not has_option(block, opt):
                        bad.append("wt %s has no option %s: %r" % (sub, opt, part))
            m = re.search(r"install\.sh(.*)$", part)
            if m:
                seen.append("install.sh")
                for opt in re.findall(r"(?<![\w-])--[a-z][\w-]*", m.group(1)):
                    if not has_option(install_help, opt):
                        bad.append("install.sh has no option %s in its help: %r" % (opt, part))
            for slash in re.findall(r"(?<![\w/])/(uak[-:][a-z-]+)", part):
                seen.append("/" + slash)
                if slash.startswith("uak:"):
                    ok = (REPO / "skills" / slash[4:] / "SKILL.md").is_file()
                else:
                    ok = (SLASH / (slash + ".md")).is_file()
                if not ok:
                    bad.append("/%s is not a slash command of the kit: %r" % (slash, part))
    return bad, seen


def placeholders(text):
    """Shell lines that cannot be pasted as they are."""
    _, blocks = split_code(text)
    bad = []
    for lang, code in blocks:
        if lang not in ("bash", "sh", "shell"):
            continue
        for line in code:
            cmd = re.sub(r"(^|\s)#.*$", "", line).strip()
            if not cmd:
                continue
            if re.search(r"<[^>]+>|/path/to|\.\.\.|…", cmd) or re.search(r"\b(ID|NAME|FILE|CMD|PATH|URL|TEXT|N)\b", cmd):
                bad.append(cmd)
    return bad


def every_command_exists():
    text = read(README)
    bad, seen = problems_with_commands(text)
    expect(seen, "the README shows commands")
    expect(not bad, "; ".join(bad[:8]))
    holes = placeholders(text)
    expect(not holes, "shell lines with a placeholder cannot be pasted as they are: %r" % holes[:4])
    return "%d commands checked" % len(seen)


def links(text):
    return [t.split("#", 1)[0] for t in re.findall(r"\]\(([^)\s]+)\)", text)] + \
           re.findall(r"<img\b[^>]*\bsrc=\"([^\"]+)\"", text)


def numbers_in(text):
    prose, _ = split_code(text)
    return set(re.findall(r"(?<![\w.])\d+(?:[.,]\d+)*", " ".join(plain(l) for l in prose)))


def llms_txt_agrees_with_the_readme():
    readme, llms = read(README), read(LLMS)
    expect(len(llms) < len(readme) and llms.count("\n") < readme.count("\n"),
           "llms.txt is shorter than the README: %d bytes, %d lines" % (len(llms), llms.count("\n")))
    lines = llms.split("\n")
    expect(lines[0].strip() == "# UPIIXIA Agentic Kit", "llms.txt opens with the title: %r" % lines[0])
    quote = " ".join(l[1:].strip() for l in lines if l.startswith(">"))
    rlines = readme.split("\n")
    what = label_text(rlines, label_lines(rlines)[LABELS[0]])
    expect(quote == what, "llms.txt's summary is the README's first sentence:\n  llms:   %r\n  README: %r" % (quote, what))
    # The same answers in the same order, before any section.
    first_h2 = next((i for i, l in enumerate(lines) if l.startswith("## ")), len(lines))
    head = "\n".join(lines[:first_h2]).lower()
    places = [head.find(l.lower()) for l in LABELS[1:]]
    expect(all(p >= 0 for p in places) and places == sorted(places),
           "llms.txt answers %s in this order before its first section" % " · ".join(LABELS[1:]))
    # Its sections are sections of the README, in the README's order.
    rh = headings(readme, 2)
    lh = headings(llms, 2)
    expect(lh, "llms.txt has sections")
    expect(all(h in rh for h in lh), "every section of llms.txt is a section of the README: %r not in %r"
           % ([h for h in lh if h not in rh], rh))
    expect([rh.index(h) for h in lh] == sorted(rh.index(h) for h in lh), "llms.txt keeps the README's order: %r" % lh)
    # No claim the README does not make: links, commands and numbers all come from the README.
    rl = set(links(readme))
    extra = [t for t in links(llms) if t not in rl]
    expect(not extra, "llms.txt links what the README does not: %r" % extra)
    rcode = "\n".join(command_text(readme)) + "\n" + readme
    extra = [c for c in command_text(llms) if c.strip() and c.strip() not in rcode]
    expect(not extra, "llms.txt shows code the README does not: %r" % extra)
    extra = sorted(numbers_in(llms) - numbers_in(readme))
    expect(not extra, "llms.txt has numbers the README does not: %r" % extra)
    bad, _ = problems_with_commands(llms)
    expect(not bad, "; ".join(bad[:4]))
    return "%d sections, %d links" % (len(lh), len(links(llms)))


def every_old_section_has_a_home():
    missing = []
    for old, home in OLD_SECTIONS:
        if isinstance(home, str):
            expect(home.startswith("dropped: ") and len(home) > len("dropped: ") + 10,
                   "%r: a dropped section says why: %r" % (old, home))
            continue
        path, heading = home
        text = read(REPO / path)
        prose, _ = split_code(text)
        if heading not in [l.rstrip() for l in prose]:
            missing.append("%r → %s %r" % (old, path, heading))
    expect(not missing, "old sections with no home: " + "; ".join(missing))
    readme = read(README)
    for doc in NEW_DOCS:
        n = len(re.findall(r"\]\(%s(#[^)]*)?\)" % re.escape(doc), readme))
        expect(n == 1, "the README links %s once (found %d)" % (doc, n))
    dropped = sum(1 for _, h in OLD_SECTIONS if isinstance(h, str))
    return "%d old headings: %d moved, %d dropped" % (len(OLD_SECTIONS), len(OLD_SECTIONS) - dropped, dropped)


def sections_in_order_with_one_for_agents():
    readme = read(README)
    h2 = headings(readme, 2)
    at = []
    for title in OUTLINE:
        expect(title in h2, "the README has a section %r (it has %r)" % (title, h2))
        at.append(h2.index(title))
    expect(at == sorted(at), "the sections come in this order: %s" % " · ".join(OUTLINE))
    body = "\n".join(section(readme, "For an agent reading this"))
    for name, what in AGENT_FILES.items():
        line = next((l for l in body.split("\n") if name in l), "")
        expect(line and what in line.lower(), "the section for an agent says %s is for the %s: %r" % (name, what, line))
    for target in re.findall(r"\]\(([^)#\s]+)", body):
        expect((REPO / target).exists(), "the section for an agent links a file that exists: %s" % target)
    return "outline in order"


def images_show_todays_product_with_alt_text():
    readme = read(README)
    images = [(src, alt) for alt, src in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)\)", readme)]
    for tag in re.findall(r"<img\b[^>]*>", readme):
        src = re.search(r"\bsrc=\"([^\"]+)\"", tag)
        alt = re.search(r"\balt=\"([^\"]*)\"", tag)
        images.append((src.group(1) if src else "", alt.group(1) if alt else ""))
    expect(images, "the README shows the product")
    images = [(src, alt) for src, alt in images if not src.startswith(BADGE_HOSTS)]   # the badges of the top block
    for src, alt in images:
        expect(not src.startswith("http"), "images are files of this repository (or a badge): %s" % src)
        expect((REPO / src).is_file(), "the image exists: %s" % src)
        expect(src not in RETIRED_IMAGES, "%s is retired: %s" % (src, RETIRED_IMAGES.get(src)))
        expect(len(alt.split()) >= 5 and Path(src).name not in alt,
               "the alt text of %s says what it shows (5 words or more): %r" % (src, alt))
    return "%d images" % len(images)


TESTS = [readme_is_at_most_300_lines, top_has_banner_vision_and_badges, first_screen_answers_the_four_questions,
         no_empty_words, every_number_has_a_source, wins_name_their_event_and_source,
         comparison_rows_have_a_source_and_a_date, every_command_exists, llms_txt_agrees_with_the_readme,
         every_old_section_has_a_home, sections_in_order_with_one_for_agents, images_show_todays_product_with_alt_text]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parents[2])   # smoke passes it
    parser.add_argument("--case", action="append")
    args = parser.parse_args()
    if not source_repository():
        print("README_RESULT PASS passed=0 failed=0 (no kit source repository here: the README is the kit's own)")
        return 0
    failed = ran = 0
    for test in TESTS:
        if args.case and test.__name__ not in args.case:
            continue
        ran += 1
        started = time.monotonic()
        try:
            note = test()
            print("PASS %s (%s, %.2fs)" % (test.__name__, note, time.monotonic() - started))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("FAIL %s (%s)" % (test.__name__, str(exc)[:1500]))
    print("README_RESULT %s passed=%d failed=%d" % ("PASS" if not failed else "FAIL", ran - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
