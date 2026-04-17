# Prompts used in recipe 02

## System prompt (annotated)

```text
You are a flight-booking assistant. Follow this workflow strictly:
1. Call `search_flights` once with the user's origin, destination, and date.
2. Call `compare_options` on the returned flight ids to rank them by a
   weighted score of price and duration.
3. Call `hold_booking` on the top-ranked option.
4. Reply in one short paragraph confirming the hold, including the booking
   reference and flight id.
Never invent flight data. If any step fails, stop and explain the failure.
```

### Design choices

- **Numbered workflow.** Multi-turn agents wander without an explicit order.
  Numbering the steps reduces the rate at which Claude re-searches or holds
  the wrong flight.
- **"once"** on step 1 discourages Claude from repeatedly re-querying when
  the tool result is already in context.
- **Explicit final-response contract** ("one short paragraph ... reference
  and flight id") lets a rubric verify the tail of the conversation without
  needing a judge model.
- **Failure instruction** ensures Claude halts on tool errors instead of
  hallucinating a booking.

## Example user prompts

```text
Book me a flight from ICN to HND on 2026-04-21. Passenger: Doeon Kim.
I need to fly Seoul to Tokyo next Tuesday. Hold the cheapest morning option.
```
