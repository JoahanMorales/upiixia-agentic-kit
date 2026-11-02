---
name: test-first
description: Use before writing code for any feature, bug fix or behavior change. Test names first, see the red on an assertion (uak red), Fakes instead of mocks, tests only grow, tests by layer.
---

# Test-first, pragmatic, for agents

The test is the shortest exact way to say what the task wants: what goes in, what must come out, what must NOT
happen. It runs; it does not get interpreted. Agents optimize toward green, so this process closes the three short
cuts to green: a test written after the code (passes by construction), a test that only checks "the mock was called",
and a test edited until it passes.

Kept from classic TDD: see the red, implement the minimum, see the green. Dropped: one tiny test per cycle and a
mandatory refactor each lap. One block of behavior per cycle costs fewer round trips.

## The cycle (the kit checks every step)

1. **Names first.** The task's `Tests:` line lists its behaviors as test names. They are the spec, shorter than a
   paragraph of prompt. Example, `PlaceOrder`:
   - `places_order_when_stock_is_enough`
   - `rejects_order_when_stock_is_short`
   - `does_not_charge_when_stock_check_fails`
   - `charges_once_when_the_request_is_retried`
   No `Tests:` line? Write the list first, in the test file. `uak done` fails when a listed name is missing.
2. **Red on the right cause.** Write the tests, then the stub (the function or route with its signature, returning
   a wrong value). Run `bash .uak/bin/uak red ID`: it must fail on an assertion. A red on "module not found", a
   missing file, no tests collected or a syntax error says nothing: `uak red` refuses it. A test that passes before
   the code tests nothing new: `uak red` refuses that too.
3. **Green, minimal.** Implement until the same command passes: `bash .uak/bin/q <Verify>`.
4. **Refactor only on green**, when it buys something. The tests guard the outside while the inside changes.

`uak done` checks the red was recorded on this branch before the tip. Nothing a test can show first (docs, config,
pure styling)? `done ID ... --no-red "why"`; the reviewer reads the why.

## Tests only grow

An existing test is a spec, not a suggestion. Never change an assertion to make it pass, never add `skip`, `xfail`,
`.only`, `.todo`, never delete a test or take it out of the run from the runner's config. `uak done` refuses all of
these (a moved or re-indented line is fine). If an existing test looks wrong, do not touch it: say so,
`uak msg human "ID · file:test · why it is wrong"`. A human allows the change: `UAK_HUMAN=NAME uak allow ID --tests --reason TEXT`.

## Fakes, not mocks

A mock answers "was I called?". A Fake has behavior and state you can assert on, so the code cannot cheat it.

- Every external dependency (payments, mail, clock, randomness, an HTTP API) sits behind a small interface with a Fake
  in the tests: `FakePayments` records charges and can be told to decline; `FrozenClock` returns one instant.
- Assert on outcomes: the order exists, `fake_payments.charges == []`, the response body. Not on
  `assert_called_once` alone: `uak done` warns when a test's new assertions only check calls.
- Never mock the database to get past a failure. Never mock the code under test.

## Bugs: the regression test comes first

A bug task (`Type: bug`) always needs its red: the test that reproduces the report, failing before the fix. If you
cannot write a test that fails before the fix, you have not understood the bug yet; a fix without a reproduction is a
guess. Example: "a coupon expired one second ago was accepted" → `FrozenClock` at the exact second, no network, no
sleep.

## Tests by layer, each with its job

| Layer | What | How fast | When it runs |
|---|---|---|---|
| Unit | domain actions, value objects, pure functions | ms, no DB, no network | every loop (`q`) |
| Integration | repositories, queries, migrations | seconds | before push |
| Contract | each endpoint's status and exact response shape; consumer-driven contracts between services | seconds | before push, in CI |
| Architecture | layer rules: the domain imports no HTTP, no ORM | ms | every loop |
| E2E | the critical journeys, in a real browser | minutes | CI and before done on UI |

Run the fast ones while iterating; the slow ones at the end. Output stays short: `pytest -q --tb=short -x`.

**Integration runs on the same database engine as production**, in a database of its own (a container), never the
development one. SQLite in memory accepts queries Postgres rejects (identifiers, NULL ordering, collations): green
here, red in production.

**Architecture tests are red first too.** A deterministic tool checks the layers for free, every run:
`import-linter` (Python, contracts in `.importlinter`), `dependency-cruiser` or ArchUnitTS (TypeScript),
ArchUnit (Java), `go-arch-lint` or a test over `go list -deps` (Go). An HTTP import inside `PlaceOrder` turns the
suite red with a clear message; no reviewer has to notice it.

## Services and contracts

Treat each service (or module with a contract) as something other teams consume:
- Its contract is a test: the provider's tests check the exact shape consumers rely on; a consumer tests against the
  provider's contract, not a hand-made mock of it. Changing it is `uak msg impact:ID --kind contract` first.
- One reason to change per module; dependencies point inward (domain ← application ← adapters).
- Each service deploys on its own, owns its data, and tolerates the others failing: timeouts, retries with backoff,
  idempotency keys, all tested with Fakes that fail on purpose.

## The professional (The Clean Coder, applied to agents)

- **Done means done**: tests green, criteria met, evidence attached. Never "done except the tests".
- **Say no, with the reason and an alternative**, instead of "I'll try": a criterion you cannot meet goes to
  `uak decision`, not to a weaker test.
- **Do no harm**: you do not ship code you did not see work; QA should find nothing.
- **Small steps, kept green**: commit on every green criterion; never leave the branch red.
- **Estimate honestly**: a task that grows past its estimate is split or reported, not rushed.

## Reviewing (read the tests first)

Read the tests before the code. If they describe the behavior well, the code almost reviews itself. Reject when: a
listed behavior has no test, an assertion is weak (`is not None`, `toBeTruthy` on an object), a test only checks
mock calls, or the red in the done note is not on an assertion.
