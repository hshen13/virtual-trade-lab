"""Example adapter only: normalize catalog whitespace, never invent product facts."""
import re
from .core import Criteria, Quote, TradeError, whole


class CatalogSeller:
    name = "catalog-whitespace-v1"

    def quote(self, source):
        seen = set()
        for row in source:
            if set(row) != {"sku", "title", "price_cents"}:
                raise TradeError("catalog rows require exactly sku, title, price_cents")
            if not isinstance(row["sku"], str) or not row["sku"].strip() or row["sku"] in seen:
                raise TradeError("sku must be nonempty and unique")
            if not isinstance(row["title"], str) or not row["title"].strip():
                raise TradeError("title must be nonempty")
            whole(row["price_cents"], "price_cents")
            seen.add(row["sku"])
        return Quote(price=10 + 5 * len(source), cost_per_attempt=2 + len(source), service=self.name)

    def fulfill(self, source, attempt, mode):
        if mode == "crash":
            raise RuntimeError("injected adapter failure")
        result = [{**row, "title": re.sub(r"\s+", " ", row["title"]).strip()} for row in source]
        if mode == "defective":
            result[0]["price_cents"] += 1  # Explicit fault injection, not hidden fake success.
        return result


class CatalogBuyer:
    """Separate oracle: checks source preservation and buyer-owned constraints."""
    def assess(self, source, result, criteria: Criteria):
        issues = []
        original = {row["sku"]: row for row in source}
        seen = set()
        if len(result) != len(source):
            issues.append("row count changed")
        for row in result:
            if set(row) != {"sku", "title", "price_cents"}:
                issues.append("unexpected output schema")
                continue
            sku = row["sku"]
            if not isinstance(sku, str) or sku not in original or sku in seen:
                issues.append("missing, unknown, or duplicate SKU")
                continue
            seen.add(sku)
            prior = original[sku]
            if type(row["price_cents"]) is not int or row["price_cents"] != prior["price_cents"]:
                issues.append(f"{sku}: product price changed")
            title = row["title"]
            if not isinstance(title, str):
                issues.append(f"{sku}: title is not text")
                continue
            expected = " ".join(prior["title"].split())
            if title != expected:
                issues.append(f"{sku}: title not normalized or content changed")
            if len(title) > criteria.max_title_length:
                issues.append(f"{sku}: title too long")
        if seen != set(original):
            issues.append("SKU coverage incomplete")
        return issues
