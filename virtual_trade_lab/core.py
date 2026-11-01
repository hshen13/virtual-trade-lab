"""Deterministic, in-memory marketplace simulation. Credits are not money."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
import json
from typing import Protocol


class TradeError(ValueError):
    """A rejected command: no state or funds changed."""


def whole(value: int, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise TradeError(f"{name} must be an integer >= {minimum}")
    return value


@dataclass(frozen=True)
class Criteria:
    """Buyer-owned policy; seller does not decide whether its work passes."""
    budget: int = 40
    max_revisions: int = 1
    max_title_length: int = 80

    def __post_init__(self):
        whole(self.budget, "budget", 1)
        whole(self.max_revisions, "max_revisions")
        whole(self.max_title_length, "max_title_length", 1)


@dataclass(frozen=True)
class Quote:
    price: int
    cost_per_attempt: int
    service: str

    def __post_init__(self):
        whole(self.price, "price", 1)
        whole(self.cost_per_attempt, "cost_per_attempt")
        if not self.service:
            raise TradeError("service name is required")


class ServiceAdapter(Protocol):
    """Adapters must be deterministic and side-effect-free for rollback/replay."""
    name: str
    def quote(self, source: list[dict]) -> Quote: ...
    def fulfill(self, source: list[dict], attempt: int, mode: str) -> list[dict]: ...


class BuyerEvaluator(Protocol):
    def assess(self, source: list[dict], result: list[dict], criteria: Criteria) -> list[str]: ...


@dataclass
class Order:
    id: str
    source: list[dict]
    criteria: Criteria
    quote: Quote
    state: str = "quoted"
    attempts: int = 0
    revisions: int = 0
    result: list[dict] | None = None
    issues: list[str] = field(default_factory=list)
    cost: int = 0


class Market:
    """Single buyer/seller, serial command processor; not a payment system."""
    def __init__(self, service: ServiceAdapter, evaluator: BuyerEvaluator,
                 buyer_credits: int = 100, seller_credits: int = 30):
        self.service, self.evaluator = service, evaluator
        self._balances = {"buyer": whole(buyer_credits, "buyer credits"),
                          "seller": whole(seller_credits, "seller credits"), "provider": 0}
        self.initial_total = sum(self._balances.values())
        self._initial_balances = dict(self._balances)
        self._orders: dict[str, Order] = {}
        self._journal: list[dict] = []
        self._events: list[dict] = []
        self._receipts: dict[str, tuple[str, dict]] = {}

    @property
    def balances(self):
        return deepcopy(self._balances)

    @property
    def journal(self):
        return deepcopy(self._journal)

    @property
    def events(self):
        return deepcopy(self._events)

    def order(self, order_id: str) -> Order:
        if order_id not in self._orders:
            raise TradeError("unknown order")
        return deepcopy(self._orders[order_id])

    def execute(self, action: str, order_id: str, key: str, **payload) -> dict:
        """Successful request keys replay exactly; changed requests cannot reuse keys.

        Failed commands are atomic and do not consume their key. Keys survive only
        for this Market instance. No concurrency or crash durability is claimed.
        """
        if not isinstance(action, str):
            raise TradeError("action must be a string")
        if not isinstance(key, str) or not key or not isinstance(order_id, str) or not order_id:
            raise TradeError("nonempty string order_id and key required")
        try:
            fingerprint = json.dumps([action, order_id, payload], sort_keys=True, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise TradeError("payload must be JSON serializable") from exc
        if key in self._receipts:
            old, receipt = self._receipts[key]
            if old != fingerprint:
                raise TradeError("idempotency key conflict")
            return deepcopy(receipt)
        snapshot = deepcopy((self._balances, self._orders, self._journal, self._events))
        try:
            self._dispatch(action, order_id, payload)
            self.assert_invariants()
            receipt = asdict(self._orders[order_id])
            self._events.append({"sequence": len(self._events) + 1, "action": action,
                                 "order": order_id, "state": receipt["state"], "key": key,
                                 "issues": deepcopy(receipt["issues"]), "attempts": receipt["attempts"],
                                 "cost_credits": receipt["cost"]})
            self._receipts[key] = (fingerprint, deepcopy(receipt))
            return receipt
        except Exception:
            self._balances, self._orders, self._journal, self._events = snapshot
            raise

    def _transfer(self, source: str, target: str, amount: int, order_id: str, reason: str):
        whole(amount, "transfer")
        if self._balances[source] < amount:
            raise TradeError(f"insufficient {source} credits")
        self._balances[source] -= amount
        self._balances[target] += amount
        self._journal.append({"sequence": len(self._journal) + 1, "order": order_id,
                              "from": source, "to": target, "credits": amount, "reason": reason})

    def _dispatch(self, action, order_id, payload):
        allowed = {"quote": {"source", "criteria"}, "fund": set(), "deliver": {"mode"},
                   "review": set(), "cancel": set()}
        if action not in allowed or payload.keys() - allowed[action]:
            raise TradeError("unknown command or unexpected fields")
        escrow = f"escrow:{order_id}"
        if action == "quote":
            if order_id in self._orders:
                raise TradeError("order already exists")
            source = deepcopy(payload.get("source"))
            if not isinstance(source, list) or not source or not all(isinstance(x, dict) for x in source):
                raise TradeError("source must be a nonempty list of objects")
            try:
                criteria = Criteria(**payload.get("criteria", {}))
            except TypeError as exc:
                raise TradeError("invalid criteria") from exc
            quote = self.service.quote(deepcopy(source))
            if not isinstance(quote, Quote) or quote.service != self.service.name:
                raise TradeError("invalid service quote")
            self._orders[order_id] = Order(order_id, source, criteria, quote)
            self._balances[escrow] = 0
            return
        if order_id not in self._orders:
            raise TradeError("unknown order")
        order = self._orders[order_id]
        if action == "fund":
            if order.state != "quoted":
                raise TradeError("only quoted orders can be funded")
            if order.quote.price > order.criteria.budget:
                raise TradeError("quote exceeds buyer budget")
            self._transfer("buyer", escrow, order.quote.price, order_id, "fund")
            order.state = "funded"
        elif action == "deliver":
            if order.state not in {"funded", "revision_requested"}:
                raise TradeError("delivery requires funded or revision_requested order")
            mode = payload.get("mode", "normal")
            if not isinstance(mode, str) or mode not in {"normal", "defective", "crash"}:
                raise TradeError("unknown demonstration mode")
            # A failed computation is still a cost; it produces reviewable failure evidence.
            self._transfer("seller", "provider", order.quote.cost_per_attempt, order_id, "compute")
            order.cost += order.quote.cost_per_attempt
            order.attempts += 1
            try:
                result = self.service.fulfill(deepcopy(order.source), order.attempts, mode)
                if not isinstance(result, list) or not all(isinstance(x, dict) for x in result):
                    raise ValueError("adapter returned an invalid result")
                # JSON roundtrip ensures a plain, finite, detached delivery artifact.
                order.result = json.loads(json.dumps(result, allow_nan=False))
                order.issues = []
            except Exception as exc:
                order.result = None
                order.issues = [f"seller failure: {type(exc).__name__}"]
            order.state = "delivered"
        elif action == "review":
            if order.state != "delivered":
                raise TradeError("review requires a delivery")
            issues = ([*order.issues] if order.result is None else
                      self.evaluator.assess(deepcopy(order.source), deepcopy(order.result), order.criteria))
            if not isinstance(issues, list) or not all(isinstance(x, str) for x in issues):
                raise TradeError("evaluator must return a list of issue strings")
            order.issues = list(issues)
            if not issues:
                self._transfer(escrow, "seller", order.quote.price, order_id, "accept")
                order.state = "accepted"
            elif order.revisions < order.criteria.max_revisions:
                order.revisions += 1
                order.state = "revision_requested"
            else:
                self._transfer(escrow, "buyer", order.quote.price, order_id, "reject_refund")
                order.state = "rejected"
        elif action == "cancel":
            if order.state not in {"quoted", "funded", "revision_requested"}:
                raise TradeError("cannot cancel delivered or terminal order; review delivery first")
            if self._balances[escrow]:
                self._transfer(escrow, "buyer", order.quote.price, order_id, "cancel_refund")
            order.state = "cancelled"

    def assert_invariants(self):
        """Runtime integrity checks remain enabled even under python -O."""
        def require(condition, message):
            if not condition:
                raise RuntimeError(f"ledger invariant: {message}")
        require(all(type(x) is int and x >= 0 for x in self._balances.values()), "invalid balance")
        require(sum(self._balances.values()) == self.initial_total, "credits must be conserved")
        reconstructed = {key: self._initial_balances.get(key, 0) for key in self._balances}
        for entry in self._journal:
            require(type(entry["credits"]) is int and entry["credits"] >= 0, "invalid journal amount")
            reconstructed[entry["from"]] -= entry["credits"]
            reconstructed[entry["to"]] += entry["credits"]
            require(reconstructed[entry["from"]] >= 0, "historical overdraft")
        require(reconstructed == self._balances, "journal does not reconcile")
        for order in self._orders.values():
            held = order.state in {"funded", "delivered", "revision_requested"}
            require(self._balances[f"escrow:{order.id}"] == (order.quote.price if held else 0), "escrow mismatch")
            require(order.cost == order.attempts * order.quote.cost_per_attempt, "cost mismatch")
            require(order.revisions <= order.criteria.max_revisions, "revision limit exceeded")
