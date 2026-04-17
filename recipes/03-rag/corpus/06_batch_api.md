# Message Batches API

The Message Batches API runs many independent prompts asynchronously at
approximately half the per-token price of synchronous requests. It is the
recommended surface for offline evaluation, bulk data labeling, and backfill
jobs where latency is not critical.

You submit a batch by POSTing to the `/v1/messages/batches` endpoint with up
to 10,000 requests or 100MB of input. Each request carries a `custom_id` you
can use to correlate outputs. The batch completes asynchronously within a
24-hour SLO; poll the batch status endpoint or use the streaming results
endpoint to retrieve outputs as they finish.
