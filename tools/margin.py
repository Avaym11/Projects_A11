def calc_margin(price: float, cost: float) -> dict:
    if price <= 0:
        return {"error": "Price must be greater than 0"}
    margin_pct = round((price - cost) / price * 100, 2)
    profit = round(price - cost, 2)
    return {"price": price, "cost": cost, "profit": profit, "margin_pct": margin_pct}
