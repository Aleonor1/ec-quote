---
name: security-audit
description: Audits the code for security defects the way an attacker and a careful reviewer would, and turns every confirmed finding into a ready fix spec. Covers secrets in code and history, vulnerable dependencies, authentication and session handling, authorization and tenant isolation (fail-open checks, IDOR), injection, XSS, CSRF, SSRF, file upload, webhooks and their signatures, payments, rate limiting, security headers, logging of personal data, and GDPR basics. Runs automated scanners first, then reads the code, then proves each finding against the local stack. Use on a whole repository before a launch or periodically, on a pull request's diff, or on a named area. Never attacks anything but the local stack, and never writes exploit code beyond a minimal local proof.
argument-hint: (none) = whole repo | diff <base> | <path or area> | pr <N>
---

# Security audit

Scope: **$ARGUMENTS**. Empty: the whole repository. `diff <base>` or `pr <N>`: only what changed, plus what it calls. A path or an area name ("payments", "auth"): that area and its entry points.

Every finding is **proven or dropped**. A scanner hit or a suspicious line is a lead, not a finding, until it is shown to produce the failure on the local stack or by a unit test.

Boundaries: probes run only against the local stack from the binding (or a test environment the human names in this conversation). No scanning of production, of third parties, or of anything the project does not own. Proofs are the minimum that shows the defect (a request that reads another tenant's record, a test that renders a script tag); never a weaponized exploit.

## Step 0: Load the binding and map the attack surface

Read `<kit-root>/bindings/PROJECT.md` (Gates, UI testing for roles and accounts, Shared environment, `## Skills pack → Security`: scanners available, data classification, compliance notes) and the orientation document (`ARCHITECTURE.md`).

Write the attack surface before reading for bugs, in `<notes folder>/security/<date>/surface.md`:

- **Entry points**: every route (method, path, auth required, roles allowed), every webhook, every background job that reads external input, every file upload, every place user HTML or markdown is rendered.
- **Trust boundaries**: browser to API, API to database, API to each external service, tenant to tenant, role to role.
- **Assets**: personal data (which fields), credentials and tokens, payment data, files, admin functions.
- **Identity**: how a user is authenticated (session, JWT, OAuth), where the session lives, how roles and tenant are resolved per request.

## Step 1: Automated scanners

Run what applies, record versions and outputs. Install a missing tool in a scratch location, never into the project's dependencies.

| Area | Tools |
| --- | --- |
| Secrets in the tree and the history | `gitleaks detect --redact` (whole history), or `trufflehog git file://. --only-verified`; fallback: a ripgrep for key patterns (`AKIA`, `sk_live_`, `-----BEGIN`, `xox[bp]-`, `ghp_`, password assignments) |
| Dependencies | `npm audit --omit=dev --json` / `pnpm audit`, `pip-audit`, `govulncheck ./...`, `osv-scanner -r .` |
| Static analysis | `semgrep --config p/owasp-top-ten --config p/secrets` (plus the language pack), `bandit -r` for Python, eslint security plugins when configured |
| Containers and IaC | `trivy fs .` when Dockerfiles or IaC exist |
| Headers and TLS (local stack) | the response headers of the app URL: CSP, HSTS (for HTTPS), X-Content-Type-Options, frame-ancestors, cookie flags |

Triage each hit: reachable from an entry point? exploitable with the project's configuration? A dependency CVE in a function the project never calls is a Minor (update in a batch); one in a reachable path is graded like any finding.

A **verified secret** in the tree or the history is reported to the human **at once**, before anything else: it must be rotated by its owner (a reserved action), and removing it from git history alone does not make it safe.

## Step 2: Read the code, threat by threat

Walk the checklist against the attack surface. For each item, look at every entry point it applies to, not a sample.

**Authorization (most real breaches)**
- Every route checks authentication and the role, server-side, in one consistent place. Find routes that do not (compare the route list with the middleware or decorator coverage).
- Every read and write of a record checks that it belongs to the caller's tenant or user (IDOR). Look for `findById(req.params.id)` with no owner filter.
- Checks fail **closed**: an exception, a missing role, an unknown value denies.
- Mass assignment: request bodies cannot set `role`, `tenantId`, `isAdmin`, `price`, `status`.
- Admin and internal endpoints are not reachable without the admin role, including through the API directly (not only hidden in the UI).

**Authentication and sessions**
- Passwords hashed with a slow hash (argon2, bcrypt, scrypt); no plain or fast hash.
- Login, reset, and OTP endpoints are rate limited; reset tokens are single use, expire, and are not logged.
- Session cookies `HttpOnly`, `Secure`, `SameSite`; JWTs verified with a fixed algorithm and an expiry; logout invalidates server-side when sessions are server-side.
- OAuth: `state` checked, redirect URIs allowlisted.

**Injection and output**
- SQL/NoSQL: no string-built queries with input; ORMs' raw query escapes checked.
- Command execution, template rendering, `eval`, deserialization of untrusted input.
- XSS: every place user content reaches HTML (`dangerouslySetInnerHTML`, `v-html`, `innerHTML`, markdown renderers, email templates, PDF generators). A CSP that would contain it.
- Path traversal in any file path built from input; file uploads checked for type by content, size limited, stored outside the web root, served with a safe content type.
- SSRF: any server-side fetch of a URL the user controls (webhook URLs, image imports, link previews) is restricted from internal addresses.

**Integrations and money**
- Webhooks verify the provider's signature with a constant-time compare and reject replays (timestamp tolerance, idempotency key).
- Payment amounts and product prices come from the server, never from the client; order state changes only from the verified webhook, not from the redirect page.
- Outbound calls have timeouts; failures do not fail open.

**Data protection**
- Logs and error reports do not contain passwords, tokens, full card data, or unnecessary personal data.
- Personal data: what is stored, why, how long; export and delete paths exist when the product serves EU users (GDPR Articles 15, 17); backups and analytics included.
- Secrets come from env, are validated at startup, and are never sent to the client bundle (`NEXT_PUBLIC_`, `VITE_` prefixes checked).

**Platform**
- CORS: no wildcard with credentials; origins allowlisted.
- CSRF protection for cookie-authenticated state-changing requests.
- Rate limits on expensive and enumeration-prone endpoints.
- Error responses do not leak stack traces or SQL in production mode.
- Debug routes, admin consoles, and source maps not exposed in production builds.

## Step 3: Prove each finding

For each lead, on the local stack (seeded, with the binding's test accounts) or in a unit test:

- write the minimal request or test that shows the failure (staff user B reads tenant A's invoice: `GET /api/invoices/<A's id>` with B's session returns 200 and the body)
- record request, response, and why it is a defect
- a lead that does not reproduce is dropped, or kept as a Note with the reason when the code is fragile but not exploitable now

## Step 4: Grade

`rules/severity-and-gates.md`, with security specifics:

| Severity | Examples |
| --- | --- |
| **Blocking** | verified secret exposed; authentication bypass; cross-tenant or cross-user data access; injection reachable from an entry point; payment amount from the client; unsigned webhook that changes state; fail-open authorization |
| **Major** | stored XSS behind login; missing rate limit on login or reset; CSRF on a state change; SSRF to internal addresses; reachable vulnerable dependency; personal data in logs |
| **Minor** | missing security header with no current exploit; unreachable vulnerable dependency; verbose errors in development only |
| **Note** | hardening suggestions |

## Step 5: Turn findings into fixes

For every Blocking and Major: write a fix spec in the binding's spec folder the way the `fix` skill does (`type: bug`, `severity`, the proof as the reproduction, the root cause, and the regression test as the first acceptance criterion: the proof request must fail closed after the fix). Group findings with the same cause (one missing ownership check in a shared repository helper is one spec, listing every route it fixes). Minors go into one hardening spec. Do not ship them from here: the human chooses `/fix <KEY>` or `/ship <keys>`.

Write the report to `<notes folder>/security/<date>/report.md` and keep it out of the repository and out of pull requests unless the human asks: it is a map for an attacker until the fixes ship.

## Output

```markdown
## Security audit: <scope> · <date> · head <sha>

| Severity | Count | Specs written |
| --- | --- | --- |
| Blocking | <n> | <keys> |
| Major | <n> | <keys> |
| Minor | <n> | <key of the hardening spec> |

**Act now:** <verified secrets to rotate, by owner> | (None)
**Scanners:** <tool: version, hits, triaged as> per line
**Attack surface:** <n routes (n unauthenticated), n webhooks, n upload points, roles>

| # | Severity | Where | Finding | Proof | Spec |
| --- | --- | --- | --- | --- | --- |

**Not checked:** <areas out of scope or without a local way to probe, and why>
**Report:** <path> (kept out of the repository)
Next: `/fix <KEY>` for each Blocking, highest first.
```

## Anti-patterns

- Reporting scanner output as findings without triage or proof.
- Probing anything but the local stack or a test environment the human named.
- Checking authorization in the UI (a hidden button) instead of on the server.
- A sample of routes instead of all of them for the authorization pass.
- Rewriting git history to remove a secret and calling it fixed without rotation.
- Committing the audit report to the repository while the findings are open.
- Fixing in the audit session: findings become specs and go through `fix`, so someone independent verifies them.
