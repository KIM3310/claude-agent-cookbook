# Review Guide - claude-agent-cookbook

Updated: 2026-05-30

This repository is archived as a supporting proof. Review it for the reusable pattern, domain evidence, and portfolio relationship; do not treat it as the current flagship unless it is explicitly revived.

## Summary

| Field | Notes |
|---|---|
| Repository | `claude-agent-cookbook` |
| Status | Archived supporting repository |
| Lane | Claude agent implementation enablement |
| Primary reader | AI platform teams, product engineering leads, developer education teams, and model platform partners. |
| Why it exists | Teams adopting Claude need runnable examples, eval habits, and reusable implementation patterns. |
| Stack | Python |

## Open First

1. Read the README archived-status note and relationship to active repositories.
2. Inspect `docs/monetization-playbook.md` for the buyer lane and offer ladder.
3. Use the commands below to confirm the proof surface still has a review path.
4. Check CI workflows before making quality claims.
5. Keep the archived status visible in any portfolio conversation.

## Checks

| Purpose | Command |
|---|---|
| Test suite | `make test` |

## CI

- .github/workflows/architecture-blueprint.yml
- .github/workflows/ci.yml
- .github/workflows/dependency-review.yml
- .github/workflows/repository-health.yml
- .github/workflows/repository-surface.yml
- .github/workflows/secret-scan.yml

## Evidence

- Recipes run with mocked tests
- Cost and API-key boundaries are documented
- Stage-pilot relationship is linked

## Commercial Notes

| Possible offer | Working price assumption | Scope |
|---|---|---|
| Agent recipe workshop | $3k-$12k | Walk a team through tool use, RAG, vision, streaming, and eval recipes. |
| Implementation accelerator | $20k-$75k | Port selected recipes into a customer's internal architecture. |
| Developer education bundle | $2k-$10k/month | License curated recipes, updates, office hours, and internal training material. |

## Boundaries

- Do not imply official vendor ownership
- Keep API pricing and model notes date-stamped when referenced
- Separate educational code from production support commitments

## Useful Metrics

- Workshop bookings
- Recipe completion rate
- Migration leads
- Support hours per cohort
