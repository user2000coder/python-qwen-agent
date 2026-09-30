"""
BCOS Search Tool

Routing:
- Bitcoin price query -> CoinGecko structured API
- General query -> DuckDuckGo

The public interface remains:

    SearchTool().run(query)
"""

import json
import re
import time
import unicodedata
import urllib.request

from ddgs import DDGS

# DDGS is a lazy proxy; ddgs.__all__ is ("DDGS",) only, so the
# exceptions have to come from the submodule.
from ddgs.exceptions import DDGSException

from config import (
    SEARCH_BACKEND,
    SEARCH_REGION,
    SEARCH_RESULTS,
    SEARCH_RETRIES,
    SEARCH_TIMEOUT,
)


class SearchTool:

    name = "search"

    # A DDGS instance caches one engine object per backend, each
    # holding an HTTP client whose impersonated fingerprint and
    # cookie jar are fixed at construction. A process-lifetime
    # instance therefore keeps sending the same fingerprint, so a
    # provider that blocks it stays blocked for the whole run.
    # A per-call client re-rolls it and avoids the library's
    # unsynchronised engine cache.

    # =====================================================
    # RUN
    # =====================================================

    def run(self, query):

        if self.is_bitcoin_price_query(query):
            return self.bitcoin_price(query)

        return self.web_search(query)

    # =====================================================
    # QUERY CLASSIFICATION
    # =====================================================

    # Matched on word boundaries, against diacritic-folded text.
    #
    # The previous bare-substring test matched "gia" inside
    # "giao dịch", "tham gia", "quốc gia" and "Georgia", so
    # roughly 8 of 11 realistic Bitcoin questions were treated as
    # price lookups: the web search was skipped and a spot price
    # returned instead of an answer.

    ASSET_PATTERN = re.compile(
        r"(?<!\w)(bitcoin|btc)(?!\w)"
    )


    # A price NOUN is required. Time words ("hôm nay", "hiện tại",
    # "today", "current") only modify a question — on their own
    # they turned "bitcoin hiện tại có bao nhiêu node" and
    # "current state of bitcoin regulation" into price lookups.

    PRICE_PATTERN = re.compile(
        r"(?<!\w)("
        r"gia|price|rate|worth|"
        r"usd|vnd|ty gia|tri gia"
        r")(?!\w)"
    )


    # "gia" is also a syllable of ordinary Vietnamese compounds
    # that have nothing to do with price. Word boundaries do not
    # help — in "tham gia" it really is a separate token — so the
    # compounds are vetoed explicitly. Heuristic list; extend it
    # when a new compound shows up.

    PRICE_VETO_PATTERN = re.compile(
        r"(?<!\w)("
        r"tham gia|quoc gia|gia dinh|gia tri|danh gia|"
        r"chuyen gia|gia nhap|gia han|gia suc|gia vi|"
        r"gia dung|gia the|gia truong"
        r")(?!\w)"
    )


    # A historical, forecast or foreign-currency question cannot be
    # answered by the spot USD/VND endpoint.

    NON_SPOT_PATTERN = re.compile(
        r"(?<!\w)("
        r"nam (?:19|20)\d\d|(?:19|20)\d\d|"
        r"hom qua|yesterday|lich su|history|historical|"
        r"du doan|prediction|forecast|"
        r"eur|jpy|gbp|cny|krw"
        r")(?!\w)"
    )


    @staticmethod
    def fold(text):
        """
        Lowercase and strip Vietnamese diacritics, so one ASCII
        pattern covers both "giá" and "gia".
        """

        lowered = str(
            text
        ).lower().strip()

        decomposed = unicodedata.normalize(
            "NFD",
            lowered
        )

        stripped = "".join(
            char
            for char in decomposed
            if not unicodedata.combining(
                char
            )
        )

        return stripped.replace(
            "đ",
            "d"
        )


    def is_bitcoin_price_query(self, query):

        q = self.fold(
            query
        )

        if not self.ASSET_PATTERN.search(
            q
        ):
            return False

        if self.NON_SPOT_PATTERN.search(
            q
        ):
            return False

        if self.PRICE_VETO_PATTERN.search(
            q
        ):
            return False

        return bool(
            self.PRICE_PATTERN.search(
                q
            )
        )

    # =====================================================
    # BITCOIN PRICE
    # =====================================================

    def bitcoin_price(self, query=""):

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

            # `results` is the only channel EvidenceVerifier reads.
            # Without it a successful price fetch produced zero
            # classifications and the user was told there was not
            # enough evidence about the price BCOS had just
            # retrieved.

            summary = (
                f"Bitcoin (BTC) = {price_usd} USD"
            )

            if price_vnd is not None:

                summary += (
                    f" / {price_vnd} VND"
                )

            if change_24h is not None:

                summary += (
                    f", 24h: {change_24h:.2f}%"
                )

            return {

                "success": True,

                "source": "CoinGecko",

                "data_type":
                    "crypto_price",

                "query": query,

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

                "count": 1,

                "results": [
                    {
                        "title":
                            "Bitcoin (BTC) spot price",
                        "url": url,
                        "content": summary,
                    }
                ],
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

                "query": query,

                "error":
                    str(e),

                "error_type":
                    type(e).__name__,

                "count": 0,

                "results": [],
            }

    # =====================================================
    # GENERAL WEB SEARCH
    # =====================================================

    def web_search(self, query):

        max_results = max(
            1,
            int(
                SEARCH_RESULTS
            )
        )

        attempts = max(
            1,
            int(
                SEARCH_RETRIES
            )
            + 1
        )

        last_error = None

        for attempt in range(
            attempts
        ):

            try:

                # A fresh client per call: see the note on the
                # class. It also bounds the per-engine wait, which
                # ddgs applies once per engine beyond its worker
                # count — up to ~35s with the default timeout.

                with DDGS(
                    timeout=SEARCH_TIMEOUT
                ) as client:

                    data = client.text(
                        query,
                        max_results=max_results,
                        region=SEARCH_REGION,
                        backend=SEARCH_BACKEND,
                    )

                return self.web_success(
                    query,
                    data
                )

            except DDGSException as exc:

                last_error = exc

                # ddgs raises this same type both for "every
                # backend refused" and for a genuinely empty
                # index. Only the first is worth retrying.

                if "No results found" in str(
                    exc
                ):

                    return self.web_success(
                        query,
                        []
                    )

                if attempt + 1 >= attempts:
                    break

                time.sleep(
                    1.5
                    * (
                        2 ** attempt
                    )
                )

            except OSError as exc:

                last_error = exc

                if attempt + 1 >= attempts:
                    break

                time.sleep(
                    1.5
                    * (
                        2 ** attempt
                    )
                )

        return {

            "success": False,

            "source": "web_search",

            "data_type": "web_search",

            "backend": SEARCH_BACKEND,

            "query": query,

            "error": str(
                last_error
            ),

            "error_type": type(
                last_error
            ).__name__,

            "count": 0,

            "results": [],
        }



    def web_success(
        self,
        query,
        data
    ):
        """
        Wrap raw ddgs items in the tool envelope.

        `source` is deliberately not "DuckDuckGo": results come
        from whichever of the configured backends answered, and
        ddgs discards per-result provenance — so the old label
        attributed a Mojeek or Startpage page to DuckDuckGo in
        the evidence the model cites.
        """

        results = []

        for item in data or []:

            if not isinstance(
                item,
                dict
            ):
                continue

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

            "success": True,

            "source": "web_search",

            "data_type": "web_search",

            "backend": SEARCH_BACKEND,

            "query": query,

            "count": len(
                results
            ),

            "results": results,
        }
