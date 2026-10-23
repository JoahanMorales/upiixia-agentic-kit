# Stack · Spring Boot service (Java)

Setup for the first task and structure reference. Conventions: the `stack-spring-boot` skill.

## Structure (package by feature)

```text
pom.xml · mvnw · .mvn/                               # owner: setup; dependencies go through it
src/main/java/<base>/Application.java               # owner: setup; nobody edits it after
src/main/java/<base>/common/                        # owner: setup or the contract task: errors, shared types, config
src/main/java/<base>/<feature>/                     # one task: <F>Controller, <F>Service, <F>Repository, dto/
src/test/java/<base>/<feature>/                     # its tests (same package: no imports needed)
src/main/resources/application.yml                  # owner: setup; a feature adds keys under app.<feature>
src/main/resources/db/migration/V<yyyyMMddHHmm>__<feature>.sql   # Flyway: shared resource, one OWNERS row per task
api/openapi.yaml                                    # the contract task; others read it, ask to change it
```
A task reserves `src/main/java/<base>/<feature>/` and `src/test/java/<base>/<feature>/`. Spring finds components by
package scan from `Application`, so a feature never edits shared wiring.

## Setup (~5 min)

Generate the project with Spring Initializr (current Spring Boot and Java versions, no hand-pinned numbers):

```bash
curl -s https://start.spring.io/starter.zip -d type=maven-project -d javaVersion=21 \
  -d groupId=com.acme -d artifactId=app -d dependencies=web,validation,actuator,data-jpa,flyway,h2,postgresql,testcontainers \
  -o app.zip && unzip -q app.zip && rm app.zip && chmod +x mvnw
```

`src/main/resources/application.yml`:

```yaml
server:
  port: ${UAK_PORT:8080}        # each worktree gets its own port from .uak-env
spring:
  flyway:
    locations: classpath:db/migration
app: {}                         # features add app.<feature>.* keys
```

`src/main/java/<base>/common/ApiErrors.java`: one `@RestControllerAdvice` that turns validation and not-found
errors into `ProblemDetail`, so every feature answers errors the same way.

Sprint: H2 in memory (`spring.datasource.url=jdbc:h2:mem:app`). Marathon: PostgreSQL in production and
Testcontainers in tests (Docker needed on every machine that runs Verify, and in the merge gate).

## Migrations without collisions
Flyway versions are global: two tasks writing `V3__` collide at merge. Use timestamps, one file per task:
`V202610221530__orders.sql`. The kit treats `db/migration/` as a shared resource: each task's file needs an
`OWNERS.md` row (`| src/main/resources/db/migration/V202610221530__orders.sql | HACK-012 |`).

## Product smoke

```bash
bash .uak/bin/uak init-smoke --command "./mvnw -q -B verify"
```
(sprint without Docker: `./mvnw -q -B test`).

## Verify per task

```bash
bash .uak/bin/q ./mvnw -q -B test -Dtest='<base-package>.<feature>.**' -Dsurefire.failIfNoSpecifiedTests=false
```

## Run
`./mvnw -q spring-boot:run -Dspring-boot.run.arguments=--server.port=$UAK_PORT`
