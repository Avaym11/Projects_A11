import os, json, statistics, time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tools.margin import calc_margin

load_dotenv()
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Model cascade: Agent 2 tries each model in order before falling back to rules.
# gemini-3.8-flash       → primary: fast & cheap (Free Tier supported)
# gemini-3.5-flash-lite  → secondary: fast & lightweight fallback model
# Rule engine            → final guaranteed fallback (no API needed)
_MODEL_CASCADE = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]

# Hard cap per model attempt: abandon if no response within 20s
_TIMEOUT_MS = 20_000


def _fallback_rules(our_price: float, competitors: list) -> dict:
    prices = [c["usd_price"] for c in competitors]
    median = statistics.median(prices)
    valid = [c for c in competitors if c["usd_price"] >= median * 0.5]
    in_stock = [c for c in valid if c["in_stock"] and c["promo"] != "flash_sale"]
    oos = [c for c in valid if not c["in_stock"]]
    flash = [c for c in valid if c["promo"] == "flash_sale"]
    anomalies = [c for c in competitors if c["usd_price"] < median * 0.5]

    if anomalies:
        names = ", ".join(c["competitor"] for c in anomalies)
        return {"action": "IGNORE_GLITCH", "proposed_price": our_price,
                "reason": f"Ignored {names} — price looks like a data error (below 50% of median ${median:.2f})."}

    if oos and not in_stock:
        return {"action": "RAISE_PRICE", "proposed_price": round(our_price * 1.08, 2),
                "reason": "All competitors out of stock; raising price 8%."}

    if flash and not in_stock:
        return {"action": "HOLD", "proposed_price": our_price,
                "reason": "Competitor flash sale is temporary; holding price."}

    if in_stock:
        lowest = min(in_stock, key=lambda c: c["usd_price"])
        if lowest["usd_price"] < our_price:
            return {"action": "MATCH", "proposed_price": round(lowest["usd_price"] - 0.01, 2),
                    "reason": f"{lowest['competitor']} has sustained lower price at ${lowest['usd_price']}; undercutting by $0.01."}

    return {"action": "HOLD", "proposed_price": our_price, "reason": "Already competitive; no change needed."}


def _try_model(model: str, prompt: str) -> dict:
    """Attempt a single Gemini model call. Raises on failure."""
    response = _client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            http_options=types.HttpOptions(timeout=_TIMEOUT_MS)
        ),
    )
    text = response.text.strip().strip("```json").strip("```").strip()
    result = json.loads(text)
    if result["action"] not in {"HOLD", "MATCH", "RAISE_PRICE", "IGNORE_GLITCH"}:
        raise ValueError(f"Invalid action: {result['action']}")
    return result


def run(product_id: str, our_price: float, cost: float, competitors: list) -> dict:
    margin = calc_margin(our_price, cost)
    comp_summary = "\n".join(
        f"- {c['competitor']}: ${c['usd_price']} | in_stock={c['in_stock']} | promo={c['promo']} | stale={c['stale']}"
        for c in competitors
    )

    prompt = f"""You are a pricing strategist for an e-commerce store.

Product: {product_id}
Our price: ${our_price} | Cost: ${cost} | Margin: {margin['margin_pct']}%

Competitor prices (all in USD):
{comp_summary}

Rules you must follow:
1. If a competitor price looks like a data error (e.g. $5 for a $200 item), ignore it and flag it.
2. If a competitor is out of stock, consider raising or holding our price instead of matching.
3. If a competitor is in a flash sale, wait — do not react to temporary drops.
4. Only propose matching a real, sustained, in-stock competitor price.

Respond ONLY with valid JSON in this exact format:
{{"action": "HOLD|MATCH|RAISE_PRICE|IGNORE_GLITCH", "proposed_price": <float>, "reason": "<one sentence>"}}"""

    # ── Model cascade: try each model once before giving up ──────────────────
    for model in _MODEL_CASCADE:
        try:
            result = _try_model(model, prompt)
            result["source"] = model
            print(f"[Strategist] {model} -> {result['action']} @ ${result['proposed_price']}: {result['reason']}")
            return result
        except Exception as e:
            print(f"[Strategist] {model} failed ({type(e).__name__}: {e}). "
                  f"{'Trying next model...' if model != _MODEL_CASCADE[-1] else 'All models exhausted.'}")
            time.sleep(1)  # brief pause before trying the next model
    # ─────────────────────────────────────────────────────────────────────────

    print("[Strategist] Falling back to deterministic rule engine.")
    result = _fallback_rules(our_price, competitors)
    result["source"] = "fallback (rule engine)"
    return result
