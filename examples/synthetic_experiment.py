"""CLI smoke only: generated simulated events, NEVER observed customer evidence."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    now = datetime.now(timezone.utc)
    with TemporaryDirectory() as directory:
        db = str(Path(directory) / "synthetic.sqlite3")

        def cli(*args):
            process = subprocess.run([sys.executable, "-m", "virtual_trade_lab.experiments", "--db", db, *args],
                                     text=True, capture_output=True, check=True)
            return json.loads(process.stdout)

        cutoff = (now - timedelta(days=1)).isoformat()
        cli("campaign", "synthetic-demo", "--currency", "CNY", "--calibration-end", cutoff,
            "--exposure-end", (now + timedelta(days=14)).isoformat(),
            "--observation-end", (now + timedelta(days=30)).isoformat())
        events = []
        for subject, stages in enumerate([list(("exposure", "interest", "quote", "order", "paid", "fulfilled", "accepted")),
                                          ["exposure", "rejected"]]):
            for index, kind in enumerate(stages + ["followup_closed"]):
                events.append({"event_id": f"sim-{subject}-{index}", "campaign_id": "synthetic-demo",
                               "subject_id": f"sim-subject-{subject}", "domain": "simulated", "partition": "calibration",
                               "event_type": kind, "occurred_at": cutoff if kind == "followup_closed" else
                               (now - timedelta(days=2) + timedelta(minutes=index)).isoformat(),
                               "amount_minor": 100 if kind == "paid" else 0, "currency": "CNY",
                               "source_id": "synthetic-script", "evidence_ref": f"synthetic:row:{subject}:{index}",
                               "transaction_id": f"sim:payment:{subject}" if kind == "paid" else ""})
        source = Path(directory) / "simulated-only.json"
        source.write_text(json.dumps(events), encoding="utf-8")
        first, repeated = cli("import", str(source)), cli("import", str(source))
        if first["inserted"] != len(events) or repeated["exact_duplicates_ignored"] != len(events):
            raise RuntimeError("Import/replay check failed")
        cli("predict", "synthetic-demo", "--method", "simulation_calibration", "--rationale",
            "Synthetic workflow smoke only; not a learned real-market probability")
        cli("freeze", "synthetic-demo", "--version", "1")
        report = cli("report", "synthetic-demo")
        if report["evaluation"]["status"] != "not_evaluated":
            raise RuntimeError("Synthetic demo must never count as observed evaluation")
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
