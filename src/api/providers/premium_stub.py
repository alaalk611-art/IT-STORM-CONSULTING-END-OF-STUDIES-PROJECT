import os
from typing import List

import httpx

from src.api.models import OHLCV, Candle, Quote, SearchResult
from src.api.providers.base import MarketDataProvider


class PremiumProvider(MarketDataProvider):
    \"""
    Exemple de squelette si tu branches TwelveData / Polygon / EODHD (clé API requise).
    \"""
    name = "premium"

    def __init__(self):
        self.api_key = os.getenv("PREMIUM_API_KEY", "")
        self.base_url = "https://api.twelvedata.com"  # exemple

    async def quote(self, symbol: str) -> Quote:
        if not self.api_key:
            raise RuntimeError("PREMIUM_API_KEY manquante")
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{self.base_url}/quote", params={"symbol": symbol, "apikey": self.api_key})
            r.raise_for_status()
            j = r.json()
            price = float(j["price"])
            change = float(j.get("change", 0) or 0)
            change_pct = float(j.get("percent_change", 0) or 0)
            return Quote(symbol=symbol, price=price, change=change, change_percent=change_pct,
                         currency=j.get("currency"), exchange=j.get("exchange"), is_delayed=False)

    async def ohlcv(self, symbol: str, interval: str = "1min", range_: str = "1day") -> OHLCV:
        raise NotImplementedError

    async def search(self, query: str) -> List[SearchResult]:
        raise NotImplementedError