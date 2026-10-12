# Business impact

All numbers below are either **measured** on the synthetic demo set (marked *measured*) or come from an
**illustrative model** whose assumptions are stated and editable (marked *assumption*). Nothing here is
company data. Replace the assumptions with real figures to size the benefit for an actual organisation.

## What was measured (24 synthetic receipts, Claude Sonnet 5.5)

| Metric | Result |
|---|---|
| Receipts turned into structured data (vendor, date, total, currency) | 24 / 24 correct, including blurry, crumpled, PDF and foreign-currency bills |
| Bills mapped to the right policy category | 23 / 24 (the miss is a 4-person tasting menu the model called client entertainment, which is arguable) |
| Duplicates caught (exact copy and two re-photographed bills) | 3 / 3, no false alarms |
| Bills left out automatically (expired, personal expense) | 3, each with the policy clause that excluded it |
| Questions the employee had to answer | **5 for 24 receipts** (one date, two approvals/justifications, two business-purpose questions) |
| Policy change (hotel limit 5,000 -> 7,000, one edited sentence) | Reimbursable total moved from INR 23,053 to INR 26,549 with **no code change** |
| Automated tests | 133 passing, 100% statement coverage of the application package |

## Time saved per claim (illustrative model)

*assumption*: preparing one receipt by hand (key in the details, pick a category, look up the limit, check for
duplicates) takes about **4 minutes**. Reviewing an AI-prepared item and answering a question takes about
**30 seconds** per question, plus **3 minutes** to review the claim once.

| | Manual | With the agent |
|---|---|---|
| 24 receipts | 24 x 4 min = **96 min** | ~1 min processing + 5 x 0.5 min + 3 min review = **~7 min** |
| Saved per claim | | **~89 min (about 90%)** |

To size it for a population: `claims per month x minutes saved per claim`. For example, 1,000 claims a month
at ~89 minutes saved is roughly 1,480 hours a month (*assumption-driven, not measured*).

## Value beyond time

- **Fewer policy leaks.** Over-limit bills, expired receipts, personal items and duplicates are caught before
  they reach finance, each with a clause reference, so reviewers stop re-checking the same things.
- **Fewer rejected-and-resubmitted claims.** The employee is told what is reimbursable (and why) *before*
  submitting, including partial amounts such as "INR 5,000 of INR 7,168 for the hotel".
- **Policy changes without a release.** Finance edits a policy document; the next claim uses the new limit.
  No ticket to engineering, no regression risk in rule code.
- **Auditability.** Every decision stores the clause reference, a verbatim quote and the arithmetic.

## Honest limits

- Measured on synthetic bills; real receipts will be messier (handwriting, non-English, long hotel folios).
- One employee profile, one policy pair and static illustrative FX rates. No authentication.
- Policy interpretation works best on clearly numbered clauses; ambiguous prose could be misread, which is why
  every extracted constraint must be backed by a verbatim quote and numbers that appear in that quote.
- LLM cost per claim was not measured. Free-tier models showed rate limits and overload (HTTP 429/503); the
  app caches AI results and degrades to a "please enter manually" path instead of failing.
