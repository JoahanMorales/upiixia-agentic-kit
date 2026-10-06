# Security policy

Report vulnerabilities privately through GitHub's "Report a vulnerability" (Security tab) on this repository. Include steps to reproduce, the affected file and the impact. We aim to answer within 7 days.

In scope:
- a guard bypass that runs a blocked destructive command;
- a secret-scanner miss on a supported format;
- privilege escalation through the coordination protocol, e.g. approving your own task or merging without a valid review.

The guards are defense in depth, not a sandbox: a bypass by an agent deliberately writing a script is a known limitation (see `kit/.uak/docs/SECURITY.md`).
