import sqlite3, os
from dotenv import load_dotenv
from db.init_db import init_db
import agents.scout as scout
import agents.strategist as strategist
import agents.guardrail as guardrail
import agents.store_manager as store_manager

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "ecommerce.db")


def get_products():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, name, our_price, cost FROM products").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "our_price": r[2], "cost": r[3]} for r in rows]


def get_day_start_price(product_id: str, current_price: float) -> float:
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT old_price FROM price_history WHERE product_id=? ORDER BY timestamp DESC LIMIT 1",
        (product_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else current_price


def run_pipeline(product: dict, human_approval_fn=None):
    pid = product["id"]
    print(f"\n{'='*55}")
    print(f"Pipeline: {product['name']} (${product['our_price']})")
    print(f"{'='*55}")

    # Agent 1: Scout
    scout_result = scout.run(pid)
    if "error" in scout_result:
        print(f"[Pipeline] Scout failed: {scout_result['error']}")
        return

    competitors = scout_result["competitors"]

    # Agent 2: Strategist
    strat_result = strategist.run(pid, product["our_price"], product["cost"], competitors)
    proposed = strat_result["proposed_price"]
    reason = strat_result["reason"]
    action = strat_result["action"]

    if action in ("HOLD", "IGNORE_GLITCH") or proposed == product["our_price"]:
        print(f"[Pipeline] No price change needed. Reason: {reason}")
        return

    # Agent 3: Guardrail
    day_start = get_day_start_price(pid, product["our_price"])
    guard_result = guardrail.run(proposed, product["cost"], day_start, competitors)

    if guard_result["approved"]:
        store_manager.run(pid, proposed, f"Strategist({strat_result['source']})+Guardrail", reason)
    else:
        print(f"[Pipeline] Circuit breaker tripped. Violations: {guard_result['violations']}")
        if human_approval_fn:
            decision = human_approval_fn(product, strat_result, guard_result)
            if decision == "approve":
                store_manager.run(pid, proposed, "Human(approved)", reason)
            elif decision == "safe":
                store_manager.run(pid, guard_result["safe_price"], "Human(safe)", reason)
            else:
                print("[Pipeline] Human rejected. Price unchanged.")
        else:
            print(f"[Pipeline] Auto-applying safe price ${guard_result['safe_price']}.")
            store_manager.run(pid, guard_result["safe_price"], "Guardrail(safe)", reason)


def human_approval_cli(product, strat, guard):
    print(f"\n🚨 HUMAN APPROVAL REQUIRED")
    print(f"  Product : {product['name']}")
    print(f"  Proposed: ${strat['proposed_price']}  |  Safe: ${guard['safe_price']}")
    print(f"  Reason  : {strat['reason']}")
    print(f"  Violations: {', '.join(guard['violations'])}")
    choice = input("  Decision [approve / safe / reject]: ").strip().lower()
    return choice if choice in ("approve", "safe", "reject") else "reject"


if __name__ == "__main__":
    init_db()
    products = get_products()
    for p in products:
        run_pipeline(p, human_approval_fn=human_approval_cli)
