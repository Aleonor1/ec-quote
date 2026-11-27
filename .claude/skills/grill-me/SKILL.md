---
name: grill-me
description: Interviews the human about a loose idea until nothing is left unstated, in rounds, each round asking only the questions whose prerequisites were just answered. Writes no files and leaves nothing behind; the result is an idea the human can commit to, and a conversation that create-spec or rnd can continue from without a second interrogation. Use when the human says "grill me", wants to pressure-test an idea, a plan, or a design before specifying it, or is not sure what they want yet. Do not use to write a spec (that is create-spec), to design a feature (that is rnd), or on top of a plan an agent wrote.
argument-hint: <the idea, in one or two sentences> | (empty: ask for it)
---

# Grill me

The idea to grill is: **$ARGUMENTS**

If it is empty, ask the human for the idea in one or two sentences and stop.

You are the senior colleague who, before anything is built, asks the questions the human has not asked themselves. Every question you ask is one they will otherwise answer by accident, later, in code. You write nothing: no file, no plan, no notes folder. When the interview ends, the human knows what they want, and the same conversation goes straight to `/create-spec` or `/rnd`.

## Step 0: Ground

Read `<kit-root>/bindings/PROJECT.md` → Identity, Definition of Ready, Reserved decisions, and `## Skills pack` → Research and design (autonomy limits, cost ceiling). Read the orientation document the binding names when it exists, so questions are asked against the real codebase, not a generic one. Do not run `project-overview`; a missing map only means you ask what the code does instead of assuming.

## Step 1: The frontier

Keep, in your head, a **frontier**: every open question whose prerequisites are already answered. Seed it from the idea with the dimensions below, keeping only the ones that apply:

| Dimension | The question behind it |
| --- | --- |
| Outcome | What can someone do afterwards that they cannot now; how will you know it worked |
| Who | Which users and roles; who must be refused; who runs it day to day |
| The first journey | The one path, start to finish, that must work on day one |
| Edges | Empty, wrong input, partial, concurrent, offline, too much, the dependency down |
| Data | What is new, what changes, what is kept how long, what must be migrated |
| Boundaries | What is explicitly out; what is "later"; what looks related but is a different feature |
| Dependencies | Other systems, secrets, accounts, people, and which of them do not exist yet |
| Constraints | Money, deadline, languages, devices, compliance, the architecture rules doc |
| Failure | The way this goes wrong that would be embarrassing; the way it goes wrong silently |
| Reversibility | What cannot be undone once shipped (a migration, a sent email, a charged card) |

A question enters the frontier only when the answers so far make it askable. "How should refunds work?" waits until "are there payments?" is answered.

## Step 2: Ask in rounds

Each round:

1. Ask **every question currently on the frontier**, numbered, shortest first. Not one at a time by default (the human may say "one at a time"; then one per turn). Not more than seven; when the frontier is larger, ask the seven whose answers unlock the most, and say how many wait.
2. For each, say in half a sentence why it matters when that is not obvious.
3. Offer your own best guess when you have one, marked as a guess, so the human can say "yes" instead of composing an answer.
4. Wait for the answers. Then update the frontier: an answer closes its question, often opens two more, and sometimes invalidates a question already asked (say so, drop it).

Rules of the interview:

- **The human owns the scope.** "Out of scope", "later", and "I don't know" are complete answers. Record them as such and move on; "I don't know" on a question that decides the design becomes a line in the final summary, never a guess.
- **Push back when an answer contradicts an earlier one**, quoting both. The point is a consistent idea, not a long list of answers.
- **Flag scope drift** when an answer grows the idea: "that is a second feature; keep it, or park it under later?"
- **Do not grill the ungrillable.** How a screen should feel, which of two layouts reads better, whether a name sounds right: nobody answers these well in words. Say so and offer a quick throwaway (a sketch in the reply, a ten-line mock, two example strings) so the human can point at one. Then record the answer in one line.
- **Ask against the code.** When the answer could be read from the repository (does this table exist, is there an adapter for that provider), read it instead of asking, and tell the human what you found.
- **A reserved decision stays the human's.** Anything in the binding's Reserved decisions or Autonomy limits is asked as a decision with options, never answered by your guess.
- **Large idea, small pieces.** When the frontier keeps growing past twenty questions after two rounds, stop and propose a split into pieces with a one-line goal each; then grill the first piece. One conversation per piece.

## Step 3: End when the frontier is empty

The interview ends when every branch has been visited and no assumption is left unstated, or when the human says stop. Then give, in one message, no file:

```markdown
## Grilled: <idea in one line>

**Outcome:** <one sentence>
**In:** <list>  **Later:** <list>  **Out:** <list>
**Decided:** <each answer that shapes the design, one line each, the human's words where they matter>
**Unknown:** <each "I don't know" that decides something, and what would settle it> | (None)
**Reserved for you:** <decisions still open that only you can take> | (None)
**Risks you named:** <list> | (None)

Next: `/create-spec` for one small change, or `/rnd` for a whole feature, in this conversation: both read the answers above and will not ask them again.
```

That is the only output. Nothing is written to disk; the next skill in this conversation reads the answers from the transcript.

## Anti-patterns

- **One question per round by default.** The frontier is the round; the human sets the pace, not the skill.
- **Questions with no prerequisite answered.** Asking about refund edge cases before knowing whether money moves at all.
- **Guessing an "I don't know".**
- **Grilling taste.** Twelve questions about a layout that a sketch would have settled.
- **Asking what the code already says.**
- **Writing a plan, a spec, or a notes file.** This skill leaves no workspace behind; `create-spec` and `rnd` write.
- **Starting on top of an agent-written plan.** The plan's assumptions are then defended instead of questioned; grill the idea, then plan.
