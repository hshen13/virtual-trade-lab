import argparse
import json
from dataclasses import asdict
from . import CatalogBuyer, CatalogSeller, Market, TradeError

SOURCE = [
    {"sku": "CUP-01", "title": "  Ceramic   cup  ", "price_cents": 1299},
    {"sku": "BAG-02", "title": "Canvas\t tote", "price_cents": 2499},
]


def run_scenario(name):
    market = Market(CatalogSeller(), CatalogBuyer())
    evidence = []
    counter = 0

    def command(action, **payload):
        nonlocal counter
        counter += 1
        return market.execute(action, "demo", f"{name}-{counter}", **payload)

    criteria = {"budget": 5 if name == "budget" else 40,
                "max_revisions": 1}
    command("quote", source=SOURCE, criteria=criteria)
    try:
        command("fund")
    except TradeError as exc:
        evidence.append(str(exc))
        command("cancel")
    else:
        if name == "cancel":
            command("cancel")
        else:
            mode = {"revision": "defective", "reject": "defective", "crash": "crash"}.get(name, "normal")
            command("deliver", mode=mode)
            reviewed = command("review")
            evidence.extend(reviewed["issues"])
            if reviewed["state"] == "revision_requested":
                command("deliver", mode="normal" if name == "revision" else mode)
                reviewed = command("review")
                evidence.extend(reviewed["issues"])
    market.assert_invariants()
    order = asdict(market.order("demo"))
    revenue = order["quote"]["price"] if order["state"] == "accepted" else 0
    return {"scenario": name, "simulated_only": True, "order": order,
            "seller": {"revenue_credits": revenue, "cost_credits": order["cost"],
                       "net_credits": revenue - order["cost"]},
            "balances": market.balances, "initial_total": market.initial_total,
            "final_total": sum(market.balances.values()), "evidence": evidence,
            "events": market.events, "journal": market.journal}


def main():
    parser = argparse.ArgumentParser(description="Virtual Trade Lab — simulation, NOT real payment")
    parser.add_argument("--scenario", choices=["all", "happy", "revision", "reject", "cancel", "budget", "crash"], default="all")
    parser.add_argument("--json", action="store_true", help="machine-readable evidence on stdout")
    args = parser.parse_args()
    names = ["happy", "revision", "reject", "cancel", "budget", "crash"] if args.scenario == "all" else [args.scenario]
    reports = [run_scenario(name) for name in names]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return
    print("Virtual Trade Lab | 纯模拟积分，不是真实交易、收入或商业验证\n")
    for report in reports:
        order, seller = report["order"], report["seller"]
        print(f"[{report['scenario']}] " + " → ".join(event["state"] for event in report["events"]))
        print(f"  报价 {order['quote']['price']} | 成本 {seller['cost_credits']} | 卖家净变动 {seller['net_credits']:+d}")
        print(f"  积分守恒 {report['initial_total']} = {report['final_total']} | 余额 {report['balances']}")
        if report["evidence"]:
            print("  失败/返工证据: " + "; ".join(report["evidence"]))
        if order["state"] == "accepted":
            print("  交付: " + json.dumps(order["result"], ensure_ascii=False))
        print()


if __name__ == "__main__":
    main()
