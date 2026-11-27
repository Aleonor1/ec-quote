# Comment shape

Every inline review comment has three parts, in this order, separated by blank lines.

1. **Severity line.** One of Blocking, Major, Minor, mapped to the host synonyms in `bindings/PROJECT.md` → Severity when the host requires them.
2. **Body.** At most two sentences. The first names the failure. The second names the fix.
3. **Attribution.** The line from `bindings/PROJECT.md` → Repository, then the tags the host's review convention requires. When the project has none, the attribution line is enough.

A Note is never an inline comment. It lives in the review body. A comment that cannot state its failure is not posted.

The review body is scanned, not read as an essay: a verdict line, a findings table, the checks that failed. Prose that restates the diff is omitted.
