from tools.competitor_data import get_competitor_prices
from tools.currency import convert_currency


def run(product_id: str) -> dict:
    result = get_competitor_prices(product_id)
    if "error" in result:
        return result

    normalized = []
    for c in result["competitors"]:
        usd_price = convert_currency(c["price"], c["currency"], "USD")
        normalized.append({
            "competitor": c["competitor"],
            "original_price": c["price"],
            "currency": c["currency"],
            "usd_price": usd_price,
            "in_stock": c["in_stock"],
            "promo": c["promo"],
            "stale": c["stale"],
        })

    print(f"[Scout] Fetched {len(normalized)} competitors for {product_id}")
    for c in normalized:
        tag = " (STALE)" if c["stale"] else ""
        print(f"  {c['competitor']}: ${c['usd_price']} | stock={c['in_stock']} | promo={c['promo']}{tag}")

    return {"product_id": product_id, "competitors": normalized}
