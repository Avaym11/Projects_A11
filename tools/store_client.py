import sqlite3, os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "ecommerce.db")


class MockStore:
    def update_price(self, product_id: str, new_price: float, decided_by: str, reason: str):
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT our_price FROM products WHERE id=?", (product_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"error": f"Product {product_id} not found"}
        old_price = row[0]
        cur.execute("UPDATE products SET our_price=? WHERE id=?", (new_price, product_id))
        cur.execute(
            "INSERT INTO price_history (product_id, old_price, new_price, decided_by, reason) VALUES (?,?,?,?,?)",
            (product_id, old_price, new_price, decided_by, reason),
        )
        conn.commit()
        conn.close()
        return {"product_id": product_id, "old_price": old_price, "new_price": new_price, "status": "updated"}


class ShopifyStore:
    """Stub — swap MockStore for this in production."""
    def update_price(self, product_id: str, new_price: float, decided_by: str, reason: str):
        raise NotImplementedError("Connect Shopify API here")


def update_price(product_id: str, new_price: float, decided_by: str, reason: str) -> dict:
    return MockStore().update_price(product_id, new_price, decided_by, reason)
