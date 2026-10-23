---
name: stack-spring-boot
description: Conventions for the Spring Boot stack (package by feature, constructor injection, ProblemDetail errors, MockMvc and Testcontainers tests, Flyway). Use when adding a controller, service, repository, migration or test in this repo.
---
# Spring Boot stack
Setup and structure: `.uak/stacks/spring-boot/STACK.md`.

| Rule | Why |
|---|---|
| One task = one feature package `<base>/<feature>/` (controller, service, repository, `dto/`) plus its tests | disjoint claims; component scan wires it, nobody edits shared wiring |
| Constructor injection, `final` fields; no field `@Autowired` | testable without a Spring context |
| DTOs as `record`s at the HTTP boundary, validated with `jakarta.validation` (`@Valid`, `@NotBlank`…); entities never leave the service | the contract stays stable when the table changes |
| Errors through the shared `@RestControllerAdvice` as `ProblemDetail`; do not add another advice in a feature | one error shape for every client |
| `@Transactional` on service methods, not on controllers | one place for the unit of work |
| Feature settings in `@ConfigurationProperties(prefix = "app.<feature>")`; never read `System.getenv` in code | config is reviewable and typed |
| Tests: `@WebMvcTest` + MockMvc for controllers, plain JUnit for services, `@DataJpaTest` (marathon: Testcontainers) for repositories | fast tests a reviewer can run per package |
| Migrations: one Flyway file per task, timestamp version `V<yyyyMMddHHmm>__<feature>.sql`, reserved in OWNERS.md; never edit a merged migration, add a new one | Flyway versions are global; edited migrations break every other database |
| New dependencies: ask the owner of `pom.xml` (`uak msg <setup-ID> --kind request`); a feature task does not edit it | one dependency change at a time, reviewed |
| The port comes from `server.port: ${UAK_PORT:8080}`; never hard-code 8080 | agents run in parallel worktrees |
| External calls with timeouts and a labeled fallback (`"demo_data": true`) | the demo survives a dead API |

```bash
bash .uak/bin/q ./mvnw -q -B test -Dtest='com.acme.app.<feature>.**' -Dsurefire.failIfNoSpecifiedTests=false
```
The code map knows Java: `uak map find OrderService`, `uak map users src/main/java/.../common/Money.java`,
`uak map impact ID` (who imports this task's classes).
