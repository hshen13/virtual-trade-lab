"""Three original, offline product verticals with real files and synthetic validation.

PPT is bounded text-template instantiation, not general slide/video generation.
No observed buyer, audience, market conversion, or real payment is produced.
"""
import argparse
from copy import deepcopy
import csv
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import random
import re
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import BadZipFile, ZipFile

from .core import Market, Quote, TradeError

ROOT = Path(__file__).parent
ORIGINAL_NAME = "纸舟计划卡"
CASES = ("accepted", "revision", "rejected", "budget_refused", "cancelled", "crash_refunded")
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main", "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}


def configuration():
    return json.loads((ROOT / "product_scenarios.json").read_text(encoding="utf-8"))


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9 \u4e00-\u9fff]{1,12}", name) or not name.strip():
        raise TradeError("Fictional product name must be 1–12 plain Chinese/ASCII letters or digits")
    return name


def instantiate_pptx(template, destination, name):
    """Mechanical replacement of the original fictional name in an original deck.

    This deliberately does not rearrange layouts or invent claims/images. Users
    must manually inspect long names. No third-party authoring library is shipped.
    """
    validate_name(name)
    if Path(template).resolve() == Path(destination).resolve():
        raise TradeError("Template and destination must differ")
    found = 0
    with ZipFile(template) as source, ZipFile(destination, "w") as target:
        if len(source.infolist()) > 1000 or sum(i.file_size for i in source.infolist()) > 20 * 1024 * 1024:
            raise TradeError("Template exceeds local expanded-size limit")
        if source.testzip() is not None:
            raise TradeError("Template ZIP failed integrity check")
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith(".xml"):
                found += data.count(ORIGINAL_NAME.encode())
                data = data.replace(ORIGINAL_NAME.encode(), escape(name).encode())
            target.writestr(info, data)
    if not found:
        Path(destination).unlink(missing_ok=True)
        raise TradeError("Template does not contain the expected original product name")


def build_bundle(output, *, name=ORIGINAL_NAME, template=None):
    validate_name(name)
    root = Path(output)
    root.mkdir(parents=True, exist_ok=True)
    template = Path(template) if template else ROOT / "samples" / "paperboat-promo.pptx"
    if not template.is_file():
        raise TradeError("Original PPT template missing; supply --template. No fake PPT will be substituted.")
    instantiate_pptx(template, root / "promo.pptx", name)
    script = f"""# {name}：直播彩排脚本

虚构示例。以下为原创离线彩排，不开播，不生成真实观众、库存、成交或用户评价。

## 开场 0–30 秒
这是虚构的{name}，我们演示纸质周计划和留白记录的使用场景。

## 展示 30–90 秒
在纸上写下本周的一项安排。留白区记录待讨论的问题。此处没有功效承诺。

## 问答 90–120 秒
模拟提问：库存和价格确定了吗？
主持回应：没有真实库存或销售报价。本次只验证表达和交付流程。

## 中断 120–130 秒
停止推介，保留当前位置。模拟连接中断，不把静默当作成交。

## 恢复 130–160 秒
从已确认的展示位置继续，不重复创建订单，也不重复发送宣传。

## 结束 160–180 秒
邀请在本地记录对脚本的反馈。没有发送链接、联系用户或打开支付入口。
"""
    (root / "livestream-script.md").write_text(script, encoding="utf-8")
    slots = [(0, 30, "opening"), (30, 90, "demonstration"), (90, 120, "question"),
             (120, 130, "interruption"), (130, 160, "recovery"), (160, 180, "stop")]
    with (root / "run-sheet.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["start_seconds", "end_seconds", "phase", "synthetic"])
        writer.writerows((start, end, phase, "true") for start, end, phase in slots)
    live = {"product_name": name, "disclosure": "虚构示例", "rehearsal_only": True,
            "broadcast_started": False, "audience_is_synthetic": True, "real_viewers": 0,
            "events": [{"at_seconds": start, "phase": phase, "synthetic": True} for start, _, phase in slots]}
    (root / "livestream-events.json").write_text(stable_json(live), encoding="utf-8")
    channel = {"product_name": name, "disclosure": "虚构示例", "real_payment": False,
               "promotion_posted": False, "real_inventory_known": False,
               "actors": [{"id": role + "-demo", "role": role, "synthetic": True} for role in ("buyer", "seller", "channel")],
               "journey": [{"stage": stage, "synthetic": True, "source": "original_rule_fixture"}
                           for stage in ("exposure", "interest", "quote", "order", "delivery", "independent_review")],
               "claims": ["纸质周计划", "留白记录"], "units": "simulated credits, not money"}
    (root / "channel-experience.json").write_text(stable_json(channel), encoding="utf-8")
    manifest = {"schema": "original-product-bundle/v1", "generated_artifact": True,
                "mock_buyer_validation": "run separately", "real_market_validated": False,
                "product_is_fictional": True, "product_name": name, "video_rendered": False,
                "business_acceptance": {"status": "not_evaluated", "genuine_paid_demand": "unverified", "voluntary_real_viewing": "unverified", "superiority_vs_defined_alternative": "unverified", "sustainable_economics_and_repeat_use": "unverified", "legal_eligibility": "unverified"},
                "broadcast_started": False, "promotion_posted": False,
                "provenance": "Original project text/template; no third-party graphics, music, logos or embedded fonts",
                "license": "MIT project sample; not a legal clearance certificate",
                "files": [{"path": f, "sha256": file_digest(root / f)} for entry in configuration()["verticals"].values() for f in entry["files"]]}
    (root / "manifest.json").write_text(stable_json(manifest), encoding="utf-8")
    return manifest


def check_bundle(root, vertical, offered, name=ORIGINAL_NAME):
    """Independent buyer inspection of actual bytes, not the seller's success flag."""
    config = configuration()
    if vertical not in config["verticals"]:
        return ["unknown product vertical"]
    expected = config["verticals"][vertical]["files"]
    if not isinstance(offered, list) or len(offered) != len(expected):
        return ["missing or extra deliverable"]
    if any(not isinstance(row, dict) or set(row) != {"path", "sha256"} for row in offered):
        return ["invalid deliverable descriptor"]
    if any(not isinstance(row["path"], str) or not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in offered):
        return ["invalid path or digest type"]
    if sorted(row["path"] for row in offered) != sorted(expected):
        return ["unexpected deliverable path"]
    issues, texts = [], []
    root = Path(root).resolve()
    for item in offered:
        file = (root / item["path"]).resolve()
        if not file.is_relative_to(root) or not file.is_file():
            issues.append("deliverable missing or outside bundle")
            continue
        if file.stat().st_size > 10 * 1024 * 1024:
            issues.append("deliverable exceeds 10 MiB local validation limit")
            continue
        if file_digest(file) != item["sha256"]:
            issues.append("offered digest does not match actual file")
        try:
            if vertical == "promo":
                with ZipFile(file) as deck:
                    if len(deck.infolist()) > 1000 or sum(i.file_size for i in deck.infolist()) > 20 * 1024 * 1024:
                        raise ValueError("PPTX expanded-size limit")
                    required_parts = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
                    if not required_parts.issubset(deck.namelist()):
                        raise ValueError("Missing PPTX package relationships")
                    presentation = ET.fromstring(deck.read("ppt/presentation.xml"))
                    if presentation.tag != "{" + NS["p"] + "}presentation" or len(presentation.findall(".//p:sldId", NS)) != 5:
                        issues.append("PPTX presentation must declare five slides")
                    slides = sorted(n for n in deck.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
                    if len(slides) != 5 or "ppt/presentation.xml" not in deck.namelist() or deck.testzip():
                        issues.append("PPTX requires five structurally readable slides")
                    if any(n.startswith(("ppt/media/", "ppt/fonts/")) for n in deck.namelist()):
                        issues.append("unreviewed bundled visual/font asset")
                    for part in deck.namelist():
                        if part.endswith(".rels"):
                            relationships = ET.fromstring(deck.read(part))
                            if any(r.attrib.get("TargetMode") == "External" for r in relationships):
                                issues.append("unreviewed external relationship")
                    for slide in slides:
                        slide_xml = ET.fromstring(deck.read(slide))
                        if slide_xml.tag != "{" + NS["p"] + "}sld":
                            issues.append("invalid slide root")
                        text = "\n".join(node.text or "" for node in slide_xml.findall(".//a:t", NS))
                        texts.append(text)
                        if "虚构示例" not in text:
                            issues.append("PPT slide missing fictional disclosure")
            elif file.suffix == ".md":
                texts.append(file.read_text(encoding="utf-8"))
            elif file.suffix == ".csv":
                rows = list(csv.DictReader(io.StringIO(file.read_text(encoding="utf-8"))))
                expected_phases = ["opening", "demonstration", "question", "interruption", "recovery", "stop"]
                if [r["phase"] for r in rows] != expected_phases or any(r["synthetic"] != "true" for r in rows):
                    issues.append("invalid rehearsal phases/provenance")
                cursor = 0
                for row in rows:
                    if int(row["start_seconds"]) != cursor or int(row["end_seconds"]) <= cursor:
                        issues.append("rehearsal timing gap or overlap")
                    cursor = int(row["end_seconds"])
                if cursor != 180:
                    issues.append("rehearsal must end at 180 seconds")
            else:
                data = json.loads(file.read_text(encoding="utf-8"))
                texts.append(stable_json(data))
                if data["product_name"] != name or data["disclosure"] != "虚构示例":
                    issues.append("wrong product or disclosure")
                if vertical == "livestream":
                    if data["broadcast_started"] is not False or data["rehearsal_only"] is not True or type(data["real_viewers"]) is not int or data["real_viewers"] != 0 or data["audience_is_synthetic"] is not True:
                        issues.append("simulated rehearsal must not claim a real broadcast/audience")
                    if [e["phase"] for e in data["events"]] != ["opening", "demonstration", "question", "interruption", "recovery", "stop"] or not all(e["synthetic"] is True for e in data["events"]) or [e["at_seconds"] for e in data["events"]] != [0, 30, 90, 120, 130, 160]:
                        issues.append("invalid simulated event timeline")
                else:
                    if data["real_payment"] is not False or data["promotion_posted"] is not False or data["real_inventory_known"] is not False:
                        issues.append("commerce fixture must not claim payment, promotion or inventory")
                    if [a["role"] for a in data["actors"]] != ["buyer", "seller", "channel"] or not all(a["synthetic"] is True for a in data["actors"]):
                        issues.append("unlabelled virtual actor")
                    if [e["stage"] for e in data["journey"]] != ["exposure", "interest", "quote", "order", "delivery", "independent_review"] or not all(e["synthetic"] is True and e["source"] == "original_rule_fixture" for e in data["journey"]):
                        issues.append("invalid synthetic channel funnel")
        except Exception as exc:
            # An unreadable file is a rejected delivery, never automatic acceptance.
            issues.append("artifact inspection failed: " + type(exc).__name__)
    combined = "\n".join(texts)
    for required in [name, "虚构示例", "纸质周计划", "留白记录"]:
        if required not in combined:
            issues.append("required supplied/fictional content missing: " + required)
    for forbidden in config["acceptance"]["forbidden_claims"]:
        if forbidden in combined:
            issues.append("unsupported claim: " + forbidden)
    return issues


class BundleSeller:
    name = "original-product-bundle-v1"

    def __init__(self, vertical, descriptors):
        self.vertical, self.descriptors = vertical, deepcopy(descriptors)

    def quote(self, source):
        config = configuration()["verticals"][self.vertical]
        return Quote(config["price_credits"], config["cost_per_attempt"], self.name)

    def fulfill(self, source, attempt, mode):
        if mode == "crash":
            raise RuntimeError("injected seller crash, not a real platform failure")
        output = deepcopy(self.descriptors)
        if mode == "defective":
            output[0]["sha256"] = "0" * 64
        return output


class BundleBuyer:
    def __init__(self, root, vertical, name):
        self.root, self.vertical, self.name = root, vertical, name

    def assess(self, source, result, criteria):
        return check_bundle(self.root, self.vertical, result, self.name)


def run_campaign(root, *, name=ORIGINAL_NAME, seeds=range(5)):
    """Fixed design coverage, not learned conversion estimates or real calibration."""
    seeds = tuple(seeds)
    if not seeds or len(seeds) > 100 or any(type(seed) is not int or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise TradeError("Use 1–100 distinct nonnegative integer seeds")
    config, reports = configuration(), []
    for vertical, settings in config["verticals"].items():
        descriptors = [{"path": file, "sha256": file_digest(Path(root) / file)} for file in settings["files"]]
        for seed in seeds:
            for case in CASES:
                market = Market(BundleSeller(vertical, descriptors), BundleBuyer(root, vertical, name))
                counter, failures = 0, []
                def command(action, **payload):
                    nonlocal counter
                    counter += 1
                    key = f"{vertical}-{seed}-{case}-{counter}"
                    result = market.execute(action, "demo", key, **payload)
                    # Deterministic repeated clicks/transport retries must be exact replays.
                    if market.execute(action, "demo", key, **payload) != result:
                        raise RuntimeError("idempotency receipt mismatch")
                    return result
                rng = random.Random(seed)
                budget = settings["price_credits"] - 1 if case == "budget_refused" else settings["price_credits"] + rng.randrange(1, 10)
                command("quote", source=[{"product_name": name, "vertical": vertical, "synthetic": True}], criteria={"budget": budget})
                try:
                    command("fund")
                except TradeError as exc:
                    failures.append(str(exc)); command("cancel")
                else:
                    if case == "cancelled":
                        command("cancel")
                    else:
                        mode = "normal" if case == "accepted" else "crash" if case == "crash_refunded" else "defective"
                        command("deliver", mode=mode)
                        result = command("review"); failures.extend(result["issues"])
                        if result["state"] == "revision_requested":
                            command("deliver", mode="normal" if case == "revision" else mode)
                            result = command("review"); failures.extend(result["issues"])
                order = asdict(market.order("demo"))
                expected = "accepted" if case in ("accepted", "revision") else "cancelled" if case in ("budget_refused", "cancelled") else "rejected"
                market.assert_invariants()
                reports.append({"vertical": vertical, "seed": seed, "case": case, "expected_state": expected,
                                "actual_state": order["state"], "expectation_met": order["state"] == expected,
                                "budget_credits": budget, "price_credits": order["quote"]["price"], "cost_credits": order["cost"],
                                "seller_net_credits": (order["quote"]["price"] if order["state"] == "accepted" else 0) - order["cost"],
                                "buyer_final_credits": market.balances["buyer"], "final_total_credits": sum(market.balances.values()),
                                "failure_evidence": failures, "journal": market.journal,
                                "synthetic_only": True, "real_market_validated": False})
    return {"schema": "product-campaign/v1", "synthetic_only": True, "seed_values": list(seeds),
            "design": "3 product verticals x 6 prespecified cases x seeds; seeds vary budget margin only, not learned behavior",
            "total_cases": len(reports), "expectations_met": sum(r["expectation_met"] for r in reports),
            "unexpected_failures": [r for r in reports if not r["expectation_met"]],
            "real_buyers": 0, "real_revenue": None, "real_market_validated": False, "cases": reports}


def main():
    parser = argparse.ArgumentParser(description="Original offline product samples and synthetic buyer acceptance; no real promotion")
    parser.add_argument("--output", required=True)
    parser.add_argument("--product-name", default=ORIGINAL_NAME)
    parser.add_argument("--template", help="Original editable PPTX template; default is bundled sample")
    args = parser.parse_args()
    try:
        manifest = build_bundle(args.output, name=args.product_name, template=args.template)
        report = run_campaign(args.output, name=args.product_name)
        (Path(args.output) / "campaign.json").write_text(stable_json(report), encoding="utf-8")
        manifest["mock_buyer_validation"] = {"case_count": report["total_cases"], "expectations_met": report["expectations_met"], "status": "completed"}
        manifest["campaign_sha256"] = file_digest(Path(args.output) / "campaign.json")
        (Path(args.output) / "manifest.json").write_text(stable_json(manifest), encoding="utf-8")
        print(stable_json({"output": str(Path(args.output)), "generated_files": len(manifest["files"]),
                           "synthetic_cases": report["total_cases"], "expected_outcomes": report["expectations_met"],
                           "real_market_validated": False, "video_rendered": False}))
        if report["unexpected_failures"]:
            parser.exit(1, "Unexpected synthetic acceptance failures; inspect campaign.json\n")
    except (OSError, ValueError, BadZipFile) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
