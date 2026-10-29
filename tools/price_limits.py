def check_price_limits(
    proposed: float,
    cost: float,
    day_start_price: float,
    min_margin_pct: float = 15.0,
    max_change_pct: float = 10.0,
) -> dict:
    violations = []
    floor = round(cost / (1 - min_margin_pct / 100), 2)
    lo = round(day_start_price * (1 - max_change_pct / 100), 2)
    hi = round(day_start_price * (1 + max_change_pct / 100), 2)

    if proposed < floor:
        violations.append(f"Below {min_margin_pct}% margin floor (${floor})")
    if not (lo <= proposed <= hi):
        violations.append(f"Outside +/-{max_change_pct}% daily band (${lo}-${hi})")

    safe = round(max(floor, min(hi, max(proposed, lo))), 2)
    return {
        "approved": len(violations) == 0,
        "violations": violations,
        "floor": floor,
        "band_low": lo,
        "band_high": hi,
        "safe_price": safe,
    }
