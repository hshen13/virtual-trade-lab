"""Evidence-labelled, local-only experiment registry. Never verifies real revenue.

No market data is bundled. All imported observations remain user declarations.
This module intentionally uses its own database, not the simulated credit ledger.
"""
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3

from .core import TradeError

EVENT_FIELDS = {"event_id", "campaign_id", "subject_id", "domain", "partition", "event_type",
                "occurred_at", "amount_minor", "currency", "source_id", "evidence_ref", "transaction_id"}
STAGES = ("exposure", "interest", "quote", "order", "paid", "fulfilled", "accepted")
EVENT_TYPES = set(STAGES) | {"rejected", "cancelled", "refunded", "cost", "followup_closed"}
TERMINALS = {"accepted", "rejected", "cancelled"}
MONEY = {"paid", "refunded", "cost"}


def now_utc():
    return datetime.now(timezone.utc)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise TradeError(f"{name}: use a nonempty opaque ID (ASCII letters/digits/_.:-), not personal data")
    return value


def timestamp(value):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError()
        return stamp
    except (AttributeError, TypeError, ValueError) as exc:
        raise TradeError("occurred_at must be an ISO timestamp with timezone") from exc


def wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    scale = 1 + z * z / total
    center = (p + z * z / (2 * total)) / scale
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    return [max(0.0, center - margin), min(1.0, center + margin)]


def metrics(events, observation_end=None):
    """Count subjects, not rows. Incomplete funnels cannot silently improve a rate."""
    all_events = events
    cutoff = timestamp(observation_end) if observation_end else None
    closed = {e["subject_id"] for e in events if e["event_type"] == "followup_closed" and (cutoff is None or timestamp(e["occurred_at"]) >= cutoff)}
    events = [e for e in events if cutoff is None or timestamp(e["occurred_at"]) <= cutoff]
    subjects = {}
    for event in events:
        subjects.setdefault(event["subject_id"], []).append(event)
    raw = {stage: {s for s, rows in subjects.items() if any(e["event_type"] == stage for e in rows)} for stage in STAGES}
    cumulative = set(subjects)
    funnel = []
    anomalies = []
    for index, stage in enumerate(STAGES):
        previous = set(cumulative)
        cumulative &= raw[stage]
        denominator = len(raw["exposure"]) if index == 0 else len(previous)
        funnel.append({"stage": stage, "raw_subject_count": len(raw[stage]),
                       "eligible_subject_count": len(cumulative), "denominator": denominator,
                       "denominator_definition": "unique exposed subjects" if index == 0 else f"subjects completing all stages through {STAGES[index-1]}",
                       "rate": len(cumulative) / denominator if denominator else None})
        if raw[stage] - cumulative:
            anomalies.append(f"{stage}: {len(raw[stage] - cumulative)} subject(s) missing preceding funnel stages")
    exposed = raw["exposure"]
    terminal = {s for s, rows in subjects.items() if any(e["event_type"] in TERMINALS for e in rows)}
    accepted = raw["accepted"] & exposed
    pending = exposed - closed
    for subject, rows in subjects.items():
        earliest = {stage: min((timestamp(e["occurred_at"]) for e in rows if e["event_type"] == stage), default=None) for stage in STAGES}
        seen = [earliest[s] for s in STAGES if earliest[s] is not None]
        if seen != sorted(seen):
            anomalies.append(f"{subject}: funnel timestamps are out of order")
    totals = {kind: sum(e["amount_minor"] for e in all_events if e["event_type"] == kind) for kind in MONEY}
    return {"subject_count": len(subjects), "exposed_subjects": len(exposed), "accepted_subjects": len(accepted),
            "pending_exposed_subjects": len(pending), "followup_closed_subjects": len(exposed & closed),
            "observation_end": observation_end, "terminal_subjects": len(terminal),
            "cancelled_subjects": sum(any(e["event_type"] == "cancelled" for e in rows) for rows in subjects.values()),
            "rejected_subjects": sum(any(e["event_type"] == "rejected" for e in rows) for rows in subjects.values()),
            "refunded_subjects": len({e["subject_id"] for e in all_events if e["event_type"] == "refunded"}),
            "funnel": funnel, "quality_issues": anomalies,
            "acceptance_rate": len(accepted) / len(exposed) if exposed else None,
            "wilson_95": wilson(len(accepted), len(exposed)),
            "cost_coverage": "unknown; absence of cost events is not zero actual cost",
            "money_as_of": max((timestamp(e["occurred_at"]) for e in all_events), default=None).isoformat() if all_events else None,
            "late_acceptance_subjects": len({e["subject_id"] for e in all_events if e["event_type"] == "accepted" and cutoff and timestamp(e["occurred_at"]) > cutoff}),
            "declared_money_minor": {"receipts": totals["paid"], "refunds": totals["refunded"],
                                     "costs": totals["cost"], "net_receipts_after_refunds": totals["paid"] - totals["refunded"],
                                     "net_after_declared_costs": totals["paid"] - totals["refunded"] - totals["cost"]}}


class ExperimentRegistry:
    SCHEMA = "evidence-registry-v1"

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        create = not self.path.exists()
        if create:
            try:
                self.path.touch(mode=0o600, exist_ok=False)
            except FileExistsError:
                create = False
        with self.connection() as db:
            if create:
                db.execute("CREATE TABLE metadata (version TEXT NOT NULL)")
                db.execute("INSERT INTO metadata VALUES (?)", (self.SCHEMA,))
                db.execute("CREATE TABLE campaigns (id TEXT PRIMARY KEY, definition TEXT NOT NULL, locked_version INTEGER, frozen_at TEXT)")
                db.execute("CREATE TABLE events (id TEXT PRIMARY KEY, campaign TEXT NOT NULL REFERENCES campaigns(id), subject TEXT NOT NULL, domain TEXT NOT NULL, partition TEXT NOT NULL, source TEXT NOT NULL, evidence TEXT NOT NULL, body TEXT NOT NULL, checksum TEXT NOT NULL, UNIQUE(source,evidence))")
                db.execute("CREATE TABLE predictions (campaign TEXT NOT NULL REFERENCES campaigns(id), version INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(campaign,version))")
            if db.execute("SELECT version FROM metadata").fetchall() != [(self.SCHEMA,)]:
                raise TradeError("Unsupported experiment schema; do not overwrite the file")

    @contextmanager
    def connection(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise TradeError("Experiment database integrity failure")
            yield db
            db.execute("COMMIT")
        except sqlite3.Error as exc:
            if db and db.in_transaction:
                db.rollback()
            raise TradeError("Experiment database invalid or unavailable; preserve it, no automatic reset") from exc
        except Exception:
            if db and db.in_transaction:
                db.rollback()
            raise
        finally:
            if db:
                db.close()

    def _campaign(self, db, campaign_id):
        row = db.execute("SELECT definition,locked_version,frozen_at FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
        if not row:
            raise TradeError("Unknown campaign")
        return json.loads(row[0]), row[1], row[2]

    def create_campaign(self, campaign_id, *, currency, calibration_end, exposure_end, observation_end,
                        holdout_subjects=None, min_holdout=30, tolerance=None, plan_rationale=""):
        identifier(campaign_id, "campaign_id")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise TradeError("currency must be a declared three-letter code; no currency conversion")
        if type(min_holdout) is not int or min_holdout < 1:
            raise TradeError("min_holdout must be a positive integer")
        if tolerance is not None and (type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 < tolerance < 1):
            raise TradeError("tolerance must be between 0 and 1")
        ends = [timestamp(v) for v in (calibration_end, exposure_end, observation_end)]
        if not ends[0] < ends[1] <= ends[2]:
            raise TradeError("Require calibration_end < exposure_end <= observation_end")
        if tolerance is not None and (not isinstance(plan_rationale, str) or not plan_rationale.strip()):
            raise TradeError("Chosen tolerance/minimum require a declared rationale, not a fake default")
        if not isinstance(plan_rationale, str) or len(plan_rationale) > 2000:
            raise TradeError("Invalid plan rationale")
        holdout_subjects = [] if holdout_subjects is None else holdout_subjects
        if not isinstance(holdout_subjects, list) or len(holdout_subjects) > 10000:
            raise TradeError("holdout_subjects must be a list of up to 10000 planned opaque IDs")
        for subject in holdout_subjects:
            identifier(subject, "holdout subject")
        if len(holdout_subjects) != len(set(holdout_subjects)):
            raise TradeError("Duplicate planned subject")
        definition = {"campaign_id": campaign_id, "currency": currency, "min_holdout": min_holdout,
                      "tolerance": tolerance, "plan_rationale": plan_rationale, "plan_review": "self-declared; scientific justification not independently reviewed",
                      "calibration_end": calibration_end, "exposure_end": exposure_end, "observation_end": observation_end,
                      "holdout_subjects": sorted(holdout_subjects), "unit": "stable anonymous customer/group; one opportunity per campaign", "target": "accepted subjects / all exposed subjects",
                      "funnel_stages": list(STAGES), "interval": "Wilson 95%, independent-subject assumption"}
        with self.connection() as db:
            old = db.execute("SELECT definition FROM campaigns WHERE id=?", (campaign_id,)).fetchone()
            if old and old[0] != canonical(definition):
                raise TradeError("Campaign definitions are immutable; use a new campaign ID")
            if not old:
                db.execute("INSERT INTO campaigns VALUES (?,?,NULL,NULL)", (campaign_id, canonical(definition)))
        return definition

    def _validate_event(self, event, definition):
        if not isinstance(event, dict) or set(event) != EVENT_FIELDS:
            raise TradeError("Event fields must exactly match the documented schema")
        for key in ("event_id", "campaign_id", "subject_id", "source_id"):
            identifier(event[key], key)
        if event["domain"] not in ("observed", "simulated") or event["partition"] not in ("calibration", "holdout"):
            raise TradeError("Explicit observed/simulated domain and calibration/holdout partition required")
        if not isinstance(event["event_type"], str) or event["event_type"] not in EVENT_TYPES:
            raise TradeError("Unknown event_type")
        event_time = timestamp(event["occurred_at"])
        if event["domain"] == "observed" and event_time > now_utc():
            raise TradeError("Observed event cannot be future-dated")
        if event["event_type"] in MONEY:
            identifier(event["transaction_id"], "transaction_id")
        elif event["transaction_id"] != "":
            raise TradeError("Nonfinancial events require empty transaction_id")
        if not isinstance(event["evidence_ref"], str) or event["evidence_ref"] != event["evidence_ref"].strip() or not 1 <= len(event["evidence_ref"]) <= 512:
            raise TradeError("A nonempty per-record evidence_ref is mandatory")
        if type(event["amount_minor"]) is not int or not 0 <= event["amount_minor"] <= 10**12:
            raise TradeError("amount_minor must be an integer in [0, 10^12]")
        if event["event_type"] not in MONEY and event["amount_minor"] != 0:
            raise TradeError("Only paid/refunded/cost events carry amounts")
        if event["event_type"] in MONEY and event["amount_minor"] == 0:
            raise TradeError("Money events require a positive amount")
        if event["currency"] != definition["currency"]:
            raise TradeError("Campaign currency mismatch; currencies cannot be mixed")

    def _events(self, db, campaign_id, domain=None, partition=None):
        rows = []
        for body, checksum in db.execute("SELECT body,checksum FROM events WHERE campaign=? ORDER BY id", (campaign_id,)):
            if hashlib.sha256(body.encode()).hexdigest() != checksum:
                raise TradeError("Stored event checksum mismatch; preserve database")
            rows.append(json.loads(body))
        return [e for e in rows if (domain is None or e["domain"] == domain) and (partition is None or e["partition"] == partition)]

    def import_events(self, events):
        if not isinstance(events, list) or not events or len(events) > 10000:
            raise TradeError("Import must contain 1–10000 events; empty data is not evidence")
        inserted = duplicates = 0
        with self.connection() as db:
            touched = set()
            for event in events:
                if not isinstance(event, dict) or not isinstance(event.get("campaign_id"), str):
                    raise TradeError("Event campaign_id is required")
                definition, locked, frozen_at = self._campaign(db, event["campaign_id"])
                self._validate_event(event, definition)
                encoded = canonical(event)
                old = db.execute("SELECT body,checksum FROM events WHERE id=?", (event["event_id"],)).fetchone()
                if old:
                    if hashlib.sha256(old[0].encode()).hexdigest() != old[1]:
                        raise TradeError("Stored event checksum mismatch; preserve database")
                    if old[0] != encoded:
                        raise TradeError("Conflicting duplicate event_id; import rolled back")
                    duplicates += 1
                    continue
                evidence = db.execute("SELECT 1 FROM events WHERE source=? AND evidence=?", (event["source_id"], event["evidence_ref"])).fetchone()
                if evidence:
                    raise TradeError("Evidence record already imported under another event ID")
                assigned = db.execute("SELECT domain,partition FROM events WHERE campaign=? AND subject=? LIMIT 1", (event["campaign_id"], event["subject_id"])).fetchone()
                if assigned and assigned != (event["domain"], event["partition"]):
                    raise TradeError("Subject domain/partition contamination; assignment cannot change")
                if event["partition"] == "holdout" and locked is None:
                    raise TradeError("Freeze a prediction before importing any holdout event")
                if event["domain"] == "observed" and event["partition"] == "holdout":
                    if event["subject_id"] not in definition["holdout_subjects"]:
                        raise TradeError("Observed holdout subject was not in frozen cohort")
                    if timestamp(event["occurred_at"]) <= timestamp(frozen_at):
                        raise TradeError("Observed holdout must occur after freeze, not just be imported later")
                    if event["event_type"] == "exposure" and timestamp(event["occurred_at"]) > timestamp(definition["exposure_end"]):
                        raise TradeError("Exposure outside the predeclared enrollment window")
                if event["partition"] == "calibration" and event["subject_id"] in definition["holdout_subjects"]:
                    raise TradeError("Planned holdout subject cannot enter calibration")
                if event["partition"] == "calibration" and locked is not None:
                    raise TradeError("Calibration is frozen; use a new campaign for another iteration")
                if event["event_type"] in {"paid", "cost"}:
                    for existing_body, in db.execute("SELECT body FROM events"):
                        existing = json.loads(existing_body)
                        if existing["event_type"] == event["event_type"] and existing["transaction_id"] == event["transaction_id"]:
                            raise TradeError("Financial transaction_id already recorded; use source-qualified IDs")
                db.execute("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", (event["event_id"], event["campaign_id"], event["subject_id"], event["domain"], event["partition"], event["source_id"], event["evidence_ref"], encoded, hashlib.sha256(encoded.encode()).hexdigest()))
                touched.add(event["campaign_id"])
                inserted += 1
            for campaign in touched:
                subjects = {}
                for event in self._events(db, campaign):
                    subjects.setdefault(event["subject_id"], []).append(event)
                for rows in subjects.values():
                    terminal = [e for e in rows if e["event_type"] in TERMINALS]
                    if len(terminal) > 1:
                        raise TradeError("One terminal decision per stable subject; repeated orders need a different prespecified outcome model")
                    payments = {}
                    for record in rows:
                        if record["event_type"] == "paid":
                            if record["transaction_id"] in payments:
                                raise TradeError("Duplicate payment transaction_id")
                            payments[record["transaction_id"]] = record
                    refunds = {}
                    for record in rows:
                        if record["event_type"] == "refunded":
                            payment = payments.get(record["transaction_id"])
                            if not payment or timestamp(record["occurred_at"]) < timestamp(payment["occurred_at"]):
                                raise TradeError("Refund must reference an earlier recorded payment")
                            refunds[record["transaction_id"]] = refunds.get(record["transaction_id"], 0) + record["amount_minor"]
                    if any(amount > payments[key]["amount_minor"] for key, amount in refunds.items()):
                        raise TradeError("Refund exceeds its referenced payment")
                    sums = {kind: sum(e["amount_minor"] for e in rows if e["event_type"] == kind) for kind in MONEY}
                    if sums["refunded"] > sums["paid"]:
                        raise TradeError("Refunds exceed recorded receipts for a subject")
        return {"inserted": inserted, "exact_duplicates_ignored": duplicates, "authenticity": "not independently verified"}

    def predict(self, campaign_id, *, method, probability=None, rationale):
        if method not in ("manual", "simulation_calibration", "observed_calibration"):
            raise TradeError("Unknown prediction method")
        if not isinstance(rationale, str) or not 1 <= len(rationale.strip()) <= 1000:
            raise TradeError("Prediction rationale/provenance required")
        with self.connection() as db:
            definition, locked, _ = self._campaign(db, campaign_id)
            if locked is not None:
                raise TradeError("Prediction frozen; holdout cannot become training data in this campaign")
            domain = {"simulation_calibration": "simulated", "observed_calibration": "observed"}.get(method)
            events = self._events(db, campaign_id, domain, "calibration") if domain else []
            summary = metrics(events, definition["calibration_end"])
            if method != "manual":
                if probability is not None:
                    raise TradeError("Empirical method calculates its own probability")
                if not summary["exposed_subjects"] or summary["pending_exposed_subjects"] or summary["quality_issues"]:
                    raise TradeError("Calibration requires a nonempty complete cohort and valid funnel")
                probability = summary["acceptance_rate"]
            if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
                raise TradeError("Manual probability must be explicit and in [0,1]")
            version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM predictions WHERE campaign=?", (campaign_id,)).fetchone()[0]
            body = {"version": version, "method": method, "probability": probability, "rationale": rationale,
                    "calibration_domain": domain, "calibration_event_ids": [e["event_id"] for e in events],
                    "calibration_sha256": hashlib.sha256(canonical(events).encode()).hexdigest(),
                    "calibration_subjects": summary["exposed_subjects"], "calibration_wilson_95": summary["wilson_95"],
                    "claim": "declared baseline" if method == "manual" else "empirical cohort fraction; not a trained general model"}
            db.execute("INSERT INTO predictions VALUES (?,?,?)", (campaign_id, version, canonical(body)))
            return body

    def freeze(self, campaign_id, version):
        if type(version) is not int or version < 1:
            raise TradeError("version must be a positive integer")
        with self.connection() as db:
            definition, locked, _ = self._campaign(db, campaign_id)
            if locked is not None and locked != version:
                raise TradeError("Primary prediction already frozen")
            if not db.execute("SELECT 1 FROM predictions WHERE campaign=? AND version=?", (campaign_id, version)).fetchone():
                raise TradeError("Unknown prediction version")
            if locked is None:
                if not timestamp(definition["calibration_end"]) < now_utc() < timestamp(definition["exposure_end"]):
                    raise TradeError("Freeze must follow calibration cutoff and precede holdout enrollment cutoff")
                prediction = json.loads(db.execute("SELECT body FROM predictions WHERE campaign=? AND version=?", (campaign_id, version)).fetchone()[0])
                if prediction["calibration_domain"]:
                    current = self._events(db, campaign_id, prediction["calibration_domain"], "calibration")
                    if hashlib.sha256(canonical(current).encode()).hexdigest() != prediction["calibration_sha256"]:
                        raise TradeError("Calibration changed after prediction; create a new prediction version before freezing")
                db.execute("UPDATE campaigns SET locked_version=?,frozen_at=? WHERE id=?", (version, now_utc().isoformat(), campaign_id))
        return {"campaign_id": campaign_id, "locked_version": version, "calibration_closed": True}

    def report(self, campaign_id):
        with self.connection() as db:
            definition, locked, frozen_at = self._campaign(db, campaign_id)
            groups = {domain: {part: metrics(self._events(db, campaign_id, domain, part), definition["calibration_end"] if part == "calibration" else definition["observation_end"]) for part in ("calibration", "holdout")} for domain in ("observed", "simulated")}
            predictions = [json.loads(row[0]) for row in db.execute("SELECT body FROM predictions WHERE campaign=? ORDER BY version", (campaign_id,))]
            primary = next((p for p in predictions if p["version"] == locked), None)
            holdout = groups["observed"]["holdout"]
            held_events = self._events(db, campaign_id, "observed", "holdout")
            observation_snapshot = {"version": hashlib.sha256(canonical(held_events).encode()).hexdigest(),
                                    "event_count": len(held_events), "event_ids": [e["event_id"] for e in held_events]}
            evaluation = {"status": "not_evaluated", "reason": "No frozen prediction with observed holdout evidence", "primary_version": locked}
            if primary and holdout["subject_count"]:
                n, accepted = holdout["exposed_subjects"], holdout["accepted_subjects"]
                evaluation.update({"denominator": n, "accepted": accepted, "observed_rate": holdout["acceptance_rate"], "wilson_95": holdout["wilson_95"]})
                if n < definition["min_holdout"] or n != len(definition["holdout_subjects"]) or holdout["pending_exposed_subjects"] or holdout["quality_issues"] or now_utc() < timestamp(definition["observation_end"]):
                    evaluation.update(status="insufficient_data", reason="Minimum cohort size, complete outcomes, and valid funnel are all required")
                elif definition["tolerance"] is None:
                    p = primary["probability"]
                    evaluation.update(status="unassessed", reason="No justified tolerance was predeclared; descriptive estimates only",
                                      absolute_error=abs(accepted / n - p), brier_score=(accepted * (1-p)**2 + (n-accepted) * p**2) / n)
                else:
                    p, (low, high), tolerance = primary["probability"], holdout["wilson_95"], definition["tolerance"]
                    status = "within_declared_tolerance" if low >= p - tolerance and high <= p + tolerance else "outside_declared_tolerance" if high < p - tolerance or low > p + tolerance else "inconclusive"
                    evaluation.update(status=status, reason="Interval comparison only; input authenticity and external validity remain unverified",
                                      absolute_error=abs(accepted / n - p), brier_score=(accepted * (1-p)**2 + (n-accepted) * p**2) / n)
            return {"campaign": definition, "frozen_at": frozen_at, "groups": groups, "predictions": predictions, "observation_snapshot": observation_snapshot, "evaluation": evaluation,
                    "completion_gates": {"real_buyer_acceptance": "unverified", "independently_verified_real_receipt": "unverified",
                                         "complete_cost_accounting": "unresolved", "legal_eligibility": "unresolved"},
                    "overall_goal": "not_completed", "authenticity": "All observed imports are user declarations, not independently verified facts",
                    "limits": ["No data-source authenticity check; no legal certification", "Wilson interval assumes independent subjects and a prespecified complete cohort",
                               "No observed/simulated pooling; no holdout-to-calibration reassignment", "A new real cohort is required for each next iteration; new IDs do not make reused evidence independent",
                               "Declared net amounts omit unknown costs/taxes and are not verified income"]}


def unique_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TradeError("Duplicate JSON object field")
        result[key] = value
    return result


def load_events(path):
    path = Path(path)
    if path.stat().st_size > 5 * 1024 * 1024:
        raise TradeError("Import file exceeds 5 MiB")
    if path.suffix.lower() == ".json":
        with path.open(encoding="utf-8-sig") as stream:
            return json.load(stream, object_pairs_hook=unique_json_keys)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != EVENT_FIELDS:
                raise TradeError("CSV headers must match the event schema exactly")
            rows = list(reader)
            for row in rows:
                try:
                    if not re.fullmatch(r"0|[1-9][0-9]*", row["amount_minor"] or ""):
                        raise ValueError()
                    row["amount_minor"] = int(row["amount_minor"])
                except (ValueError, TypeError) as exc:
                    raise TradeError("CSV amount_minor must contain integer minor units") from exc
            return rows
    raise TradeError("Import supports .json or .csv only")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Local evidence registry; no real data bundled, no legal/revenue certification")
    parser.add_argument("--db", default=".virtual-trade-lab/experiments.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("campaign")
    create.add_argument("id")
    create.add_argument("--currency", required=True)
    create.add_argument("--min-holdout", type=int, default=30)
    create.add_argument("--tolerance", type=float)
    create.add_argument("--plan-rationale", default="")
    create.add_argument("--calibration-end", required=True)
    create.add_argument("--exposure-end", required=True)
    create.add_argument("--observation-end", required=True)
    create.add_argument("--holdout-subjects", help="JSON file containing predeclared opaque subject IDs")
    imp = sub.add_parser("import")
    imp.add_argument("file")
    pred = sub.add_parser("predict")
    pred.add_argument("id")
    pred.add_argument("--method", choices=["manual", "simulation_calibration", "observed_calibration"], required=True)
    pred.add_argument("--probability", type=float)
    pred.add_argument("--rationale", required=True)
    freeze = sub.add_parser("freeze")
    freeze.add_argument("id")
    freeze.add_argument("--version", type=int, required=True)
    report = sub.add_parser("report")
    report.add_argument("id")
    args = parser.parse_args()
    try:
        registry = ExperimentRegistry(args.db)
        if args.command == "campaign":
            subjects = json.loads(Path(args.holdout_subjects).read_text(encoding="utf-8")) if args.holdout_subjects else []
            result = registry.create_campaign(args.id, currency=args.currency, min_holdout=args.min_holdout, tolerance=args.tolerance,
                                              calibration_end=args.calibration_end, exposure_end=args.exposure_end,
                                              observation_end=args.observation_end, holdout_subjects=subjects, plan_rationale=args.plan_rationale)
        elif args.command == "import":
            result = registry.import_events(load_events(args.file))
        elif args.command == "predict":
            result = registry.predict(args.id, method=args.method, probability=args.probability, rationale=args.rationale)
        elif args.command == "freeze":
            result = registry.freeze(args.id, args.version)
        else:
            result = registry.report(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (TradeError, OSError, ValueError, RecursionError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
