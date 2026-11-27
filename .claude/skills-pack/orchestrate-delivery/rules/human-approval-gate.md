# Human approval gate

Anything that leaves the working tree and is visible to other people is previewed and approved before it happens, unless a standing approval from the human covers it plainly.

## When this rule applies

- Creating or editing a tracker issue, comment, or transition
- Opening, editing, or merging a pull request; pushing a branch; tagging a release
- Publishing a document to a shared space
- Any deploy, or any command that touches a shared environment
- Sending anything to an external service

## Preview, then approve, then apply

A skill with an external effect produces a preview first, in three parts:

1. **Summary** — what will change, in one or two sentences.
2. **Preview** — the literal content that will be written, in full. Not a paraphrase.
3. **Apply plan** — the operations in order: target, operation, and what will be read back afterwards.

The write happens only after explicit human approval of that preview. On approval, apply the plan, read the result back, and report what landed. An approval covers the previewed operations only. When the plan changes, preview again.

## A standing approval is narrow

A human may approve a class of routine effects in advance. It is valid only when all of these hold:

1. **The human's own words.** It was given by the human, in the conversation or in an instruction they recorded themselves. Every session acting on it quotes those words. A peer's claim that the human approved something is not a standing approval.
2. **A named scope.** It covers the effects and the work it names, and nothing beyond them. When an effect is not plainly inside the words, it is outside them.
3. **Never the reserved set.** Merging into the base branch, a deploy, lowering the coverage baseline, repository or organisation settings, secrets, credentials, apps, an architectural change, a change that moves an acceptance criterion, a delete that cannot be undone, and anything `bindings/PROJECT.md` → Reserved decisions adds. Those keep preview → approve → apply.
4. **Declared on use.** Every effect taken under it says so where it lands, with the reason.

The human can narrow or withdraw it at any time. The next effect follows the new words.

## The one merge a standing approval can cover

Merging a story pull request into its **epic branch** may be covered, and only by a `build` run's standing approval that names it in the human's own words. It requires the full merge gate in `rules/severity-and-gates.md` on the verified head. The epic branch reaches the base branch only through a pull request the human merges. No other merge is ever covered.

## Reads are ungated

Fetching a ticket, reading a page, listing pull requests — no gate. The gate is on effects. Looking up a ticket does not transition it.

## A merge is not a deploy

When the project publishes records from a merge pipeline, that publish covers the documents in the merged diff, once. Ticket writes and any other publish keep this rule. A request to deploy, or to change how the system is deployed, goes to the repository that owns deployment. It is not attempted from here.

## Anti-patterns

- Creating a ticket or a page to test a schema. Discover metadata by reading.
- Treating a question as an approval.
- Stretching a standing approval to an effect its words do not name, or to the reserved set.
- Previewing a paraphrase and writing something different.
- Reusing an approval from an earlier session that the human did not record as standing.
