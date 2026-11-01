# Lost-response refund regression pack — private simulation

**A narrow, original proof-of-behavior fixture, not a production payment system or an Adyen fix.** No real funds, accounts, secrets, model calls, Docker, network requests, third-party dependencies, or system configuration changes. Python 3.9+ standard library only. Databases are created in temporary directories and removed on exit.

## Run

```sh
cd examples/refund-regression  # from the virtual-trade-lab repository root
python -m unittest -v
python demo.py
```

The positive-control baseline makes two unkeyed submissions for one intended 2000-minor-unit partial refund after the first response disappears: two provider refunds settle, totaling 4000. The durable variant records intent before sending, loses its response, restarts both databases, sees a stale empty read, and retries with its persisted operation key: one provider refund settles, totaling 2000. The state progresses **unknown → accepted → succeeded**; accepted is not success. A delayed failure is separately tested.

`demo-output.json` and `test-results.txt` are captured local results, not live-provider evidence.

## Three identities, not one

- **Logical operation:** caller-assigned business intent, e.g. `return-line-7`. Its durable key is `logical:return-line-7` in this single-merchant fixture. Reuse the operation ID for retries. A legitimately different equal-amount refund needs a different operation ID.
- **Attempt:** each outbound attempt gets a local database ID; it is not the idempotency key.
- **Provider refund:** assigned by the fake provider, learned from a response or event; at most one per keyed operation.

Payment and amount are checked for consistency but are **not hashed together to identify intent**. Changing a payload under an existing operation ID is rejected. A failed operation does not silently create a replacement; any new authorized business intent must be explicit. Merchant/account/currency namespaces are out of scope and must be designed before real integration.

## What is grounded in a real report

[Adyen/adyen-mcp issue #149](https://github.com/Adyen/adyen-mcp/issues/149), filed by terminalstate, reports a lost response after refund acceptance and repeat partial refunds in a local fake. Its [maintainer response](https://github.com/Adyen/adyen-mcp/issues/149#issuecomment-6083156969) welcomes a PR review but deprioritizes feature work while a remote MCP is developed. The page was read on 2026-11-01 and displayed Open (web cache, not an independently fresh API status check). This is neither a budget commitment nor customer demand evidence.

Prior art: terminalstate's [double-take README](https://github.com/terminalstate/double-take#readme) and [WRITEUP](https://github.com/terminalstate/double-take/blob/main/WRITEUP.md) already demonstrate synthetic lost-response failures and recommend stable business-operation keys and a ledger. The write-up explicitly excludes eventual consistency. No novelty is claimed for those ideas. This small fixture independently implements durable restart behavior, delayed reads, terminal event ordering, and identity distinctions. No upstream code was copied, installed, or executed. Our delayed-read/event model is a **declared extension of the simulation**, not evidence of actual Adyen consistency semantics.

## Explicit model assumptions and boundaries

1. One synthetic merchant, one currency, positive integer minor units. Fake captured funds are fixed; only terminal successes count toward refunded funds.
2. Fake submissions persist an accepted refund before the response can disappear. Acceptance does not reserve funds: oversubscribed requests may be accepted, then fail at serialized settlement. No successful refund can take the settled total beyond captured funds. This is a chosen toy settlement rule, not a complete specification of Adyen's reservation/race behavior.
3. Provider idempotency keys are durably unique and retained forever in this fixture. A retry with the same key and payload replays its refund; changed payload is rejected. **A client ledger alone does not provide exactly-once external effects.** Expired provider keys, multi-region differences, lost local storage, and caller-generated new IDs for the same intent are outside the guarantee.
4. Events are normalized fixture objects, assumed authentic, with stable provider refund ID, operation key, payment, amount, and a per-refund version: accepted=1, immutable succeeded/failed=2. Real webhook schemas, authentication, operation correlation, and ordering must be validated separately. This is not an Adyen webhook parser.
5. Events can arrive duplicated or out of order. Terminal events may arrive before accepted. Lower-version accepted events cannot regress terminal state. Conflicting terminal outcomes, changed duplicate-event payloads, unknown keys, or mismatched identities raise an error and roll back; operational quarantine/review queues are not implemented.
6. Empty delayed reads do not prove no refund exists. Unknown stays unknown without positive evidence. Accepted remains pending until terminal evidence. Eventual outcome requires delivery of a terminal event or a visible authoritative read; no liveness is promised if evidence never arrives.
7. Restart tests close and reopen both SQLite files. Fault injection covers intent persisted before send, response lost after acceptance, and process-level interruption before local receipt. It does not simulate power loss, filesystem corruption, a killed operating-system process, distributed workers, or all concurrent interleavings. The provider uses serialized SQLite transactions for settlement; the driver is deterministic and sequential.
8. Terminal outcomes are immutable here. Reversals, chargebacks, later refund failures after reported success, cancellation, reconciliation conflicts needing business decisions, and real provider retention policies require another state model.

## Regression inventory

17 unittest methods cover positive control; durable restart and two attempts/one key; crash boundaries; stale reads; indefinitely unknown operations; terminal-before-accepted events; two distinct equal-amount refunds; delayed failed refunds; full-balance oversubscription failing later; invalid amounts; operation payload conflicts; provider key conflicts; bad event identities/payloads/versions; and all six orderings of three events for both terminal outcomes, with duplicate delivery and restarts between events.

### Missing terminal webhook fallback

Two additional tests cover both succeeded and failed provider outcomes with **no webhook delivered at all**: the initial response is lost, the fake provider settles, both databases close/reopen, repeated stale empty reads leave the operation unknown, and the first visible authoritative read reaches the terminal state. A second restart preserves it. Repeated stale/visible observations and retries cannot regress state, add attempts, call submit, create another refund, or change the settled total (2000 on success, 0 on failure). These assertions exercise the existing finite fake-provider model, not a live provider or its actual read-consistency contract.

## Evidence boundary and next useful validation

This pack does **not** run current `@adyen/mcp`, reproduce that package's implementation, prove a fix, certify production safety/compliance, establish willingness to pay, or claim a sale. It has not been posted, submitted as a PR, or deployed.

For a separately authorized feedback/pilot, request a sanitized trace with original intent ID, attempt ID, provider key/refund ID, accepted response/error, webhook fields and delivery order, and timestamps. Compare each actual contract to the assumptions above; turn any mismatch into a failing fixture before proposing an adapter. A maintainer's review invitation is a feedback opening, not procurement. Real sandbox integration, publication, outreach, or payment handling require separate authorization and real schema/retention validation.
