import os, requests
from dotenv import load_dotenv

load_dotenv()
_API_KEY = os.getenv("EXCHANGE_RATE_API_KEY")
_cache = {}

# Hardcoded fallback rates used when the API key is missing or the call fails.
_FALLBACK_RATES = {"EUR_USD": 1.09, "GBP_USD": 1.27, "INR_USD": 0.012}

def convert_currency(amount: float, from_currency: str, to_currency: str = "USD") -> float:
    if from_currency == to_currency:
        return round(amount, 2)
    key = f"{from_currency}_{to_currency}"
    if key not in _cache:
        if _API_KEY:
            try:
                url = f"https://v6.exchangerate-api.com/v6/{_API_KEY}/pair/{from_currency}/{to_currency}"
                r = requests.get(url, timeout=5)
                r.raise_for_status()
                _cache[key] = r.json()["conversion_rate"]
            except Exception as e:
                print(f"[Currency] FX API failed ({e}). Using fallback rate for {key}.")
                _cache[key] = _FALLBACK_RATES.get(key, 1.0)
        else:
            print(f"[Currency] No EXCHANGE_RATE_API_KEY set. Using fallback rate for {key}.")
            _cache[key] = _FALLBACK_RATES.get(key, 1.0)
    return round(amount * _cache[key], 2)
