import time

_MOCK_DATA = {
    "P001": [
        {"competitor": "Amazon",  "price": 279.99, "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "Walmart", "price": 289.00, "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "EU Store","price": 249.00, "currency": "EUR", "in_stock": True,  "promo": None},
    ],
    "P002": [
        {"competitor": "Amazon",  "price": 1149.00,"currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "BestBuy", "price": 1179.00,"currency": "USD", "in_stock": False, "promo": None},
        {"competitor": "EU Store","price": 1050.00,"currency": "EUR", "in_stock": True,  "promo": "flash_sale"},
    ],
    "P003": [
        {"competitor": "Amazon",  "price": 769.99, "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "Walmart", "price": 749.00, "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "EU Store","price": 699.00, "currency": "EUR", "in_stock": False, "promo": None},
    ],
    "P004": [
        {"competitor": "Amazon",  "price": 94.99,  "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "Walmart", "price": 89.00,  "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "EU Store","price": 82.00,  "currency": "EUR", "in_stock": True,  "promo": None},
    ],
    "P005": [
        {"competitor": "Amazon",  "price": 979.00, "currency": "USD", "in_stock": True,  "promo": None},
        {"competitor": "BestBuy", "price": 999.00, "currency": "USD", "in_stock": False, "promo": None},
        {"competitor": "EU Store","price": 899.00, "currency": "EUR", "in_stock": True,  "promo": "flash_sale"},
    ],
}

_last_known = {}

def get_competitor_prices(product_id: str) -> dict:
    data = _MOCK_DATA.get(product_id)
    if not data:
        return {"error": f"No competitor data for {product_id}"}
    results = [{**e, "stale": False, "fetched_at": time.time()} for e in data]
    _last_known[product_id] = results
    return {"product_id": product_id, "competitors": results}
