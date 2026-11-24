# Existing tests a human allowed to change (uak allow --tests)

Append-only. Format: - ID | epoch | human | reason. Why: a test is a spec; changing one is a human decision.

- UAK-068 | 1794533900 | JoahanMorales | gene count 8 to 9 (stage gene)
- UAK-082 | 1794637977 | JoahanMorales | flake de Windows en la limpieza
- UAK-083 | 1794676817 | JoahanMorales | premisas que cambian con el tope de three.js y las fuentes distintas
- UAK-141 | 1795300954 | JoahanMorales | the minimal-count assertions compare against the bound with its 15% margin; calibrated from real Windows runs (one shard took 26m36s of 25)
- UAK-144 | 1795382352 | JoahanMorales | the Windows table is now in measured Windows seconds, the bound is 30 min (test_flaky_guard alone takes 25 min on Windows), WINDOWS_SCALE is gone
- UAK-150 | 1795392855 | JoahanMorales | twenty_runs_under_load and its assertion line moved unchanged from test_flaky_guard.py to test_flaky_guard_race.py; the MEASURED_* anchors in test_ci_shards.py got new values for the two files
- UAK-152 | 1795434435 | JoahanMorales | 19 jobs: los tests del asistente no caben en 9 grupos de Windows
- UAK-153 | 1795451178 | JoahanMorales | el token ya no se imprime y el nombre es la identidad de git; cuatro tests de asistente se ajustan a eso
- UAK-154 | 1795451182 | JoahanMorales | 99.0.0 ahora es version mayor y bloquea; cuatro lineas de tests publican una version de la misma mayor
- UAK-156 | 1795476545 | JoahanMorales | la tarea quita el temporizador de 60 s que test_dashboard_profiles.py:137 exige
- UAK-158 | 1795494033 | JoahanMorales | el asistente usa los tokens del panel y marcas SVG; cuatro líneas de test leían la paleta vieja y el glifo ✓
- UAK-159 | 1795502193 | JoahanMorales | el flujo pasa a diez pantallas; los tests de Dylan describen el flujo anterior
- UAK-160 | 1795502196 | JoahanMorales | el español se escribe desde códigos; los tests comparan frases traducidas
- UAK-162 | 1795502200 | JoahanMorales | el panel se rediseña según la maqueta; los tests leen la estructura anterior
