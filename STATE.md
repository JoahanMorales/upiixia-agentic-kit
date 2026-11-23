# STATE

Phase: execution
Updated: 1795460289
AVAILABLE: UAK-156 UAK-158 UAK-159 UAK-160 UAK-161 UAK-162 UAK-163 UAK-164 UAK-165 UAK-166 UAK-167 UAK-169 
CLAIMED: -
BLOCKED: -
REVIEW: UAK-153 UAK-185 UAK-186 
INTEGRATED: (133; last 12) ... UAK-144 UAK-145 UAK-146 UAK-147 UAK-148 UAK-150 UAK-151 UAK-152 UAK-154 UAK-155 UAK-157 UAK-168 
CANCELLED: UAK-002 UAK-005 UAK-149 

Claims (first 24; status --task ID shows detail):
UAK-153 | REVIEW | kit-a1 | until 1795545900
UAK-185 | REVIEW | kit-a4 | until 1795546689
UAK-186 | REVIEW | kit-a2 | until 1795546051

Blockers: BLOCKED tasks; use status --task ID --summary.
Current decisions (last 5):
- 1795434435 | allow | JoahanMorales | test change: UAK-152 | Why: 19 jobs: los tests del asistente no caben en 9 grupos de Windows
- 1795451158 | plan | JoahanMorales/JoahanMorales | tasks added: UAK-169 UAK-185 UAK-186 | Why: backlog without PR (Plan-Channel: claims)
- 1795451168 | plan --amend | JoahanMorales/JoahanMorales | amended: UAK-153 Paths: kit/.uak/bin/lib/setup.py, kit/.uak/bin/lib/setup.html, kit/.uak/bin/guard, kit/.uak/docs/WHY.md
- 1795451178 | allow | JoahanMorales | test change: UAK-153 | Why: el token ya no se imprime y el nombre es la identidad de git; cuatro tests de asistente se ajustan a eso
- 1795451182 | allow | JoahanMorales | test change: UAK-154 | Why: 99.0.0 ahora es version mayor y bloquea; cuatro lineas de tests publican una version de la misma mayor

Global next step: available P0; else review PRs, tests, demo, rehearsal.
Why: bounded snapshot to resume without rereading history.
