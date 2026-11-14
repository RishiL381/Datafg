# Labeling guide: 5 complaint aspects

File: `label_template.csv` (local only, gitignored: it has review text). One row = one 1-2 star review.
Each aspect column is **1** if the review complains about it, **0** if not. A review can have several 1s, or none
(for example, it only complains about food quality or a misdiagnosis).

Pre-labels come from an LLM (Claude in this session) that read each review. **Your job:** fix any wrong 0/1, then put
`1` in `checked`. Use `notes` for anything odd. Rows with `checked` empty are not used for training or testing.

| Aspect | Mark 1 when the reviewer complains about... | Not this aspect |
|---|---|---|
| `wait_time` | long waits in line, lobby, drive-thru, or on hold; slow service; prescription not ready / slow refills; long delay to get an appointment, referral, or results; appointments cancelled or rescheduled | merely mentioning a time ("I came at 3pm") |
| `cost` | prices too high, overcharging, wrong or surprise bills, insurance or coverage problems, copays, fees, refunds refused | "free" or "cheap" as praise |
| `staff` | rude, dismissive, unhelpful, unprofessional, or incompetent staff or providers; poor communication; disrespect or discrimination | product or food quality; building issues |
| `language_access` | language barriers: no interpreter, staff can't or won't speak the customer's language, being mistreated over language or accent | a review simply written in Spanish/Chinese with no language complaint |
| `hours_availability` | closed when it should be open, posted/Google hours wrong, closes early, lunch closures, limited hours, service unavailable (urgent care not taking patients), phone never answered or can't reach anyone | waiting on hold for a long time (that is `wait_time`; if both, mark both) |

Edge rules
- Long hold on the phone = `wait_time`. Phone never answered at all = `hours_availability`.
- "Out of stock" medication: mark `wait_time` only if the reviewer complains about the delay it caused.
- Security guards treating customers badly = `staff`.
- Judge what the reviewer complains about, not every topic they mention.
