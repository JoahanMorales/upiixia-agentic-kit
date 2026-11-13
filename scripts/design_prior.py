#!/usr/bin/env python3
"""Regenerate the kit's default design prior (kit/.uak/settings/design-prior.json) from the maintainers' taste profiles.

    python3 scripts/design_prior.py --from ~/.uak/taste/<human>.json [--from ...] [--out FILE]

Run at release (the CHANGELOG step); the evidence line it prints (rounds, projects, picks) goes into the release notes.
The rules (traits only; picked in 2+ distinct projects, 3+ for type, scale and color; clearly off neutral) live in
kit/.uak/bin/lib/design_prior.py. Python 3.8+ standard library only."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kit", ".uak", "bin", "lib"))
import design_prior  # noqa: E402

if __name__ == "__main__":
    sys.exit(design_prior.main(["build"] + sys.argv[1:]))
