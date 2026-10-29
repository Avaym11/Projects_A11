from tools.store_client import update_price


def run(product_id: str, new_price: float, decided_by: str, reason: str) -> dict:
    result = update_price(product_id, new_price, decided_by, reason)
    if "error" in result:
        print(f"[StoreManager] ERROR: {result['error']}")
    else:
        print(f"[StoreManager] Updated {product_id}: ${result['old_price']} -> ${result['new_price']} (by {decided_by})")
    return result
