"""
BCOS Search Tool

Routing:
- Bitcoin price query -> CoinGecko structured API
- General query -> DuckDuckGo

The public interface remains:

    SearchTool().run(query)
"""

import json
import urllib.request

from ddgs import DDGS

from config import SEARCH_RESULTS


class SearchTool:

    name = "search"

    def __init__(self):
        self.client = DDGS()

    # =====================================================
    # RUN
    # =====================================================

    def run(self, query):

        if self.is_bitcoin_price_query(query):
            return self.bitcoin_price()

        return self.web_search(query)

    # =====================================================
    # QUERY CLASSIFICATION
    # =====================================================

    def is_bitcoin_price_query(self, query):

        q = str(query).lower().strip()

        bitcoin_terms = [
            "bitcoin",
            "btc",
            "giá bitcoin",
            "gia bitcoin",
            "giá btc",
            "gia btc",
        ]

        price_terms = [
            "giá",
            "gia",
            "price",
            "bao nhiêu",
            "bao nhieu",
            "hiện tại",
            "hien tai",
            "hôm nay",
            "hom nay",
            "today",
            "current",
            "realtime",
            "real-time",
        ]

        has_bitcoin = any(
            term in q
            for term in bitcoin_terms
        )

        has_price = any(
            term in q
            for term in price_terms
        )

        return (
            has_bitcoin
            and has_price
        )

    # =====================================================
    # BITCOIN PRICE
    # =====================================================

    def bitcoin_price(self):

        url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin"
            "&vs_currencies=usd,vnd"
            "&include_24hr_change=true"
        )

        try:

            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "BCOS-Agent/1.0",
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=10,
            ) as response:

                raw = response.read().decode(
                    "utf-8"
                )

                data = json.loads(
                    raw
                )

            bitcoin = data.get(
                "bitcoin",
                {}
            )

            price_usd = bitcoin.get(
                "usd"
            )

            price_vnd = bitcoin.get(
                "vnd"
            )

            change_24h = bitcoin.get(
                "usd_24h_change"
            )

            if price_usd is None:

                raise ValueError(
                    "Bitcoin price missing "
                    "from CoinGecko response"
                )

            return {

                "success": True,

                "source": "CoinGecko",

                "data_type":
                    "crypto_price",

                "asset":
                    "Bitcoin",

                "symbol":
                    "BTC",

                "price_usd":
                    price_usd,

                "price_vnd":
                    price_vnd,

                "change_24h_percent":
                    change_24h,

                "confidence":
                    "high",
            }

        except Exception as e:

            return {

                "success": False,

                "source": "CoinGecko",

                "data_type":
                    "crypto_price",

                "asset":
                    "Bitcoin",

                "symbol":
                    "BTC",

                "error":
                    str(e),
            }

    # =====================================================
    # GENERAL WEB SEARCH
    # =====================================================

    def web_search(self, query):

        try:

            results = []

            data = self.client.text(
                query,
                max_results=SEARCH_RESULTS,
            )

            for item in data:

                results.append({

                    "title":
                        item.get(
                            "title",
                            ""
                        ),

                    "url":
                        item.get(
                            "href",
                            ""
                        ),

                    "content":
                        item.get(
                            "body",
                            ""
                        ),
                })

            return {

                "success":
                    True,

                "source":
                    "DuckDuckGo",

                "query":
                    query,

                "count":
                    len(results),

                "results":
                    results,
            }

        except Exception as e:

            return {

                "success":
                    False,

                "source":
                    "DuckDuckGo",

                "query":
                    query,

                "error":
                    str(e),

                "results":
                    [],
            }
