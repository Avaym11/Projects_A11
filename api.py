"""
EcomPriceAgent AI - FastAPI Backend
Run:   python -m uvicorn api:app --reload --port 8000
DB:    ecommerce.db (python db/init_db.py) - auto-created on first start if missing.
LLM:   set GEMINI_API_KEY in .env. Without it, the rule engine is used.

Design rule: the LLM only DECIDES (action + reasoning). All numbers
(prices, margins, FX, limits) are computed by plain Python code.
"""
import json, os, statistics
from contextlib import closing
from pathlib import Path
import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from db.init_db import init_db

BASE_DIR = Path(__file__).parent
os.chdir(BASE_DIR)
DB = os.getenv("DB_PATH", "ecommerce.db")

if not Path(DB).exists():
    init_db()

app = FastAPI(title="EcomPriceAgent AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Baseline competitor data per SKU. Scenarios mutate mock_prices from this.
BASELINE = {
    "P001": [("Amazon", 279.99, "USD"), ("Walmart", 289.00, "USD"), ("EU Store", 249.00, "EUR")],
    "P002": [("Amazon", 1149.00, "USD"), ("BestBuy", 1179.00, "USD"), ("EU Store", 1050.00, "EUR")],
    "P003": [("Amazon", 769.99, "USD"), ("Walmart", 749.00, "USD"), ("EU Store", 699.00, "EUR")],
    "P004": [("Amazon", 94.99, "USD"), ("Walmart", 89.00, "USD"), ("EU Store", 82.00, "EUR")],
    "P005": [("Amazon", 979.00, "USD"), ("BestBuy", 999.00, "USD"), ("EU Store", 899.00, "EUR")],
}
RATE_LIMITED = set()  # {(product_id, competitor)} simulating HTTP 429

FX_RATES = {"USD": 1.0, "EUR": 1.09}


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# TOOLS (plain code, no LLM)
# --------------------------------------------------------------------------
def calc_margin(price: float, cogs: float) -> float:
    return round((price - cogs) / price * 100, 2)


def min_floor(cogs: float, margin_pct: float) -> float:
    return round(cogs / (1 - margin_pct / 100), 2)


def get_product(con, product_id):
    r = con.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    if not r:
        raise HTTPException(404, f"Unknown product {product_id}")
    return dict(r)


def get_competitor_rows(con, product_id):
    return con.execute(
        "SELECT * FROM mock_prices WHERE product_id=? ORDER BY id", (product_id,)
    ).fetchall()


def lowest_competitor_usd(con, product_id):
    rows = con.execute(
        "SELECT price, currency FROM mock_prices WHERE product_id=? AND in_stock=1", (product_id,)
    ).fetchall()
    vals = [round(r["price"] * FX_RATES.get(r["currency"], 1.0), 2) for r in rows]
    return min(vals) if vals else None


class MockStore:
    def update_price(self, product_id, new_price):
        with closing(db()) as con:
            con.execute("UPDATE products SET our_price=? WHERE id=?", (new_price, product_id))
            con.commit()


class ShopifyStore:  # stub for the pitch
    def update_price(self, product_id, new_price):
        raise NotImplementedError("Connect Shopify Admin API here (future scope).")


STORE = MockStore()


def record_change(con, product_id, old, new, by, reason, status, intercepted):
    con.execute(
        "INSERT INTO price_history (product_id, old_price, new_price, decided_by, reason) VALUES (?,?,?,?,?)",
        (product_id, old, new, by, reason),
    )
    if new != old:
        lo = lowest_competitor_usd(con, product_id)
        con.execute(
            "INSERT INTO audit_log (ts, product_id, old_price, new_price, decided_by, reason, status, intercepted) VALUES (?,?,?,?,?,?,?,?)",
            (now(), product_id, old, new, by, reason, status, int(intercepted)),
        )
    con.commit()


# --------------------------------------------------------------------------
# AGENT 1: SCOUT
# --------------------------------------------------------------------------
def scout(product_id):
    trace, out = [], []
    with closing(db()) as con:
        rows = get_competitor_rows(con, product_id)
    for r in rows:
        rate = FX_RATES.get(r["currency"], 1.0)
        if (product_id, r["competitor"]) in RATE_LIMITED:
            for w in (1, 2, 4):
                trace.append(f"Scout: {r['competitor']} returned 429. Backing off {w}s (simulated).")
            trace.append(f"Scout: still blocked. Using cached price and marking it STALE.")
            cached = r["cached_price"] if r["cached_price"] else r["price"]
            out.append({"n": r["competitor"], "usd": round(cached * rate, 2),
                        "s": "Out of Stock" if not r["in_stock"] else "In Stock", "stale": True})
        else:
            status = r["status"] if "status" in r.keys() else ("In Stock" if r["in_stock"] else "Out of Stock")
            out.append({"n": r["competitor"], "usd": round(r["price"] * rate, 2), "s": status, "stale": False})
    trace.append("Scout: loaded " + ", ".join(f"{c['n']} ${c['usd']}" for c in out))
    return out, trace


# --------------------------------------------------------------------------
# AGENTS — imported from agents/ package (single source of truth)
# --------------------------------------------------------------------------
from agents import strategist as strategist_agent
from agents import guardrail as guardrail_agent


def _to_agent_comps(comps):
    """Convert api.py scout output format → agents/ package format."""
    return [
        {
            "competitor": c["n"],
            "usd_price": c["usd"],
            "in_stock": c["s"] not in ("Out of Stock",),
            "promo": "flash_sale" if c["s"] == "Flash Sale" else None,
            "stale": c["stale"],
        }
        for c in comps
    ]


# --------------------------------------------------------------------------
# API MODELS
# --------------------------------------------------------------------------
class SkuReq(BaseModel):
    sku: str

class ScenarioReq(BaseModel):
    sku: str
    scenario: str  # normal | oos | glitch | flash | margin | ratelimit

class DecideReq(BaseModel):
    decision: str  # approve | safe | reject

class StrategistReq(BaseModel):
    product: str = ""
    ourPrice: float
    cogs: float = 0
    competitors: List[dict]

class GuardrailConfig(BaseModel):
    min_margin_pct: float = 15.0
    max_daily_change_pct: float = 10.0


# --------------------------------------------------------------------------
# ENDPOINTS
# --------------------------------------------------------------------------
@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(str(BASE_DIR / "dashboard" / "favicon.ico")) if (BASE_DIR / "dashboard" / "favicon.ico").exists() else HTTPException(404)


@app.get("/")
def home():
    p = BASE_DIR / "dashboard" / "index.html"
    return FileResponse(str(p)) if p.exists() else {"status": "API running. See /docs"}


@app.get("/api/state/{product_id}")
def state(product_id: str):
    with closing(db()) as con:
        p = get_product(con, product_id)
        rows = get_competitor_rows(con, product_id)
        comps = [{"competitor": r["competitor"], "price": r["price"], "currency": r["currency"],
                  "usd": round(r["price"] * FX_RATES.get(r["currency"], 1.0), 2),
                  "in_stock": bool(r["in_stock"]),
                  "status": r["status"] if "status" in r.keys() else ("In Stock" if r["in_stock"] else "Out of Stock"),
                  "rate_limited": (product_id, r["competitor"]) in RATE_LIMITED}
                 for r in rows]
        hist = [dict(r) for r in con.execute(
            "SELECT timestamp, new_price FROM price_history WHERE product_id=? ORDER BY id", (product_id,))]
        live = [c["usd"] for c in comps if c["in_stock"]]
        med = statistics.median(live) if live else p["our_price"]
        mk = statistics.mean([x for x in live if x >= med * 0.5] or [p["our_price"]])
        profit = lambda pr: round(100 * (mk / pr) ** 2 * (pr - p["cost"]), 2)
        return {"product": {**p, "margin_pct": calc_margin(p["our_price"], p["cost"]),
                            "floor_price": min_floor(p["cost"], 15.0)},
                "competitors": comps, "history": hist,
                "metrics": {"agent_profit_per_day": profit(p["our_price"]),
                            "static_profit_per_day": profit(p["our_price"])}}


@app.post("/api/scenario")
def scenario(req: ScenarioReq):
    pid, s = req.sku, req.scenario
    if pid not in BASELINE:
        raise HTTPException(400, f"Unknown product {pid}")
    with closing(db()) as con:
        p = get_product(con, pid)
        o, fx = p["our_price"], 1.09
        RATE_LIMITED.difference_update({k for k in RATE_LIMITED if k[0] == pid})
        prices = {n: [pr, "In Stock"] for n, pr, _ in BASELINE[pid]}
        if s == "normal":
            prices["Amazon"][0] = round(o * 0.93, 2)
        elif s == "oos":
            prices["Amazon"] = [round(o * 0.90, 2), "Out of Stock"]
            prices[list(prices.keys())[1]][0] = round(o * 1.02, 2)
            prices[list(prices.keys())[2]][0] = round(o * 1.04 / fx, 2)
        elif s == "glitch":
            prices[list(prices.keys())[1]][0] = 5.00
        elif s == "flash":
            prices["Amazon"][0] = round(o * 1.02, 2)
            prices[list(prices.keys())[1]][0] = round(o * 1.04, 2)
            prices[list(prices.keys())[2]] = [round(o * 0.88 / fx, 2), "Flash Sale"]
        elif s == "margin":
            prices["Amazon"][0] = round(p["cost"] * 1.05, 2)
        elif s == "ratelimit":
            RATE_LIMITED.add((pid, "Amazon"))
            con.execute("UPDATE mock_prices SET cached_price=? WHERE product_id=? AND competitor='Amazon'",
                        (round(o * 0.97, 2), pid))
        else:
            raise HTTPException(400, "Unknown scenario")
        for name, (pr, st) in prices.items():
            con.execute("UPDATE mock_prices SET price=?, in_stock=?, status=? WHERE product_id=? AND competitor=?",
                        (pr, 0 if st == "Out of Stock" else 1, st, pid, name))
        con.commit()
    return {"ok": True, "scenario": s}


@app.post("/api/strategist")
def strategist_endpoint(req: StrategistReq):
    # Accept either dashboard format {n, usd, s, stale} or agent format {competitor, usd_price, ...}
    agent_comps = []
    for c in req.competitors:
        if "n" in c:  # dashboard/scout format → convert
            agent_comps.append({
                "competitor": c["n"], "usd_price": c.get("usd", 0),
                "in_stock": c.get("s") not in ("Out of Stock",),
                "promo": "flash_sale" if c.get("s") == "Flash Sale" else None,
                "stale": c.get("stale", False),
            })
        else:  # already in agent format
            agent_comps.append(c)
    d = strategist_agent.run(req.product, req.ourPrice, req.cogs, agent_comps)
    return {"action": d["action"], "target": d["proposed_price"], "reason": d["reason"],
            "flagged": d["action"] == "IGNORE_GLITCH", "source": d["source"]}


@app.post("/api/run")
def run_pipeline(req: SkuReq):
    pid = req.sku
    trace = []
    comps, t = scout(pid)
    trace += t
    with closing(db()) as con:
        p = get_product(con, pid)
        # Convert to agents/ format, then run through the imported agent modules
        agent_comps = _to_agent_comps(comps)
        st_raw = strategist_agent.run(pid, p["our_price"], p["cost"], agent_comps)
        target  = st_raw["proposed_price"]
        flagged = st_raw["action"] == "IGNORE_GLITCH"
        st = {"action": st_raw["action"], "target": target,
              "reason": st_raw["reason"], "source": st_raw["source"], "flagged": flagged}
        trace.append(f"Strategist ({st['source']}): {st['action']} -> ${target}. {st['reason']}")

        g_raw = guardrail_agent.run(target, p["cost"], p["our_price"], agent_comps)
        g = {"ok": g_raw["approved"], "violations": g_raw["violations"],
             "safe_price": g_raw["safe_price"], "floor": g_raw["floor"],
             "band": [g_raw["band_low"], g_raw["band_high"]]}

        if target == p["our_price"]:
            trace.append("Guardrail: no price change proposed.")
            status = "Flagged" if flagged else "Held"
            record_change(con, pid, p["our_price"], p["our_price"], "Strategist", st["reason"], status, flagged)
            result = {"status": "NO_CHANGE"}
        elif g["ok"]:
            trace.append(f"Guardrail: passed (floor ${g['floor']}, band ${g['band'][0]}-${g['band'][1]}).")
            STORE.update_price(pid, target)
            record_change(con, pid, p["our_price"], target, "Strategist + Guardrail", st["reason"], "Auto-Approved", flagged)
            trace.append(f"Store: {pid} -> ${target}")
            result = {"status": "APPLIED", "new_price": target}
        else:
            trace.append("Guardrail: CIRCUIT BREAKER. " + "; ".join(g["violations"]))
            cur = con.execute(
                "INSERT INTO pending_approvals (product_id, proposed_price, safe_price, reason, flag) VALUES (?,?,?,?,?)",
                (pid, target, g["safe_price"], st["reason"], "; ".join(g["violations"])))
            con.commit()
            result = {"status": "NEEDS_APPROVAL", "approval_id": cur.lastrowid,
                      "proposed_price": target, "safe_price": g["safe_price"],
                      "violations": g["violations"]}

    RATE_LIMITED.difference_update({k for k in RATE_LIMITED if k[0] == pid})
    return {**result, "strategy": st, "guardrail": g, "trace": trace}


@app.get("/api/approvals")
def approvals(status: Optional[str] = "pending"):
    with closing(db()) as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM pending_approvals WHERE status=? ORDER BY id DESC", (status,))]


@app.post("/api/approvals/{approval_id}/decide")
def decide(approval_id: int, req: DecideReq):
    with closing(db()) as con:
        a = con.execute("SELECT * FROM pending_approvals WHERE id=?", (approval_id,)).fetchone()
        if not a:
            raise HTTPException(404, "Approval not found")
        if a["status"] != "pending":
            raise HTTPException(409, "Already decided")
        p = get_product(con, a["product_id"])
        if req.decision == "reject":
            con.execute("UPDATE pending_approvals SET status='rejected' WHERE id=?", (approval_id,))
            record_change(con, a["product_id"], p["our_price"], p["our_price"], "Human", a["flag"], "Rejected", True)
            return {"status": "REJECTED", "price": p["our_price"]}
        if req.decision not in ("approve", "safe"):
            raise HTTPException(400, "decision must be approve | safe | reject")
        new = a["proposed_price"] if req.decision == "approve" else a["safe_price"] if a["safe_price"] else p["our_price"]
        STORE.update_price(a["product_id"], new)
        con.execute("UPDATE pending_approvals SET status=? WHERE id=?",
                    ("approved" if req.decision == "approve" else "safe_applied", approval_id))
        record_change(con, a["product_id"], p["our_price"], new, "Human override",
                      f"{a['reason']} [{a['flag']}]",
                      "Approved (human)" if req.decision == "approve" else "Safe price (human)", True)
        return {"status": "APPLIED", "price": new}


@app.get("/api/audit")
def audit(limit: int = 50):
    with closing(db()) as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]


@app.post("/api/reset")
def reset():
    RATE_LIMITED.clear()
    init_db()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)

