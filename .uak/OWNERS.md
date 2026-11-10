# OWNERS · shared files of the kit

The engine's shared files belong to the task that closes the phase; every task before it is one of its dependencies,
so they may write there first (`uak claim` allows a task the owner waits on).

| Pattern | Owner task |
|---|---|
| `kit/.uak/bin/lib/` | UAK-006 |
| `kit/.uak/bin/uak` | UAK-006 |
| `kit/.uak/bin/uak-coordination` | UAK-006 |
| `kit/.uak/bin/smoke` | UAK-006 |
| `.github/workflows/` | UAK-006 |
| `kit/.github/workflows/` | UAK-027 |
