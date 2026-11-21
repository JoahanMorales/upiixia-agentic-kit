## UAK-037 · A gitleaks finding has its own way out

- **Type:** bug
- **Priority:** P2
- **Estimate:** 1 h
- **Depends on:** None
- **Paths:** kit/.uak/bin/secret-scan, kit/.uak/bin/lib/security.sh, kit/.uak/bin/uak, kit/.uak/bin/lib/commands.tsv, kit/.uak/docs/CLI.md, kit/.uak/tests/test_gitleaks_exception.py
- **Acceptance:**
  - when the finding comes from gitleaks (SECRET_EXTERNAL), the message points to its fingerprint and to `uak secret-exception ID --fingerprint FP --reason TEXT`, which secret-scan honors through a `.gitleaksignore` entry; the kit's own rules keep `--path --rule`. The scan stays on
  - why (deus-ex-machina): smoke flagged fixture history through gitleaks and suggested secret-exception, which refuses rules that are not the kit's
- **Tests:** gitleaks_finding_names_its_fingerprint, fingerprint_exception_clears_only_that_finding
- **Verify:** `python3 kit/.uak/tests/test_gitleaks_exception.py`
- **Next step:** the SECRET_EXTERNAL branch of kit/.uak/bin/secret-scan

