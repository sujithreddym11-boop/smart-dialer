# Architecture decision record

## Decision 1: Python + SQLite
Choose a single application with separate pacing, safety, allocator and provider responsibilities. SQLite is durable, easy to run and supports atomic reservations across local processes. Its single writer is a throughput bottleneck; a network filesystem is not a substitute for a distributed database.

## Decision 2: Safety over speculative dialing
A statistical estimate is not a guarantee. The safety controller caps outstanding new calls to actual unreserved agents. No direct provider access is given to the pacing engine. Predictive proposals are visible but conservative approvals intentionally sacrifice speculative utilization gains. A real service should enforce the boundary with separate provider credentials and authorization.

## Decision 3: Durable state and idempotency
Reserve both resources and create a call in one transaction. Partial unique indexes backstop the invariant. Mock dispatch writes a unique provider job and event schedule atomically. Real dispatch would instead use a transactional outbox, provider idempotency keys, leases with fencing tokens and reconciliation of ambiguous requests before releasing capacity. Persist event IDs, validate state transitions and use authoritative provider status for contradictory terminal events.

## Scaling
At 100 agents, a single SQLite writer is adequate for this prototype. At 1,000 agents, repeated full scans and writer contention become important: index availability, batch updates and measure lock wait. At 10,000 agents, move to PostgreSQL with row-level locking (FOR UPDATE SKIP LOCKED), partition work by campaign or agent pool, and use bounded queues for provider events. Keep agent ownership globally unique even across campaigns. Monitor queue age, event lag, reservation conflicts, provider rate limits and abandoned calls. At larger scale, isolate hot campaigns and apply backpressure; do not add workers without measuring contention.

## Final question: maximizing utilization while retaining deterministic safety
I would separate statistical forecasting from the hard safety invariant. Predict answer rate, setup latency and expected agent release to prepare the next borrower and schedule work before an agent becomes free. Initiate an agent-bound call only when an actual agent reservation exists. If a provider supports an independently verified, non-abandoning connection mechanism, explore that separately with explicit compliance review; probabilities alone cannot guarantee that simultaneous answers fit available agents. Use provider health, short wrap-up, fast allocation and adaptive pacing to reduce idle time without silently overbooking. If health or state freshness deteriorates, fall back to progressive or stop dialing.

## What I would improve next
Real provider reconciliation and cancellation acknowledgement, reservation leases, a half-open circuit breaker, answer-rate estimation over resolved attempts, explicit pause/re-login, integration tests with actual process termination, and more realistic call-arrival and utilization experiments.
