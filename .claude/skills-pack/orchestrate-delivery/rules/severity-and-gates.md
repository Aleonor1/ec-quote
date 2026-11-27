# Severity and gates

Reviews of documents, code, and acceptance use the same four severities and the same three verdicts.

## Severities

| Severity | Definition | Effect |
| --- | --- | --- |
| **Blocking** | Ships incorrect, insecure, or unrecoverable behaviour, or a one-way door taken without a recorded decision | Verdict is BLOCK. Work does not proceed. |
| **Major** | A real defect or a real risk, with a bounded workaround or a later fix that is genuinely possible | Verdict is REVISE. Must be answered. |
| **Minor** | Correctness-neutral. Naming, duplication, a missing test for a low-risk path | Fix now or file it. Does not gate. |
| **Note** | Context, an alternative, or praise. No action implied | Never gates. |

Security boundary crossings, data-loss paths, tenant-isolation gaps, fail-open authorization, and silent failures are **Blocking** by definition. Do not invent other severity words. A host tool's synonyms are the ones in `bindings/PROJECT.md` → Severity, and they map onto these four.

## Verdicts

| Verdict | Meaning | Who clears it |
| --- | --- | --- |
| **PASS** | No Blocking, no Major. Minors listed | — |
| **REVISE** | No Blocking; one or more Major, each with a named condition | the author, by answering every condition |
| **BLOCK** | At least one Blocking finding | the author and a human decision |

A REVISE condition is cleared by answering it: fixing it, or recording why it is acceptable with the trade-off stated. Dropping it silently is not clearing it.

## A finding is falsifiable

Every finding names the severity, the location, what is wrong, the concrete failure it produces, and what would make it right. A finding that cannot state its failure is a Note.

## The merge gate

A pull request is ready to merge only when, on its current head, every required check has passed, no review still requests changes, every review thread is resolved, the code-review, QA, and UI-test verdicts are PASS (UI test may be N/A with its reason), and `rules/test-quality-gate.md` holds. A check still running is not green.

The one exception is a red the pull request did not cause: a failure that reproduces on the base without this change, or an environment failure. It is named, with the evidence. When it is quick to fix and no other open pull request already fixes it, it is fixed here.

## Anti-patterns

- Approving with a Blocking finding open because a follow-up ticket will fix it.
- A review body with findings and no verdict, or a verdict with no findings enumerated.
- Re-raising a decision the project has already recorded, with its reason. That is a Note, unless the diff changes the exposure.
