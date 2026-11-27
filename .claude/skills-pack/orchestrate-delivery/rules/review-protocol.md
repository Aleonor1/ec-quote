# Review protocol

`skills/review-code/SKILL.md` walks these in order. A step that does not apply to the project is recorded N/A with the reason. It is not skipped silently.

1. **Ticket, then diff.** Criteria first. Note anything in the diff that no criterion asks for, and anything a criterion needs that the diff does not do.
2. **Evidence.** Gate results with real output, from the commands in `bindings/PROJECT.md` → Gates. A claim with no output is a Major.
3. **Correctness.** The change does what the criteria say, including the boundary and the error the criterion names.
4. **Security.** Authentication, authorization, tenant or account isolation when the project has it, secrets, injection, fail-open defaults. Checked whether or not the diff looks security-relevant.
5. **Failure.** What happens when a dependency is down, a retry arrives, or input is malformed, where the change has such a path.
6. **Tests.** For each criterion, the test would fail without the change. Weakened assertions, skipped cases, and tests that assert a call sequence instead of behaviour are findings.
7. **Boundaries.** Protected paths in `bindings/PROJECT.md` are untouched. Each documentation surface is updated or N/A with a reason. Configuration that a deploy needs comes from the environment.
8. **Grade.** Severity from `rules/severity-and-gates.md`. The verdict is the maximum.
