---
name: release
description: Prepares a release of what is merged on the base branch and carries it through staging, stopping before production for the human. Works out what changed since the last release, picks the version, writes the changelog and release notes, orders migrations and checks they are safe, lists env vars and secrets the release needs, deploys to staging when the binding allows it, runs the smoke and UI-walk suites against staging, and hands the human a production checklist with a rollback plan. Use after merges, when the human says release, ship to production, or prepare a deploy. Never deploys to production itself.
argument-hint: (none) | <version> | staging-only | notes-only
---

# Release

Argument: **$ARGUMENTS**. Empty: prepare the next release from everything merged since the last one. A version (`1.4.0`): use it. `staging-only`: stop after staging verification. `notes-only`: changelog and notes, no deploy.

A deploy to production is a **reserved decision**, always. This skill does everything up to it, so the human's part is reading one checklist and pressing one button.

## Step 0: Load the binding

`<kit-root>/bindings/PROJECT.md`: Identity, Repository (release note), Gates, UI testing, Reserved decisions, and `## Release` (versioning scheme, version files, tag format, changelog path, migration command and check, staging deploy command and URL, production deploy owner and command, health check, rollback, release branch). A `## Release` still full of placeholders: stop, and send the human to `/onboard-project refresh` or ask for the deploy facts in one round.

## Step 1: What is in this release

1. Find the last release: the latest tag matching the binding's tag format (`git describe --tags --abbrev=0 --match <pattern>`), or the changelog's last entry. None: this is the first release; the range is the whole history up to the base head.
2. List the merged pull requests and commits in the range `<last tag>..origin/<base>`. Read each pull request body (or commit message) for its ticket, its summary, its hand-over, and its documentation rows. Group them: **Features** (epics and stories), **Fixes** (`type: bug` specs, with severity), **Changes** (behaviour changes a user notices), **Internal** (refactors, tooling, tests), **Security**.
3. Collect what the release **needs** from the bodies, the diff, and the specs:
   - migrations: every new migration file or migration function in the range
   - env vars: names added to the env validation file or `.env.example`
   - secrets, accounts, DNS, third-party settings named in any hand-over
   - feature flags introduced, and their intended state
   - data repair scripts from `fix` specs that must run after deploy
4. Check the base is green: the latest CI run on the base head, or the gates run fresh on it. A red base does not get released. Stop and report.

## Step 2: Version

Semantic versioning unless the binding says otherwise:

- **major**: anything a client of the product must change for (a removed or renamed public API field, a breaking import format, a required data migration users must act on)
- **minor**: a feature
- **patch**: only fixes and internal changes

State the reason for the bump in one line. A version given as the argument wins, but if it understates the change (a breaking change in a patch), say so and ask once.

## Step 3: Migrations are safe and ordered

For each migration in the range, read it and answer:

| Question | Unsafe answer |
| --- | --- |
| Can the previous app version still run against the migrated schema? (needed for a rolling deploy and for rollback) | It drops or renames a column the old code reads; it adds a NOT NULL column with no default |
| Is it reversible, or is a backup taken first? | A destructive change with no down path and no backup step |
| How long does it lock? | An index without `CONCURRENTLY` (or the engine's equivalent) on a large table; a full-table rewrite |
| Is it idempotent? | Running it twice fails or duplicates data |
| Order relative to the deploy | It must run before the new code but the binding runs it after, or the reverse |

Run the binding's migration check (a dry run against a fresh local database built from the previous release, then migrated) when it exists. Any unsafe answer is a **Blocking** finding for the release: split the migration (expand, deploy, contract) as a `/fix` or a follow-up story; do not release it as is.

## Step 4: Write the release

On a branch `release/<version>` from `origin/<base>` (or the binding's release branch flow):

- **Changelog**: a new entry at the top of the binding's changelog, in its existing format (Keep a Changelog when there is none): version, date, the groups from Step 1, each line a user-facing sentence with the ticket key. Internal changes collapse to one line.
- **Version files**: bump every file the binding lists (`package.json`, `pyproject.toml`, an `APP_VERSION` constant).
- **Release notes**: `<notes folder>/release-<version>.md`, for the human and their users: what is new in plain words, what changed in behaviour, what to do (if anything).
- **Release checklist**: `<notes folder>/release-<version>-checklist.md` (the template in Step 7).

Run the gates on the release branch. Open a pull request against the base with the changelog, the version bump, and the checklist in the body. The human merges it (or the binding says the release commit goes straight to the base under their standing approval; then commit and push it, nothing else).

After the release pull request is merged: tag the merge commit with the binding's tag format and push the tag, only when the binding's Release → Tagging row says the pack may tag; otherwise put the tag command in the checklist.

## Step 5: Staging

When the binding has a staging deploy command and does not list staging as reserved:

1. Deploy the release commit to staging with that command. Record its output and the deployed version (the health endpoint, a version header, or the page footer).
2. Run migrations on staging the way production will run them, in the order Step 3 decided.
3. Set flags as the release intends.
4. **Verify staging:**
   - the health check returns healthy and the deployed version equals the release version
   - `scripts/ui-walk.mjs --url <staging URL>` with the staging test accounts: no new issue compared with the walk on the previous release (keep `ui-map.json` per release to compare)
   - the smoke spec and the end-to-end suite with `BASE_URL=<staging URL>`, when the suite is safe against staging (the binding says so)
   - each fix in the release: its reproduction, run against staging, no longer shows the symptom
   - each feature's main journey (from its design document) walked once through the screen
5. Any failure: stop. Report the failure with evidence; propose a `/fix`; the release does not go further. Roll staging back with the binding's rollback when the failure leaves staging broken for others.

No staging in the binding: say so plainly in the checklist. The production deploy then carries more risk, and the checklist puts the post-deploy verification first.

## Step 6: Hand over production

Never deploy to production. Give the human the checklist and stop. When the human deploys and tells you, run the **post-deploy verification** on production: health and version; the UI walk **read-only** (anonymous and the least privileged role, GET only, as the walker always is); the smoke spec only if the binding marks it production-safe. Report the result and the first error-tracker events since the deploy when a connector is available.

## Step 7: The checklist (output)

```markdown
# Release <version> · <date>

**Range:** <last tag>..<sha> · <n> pull requests · bump <major|minor|patch> because <reason>
**Base CI:** green on <sha>   **Staging:** <verified on <URL> at <time> | not available>

## Before deploying
- [ ] Secrets/env vars set in production: <NAME (purpose, from which hand-over)> | none
- [ ] Third-party setup: <webhook URLs, DNS, accounts> | none
- [ ] Backup taken: <command> (required: <yes, because migration X is destructive | no>)

## Deploy
1. <migration command, if migrations run before the code> · expected: <tables/columns>
2. <production deploy command or button, owner: <who>>
3. <flags to set, in order> | none
4. <data repair scripts from fixes, with their expected row counts> | none

## Verify (tell me when deployed, I run these)
- [ ] Health: <URL> returns healthy, version <version>
- [ ] UI walk read-only on <prod URL>: no new issue vs staging
- [ ] <the one journey per feature to click through by hand>
- [ ] Error tracker: no new error group in the first 30 minutes

## Roll back if
<the signals: health red, error rate above X, a journey broken>
Rollback: <the binding's rollback command> · <migration rollback or "forward-fix only, because <reason>">

## In this release
<the changelog entry>
```

## Anti-patterns

- **Deploying to production,** even when asked inside a standing approval. Production deploys need the human's words for that deploy, every time; give them the checklist.
- **Releasing a red base.**
- **A destructive migration in the same deploy as the code that stops using the column.** Expand, deploy, contract.
- **A changelog copied from commit subjects.** Users read it; write sentences they understand.
- **Running the UI walk with write actions against production,** or seeding production.
- **Forgetting the hand-overs:** a secret named in a merged pull request that nobody set is an outage at deploy time.
