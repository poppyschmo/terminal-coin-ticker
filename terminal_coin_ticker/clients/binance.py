#!/bin/python3
# -*- coding: UTF-8 -*-
"""
https://github.com/binance-exchange/binance-official-api-docs
"""
# This file is part of <https://github.com/poppyschmo/terminal-coin-ticker>

import asyncio

from terminal_coin_ticker import (
    add_async_sig_handlers, remove_async_sig_handlers, ppj
)
from terminal_coin_ticker.clients import (
    USE_AIOHTTP, Transmap, ExchangeClient,
)

VERBOSITY = 6

# These are for the REST API's ``ticker`` and ``exchangeInfo`` symbol calls
# Stream keys are more idiosyncratic and handled granularly by each method
tmap = Transmap(
    sym="symbol",
    time="time",
    last="lastPrice",
    volB="volume",
    volQ="quoteVolume",
    bid="bidPrice",
    ask="askPrice",
    open="openPrice",
    chg=None,  # OR convert to quotient by dividing by open
    chgP="priceChangePercent",
    curB="baseAsset",
    curQ="quoteAsset",
    tick="tickSize"
)


class BinanceClient(ExchangeClient):
    """
    errors_reference = {
        -1000: "UNKNOWN",
        -1001: "DISCONNECTED",
        -1002: "UNAUTHORIZED",
        -1003: "TOO_MANY_REQUESTS",
        -1006: "UNEXPECTED_RESP",
        -1007: "TIMEOUT",
        -1013: "INVALID_MESSAGE",
        -1014: "UNKNOWN_ORDER_COMPOSITION",
        -1015: "TOO_MANY_ORDERS",
        -1016: "SERVICE_SHUTTING_DOWN",
        -1020: "UNSUPPORTED_OPERATION",
        -1021: "INVALID_TIMESTAMP",
        -1022: "INVALID_SIGNATURE",
        -1100: "ILLEGAL_CHARS",
        -1101: "TOO_MANY_PARAMETERS",
        -1102: "MANDATORY_PARAM_EMPTY_OR_MALFORMED",
        -1103: "UNKNOWN_PARAM",
        -1104: "UNREAD_PARAMETERS",
        -1105: "PARAM_EMPTY",
        -1106: "PARAM_NOT_REQUIRED",
        -1112: "NO_DEPTH",
        -1114: "TIF_NOT_REQUIRED",
        -1115: "INVALID_TIF",
        -1116: "INVALID_ORDER_TYPE",
        -1117: "INVALID_SIDE",
        -1118: "EMPTY_NEW_CL_ORD_ID",
        -1119: "EMPTY_ORG_CL_ORD_ID",
        -1120: "BAD_INTERVAL",
        -1121: "BAD_SYMBOL",
        -1125: "INVALID_LISTEN_KEY",
        -1127: "MORE_THAN_XX_HOURS",
        -1128: "OPTIONAL_PARAMS_BAD_COMBO",
        -1130: "INVALID_PARAMETER",
        -2008: "BAD_API_ID",
        -2009: "DUPLICATE_API_KEY_DESC",
        -2012: "CANCEL_ALL_FAIL",
        -2013: "NO_SUCH_ORDER",
        -2014: "BAD_API_KEY_FMT",
        -2015: "REJECTED_MBX_KEY"
    }
    """
    exchange = "Binance"
    url = "wss://stream.binance.com:9443"
    rest = {
        "base":  "https://api.binance.com/api/v1",
        "ticker": "/ticker/24hr",  # used by volume ranker
        "symbols": "/exchangeInfo"
    }
    trans = tmap

    def __init__(self, verbosity=VERBOSITY, logfile=None,
                 use_aiohttp=USE_AIOHTTP):
        self.lock = asyncio.Lock()
        self.streams = set()
        super().__init__(verbosity, logfile, use_aiohttp)
        self.quantize = True

    async def _reload(self):
        if self.lock.locked():
            return None
        await self.lock.acquire()
        try:
            if hasattr(self, "_conn"):
                await self.__aexit__(None, None, None)
            # Wait while url modified
            settled = set()
            while self.streams != settled:
                self.echo("Waiting till settled: %r" %
                          (self.streams ^ settled), 7)
                settled = set(self.streams)
                await asyncio.sleep(0.1)
            self.echo("Settled: %r" % (self.streams), 7)
            #
            if not self.streams:
                self.echo("No streams to consume")
                return None
            #
            path = "/streams"
            streams = "/".join(self.streams)
            query = "".join(("?streams=", *streams))
            url = "".join((self.url, path, query))
            self.echo("Query: %r" % query)
            await super().__aenter__(url)
        finally:
            self.lock.release()

    async def __aenter__(self):
        """
        Logic from parent method moved to self._reload
        """
        return self

    async def consume_response(self, message):
        if not self.ticker_subscriptions:
            self.echo("Not subscribed to any symbols")
            return None
        from collections import abc
        if not isinstance(message, abc.Mapping):
            raise ValueError("Malformed message: %s" % message)
        if "error" in message:
            self.echo(message["error"], level=3)
            return message["error"]
        elif "stream" not in message:
            raise ValueError("Stream not in message: %r" % message)
        sym, __, stream_type = message["stream"].partition("@")
        sym = sym.upper()
        data = message["data"]
        # self.echo("New - sym: %r, stream_type: %r" % (sym, stream_type))
        assert data["s"] == sym
        assert sym in self.ticker_subscriptions
        self.ticker.setdefault(sym, {})
        if stream_type == "ticker":
            # Binance's ``data["p"]`` is the plain algebraic change (diff btwn
            # open and last). Better to just send percent and later divide by
            # 100, since the fmt specifier ``%p`` takes a quotient
            #
            # TODO verify bid/ask prices match exchange website. Would be nice
            # to avoid subscribing to the orderbook entirely. Easiest to check
            # with low-volume pairs
            self.ticker[sym].update(dict(
                sym=data["s"],
                chgP=data["P"],
                bid=data["b"],
                ask=data["a"],
                open=data["o"],
                volB=data["v"],
                volQ=data["q"],
                time=data["E"]
            ))
        elif stream_type == "aggTrade":
            # self.echo("Updating last price for %r to %r" % (sym, data["p"]))
            self.ticker[sym].update({"last": data["p"], "time": data["E"]})
        return None

    async def get_symbols(self, symbol=None, cache_result=True):
        """
        This uses a normal http GET request via the REST API
        TODO: add native keys and example values here
        """
        if self.symbols is None:
            import json
            import urllib.request
            from urllib.error import HTTPError
            url = "".join((self.rest["base"], self.rest["symbols"]))
            try:
                with urllib.request.urlopen(url) as f:
                    data = json.load(f)
            except HTTPError as e:
                raise ConnectionError("Problem connecting to %s" % url)
            if "error" in data:
                raise ConnectionError(data["error"])
            self.symbols = {
                s["symbol"]: dict(curB=s[self.trans.curB],
                                  curQ=s[self.trans.curQ],
                                  tick=next(d[self.trans.tick].rstrip("0") for
                                            d in s["filters"] if
                                            self.trans.tick in d))
                for s in data["symbols"]
            }
            self.markets = {v["curQ"] for v in self.symbols.values()}
            if "123456" in self.symbols:
                del self.symbols["123456"]
            self.markets.discard("456")
        if symbol is None:
            return list(self.symbols.values())
        else:
            return self.symbols[symbol]

    async def do_poll(self, symbol, key):
        while key not in self.ticker.get(symbol, {}):
            await asyncio.sleep(0.01)

    async def subscribe_agg_trade(self, symbol):
        assert symbol in self.ticker_subscriptions
        stream_name = "%s@aggTrade" % symbol.lower()
        self.streams.add(stream_name)
        # This is destined for ``asyncio.wait()``, so no need to wrap in Task
        return self.do_poll(symbol, "last")

    async def unsubscribe_agg_trade(self, symbol):
        assert symbol not in self.ticker_subscriptions
        stream_name = "%s@aggTrade" % symbol.lower()
        self.streams.discard(stream_name)

    async def subscribe_ticker(self, symbol):
        if symbol in self.ticker_subscriptions:
            self.echo("Already subscribed to %r" % symbol, level=4)
            return None
        self.ticker_subscriptions.add(symbol)
        stream_name = "%s@ticker" % symbol.lower()
        self.streams.add(stream_name)
        start_trade = await self.subscribe_agg_trade(symbol)
        await self._reload()
        start_ticker = self.do_poll(symbol, "chgP")
        await asyncio.wait((start_trade, start_ticker))
        if self.verbose:
            self.echo("adding %s to ticker_subscriptions" % symbol)
        return "Subscribed to %r" % symbol

    async def unsubscribe_ticker(self, symbol):
        if symbol not in self.ticker_subscriptions:
            self.echo("Already unsubscribed from %r" % symbol, level=4)
            return None
        self.ticker_subscriptions.discard(symbol)
        stream_name = "%s@ticker" % symbol.lower()
        self.streams.discard(stream_name)
        await self.unsubscribe_agg_trade(symbol)
        await self._reload()
        return "Unsubscribed from %r" % symbol

    def make_date(self, timestamp):
        from datetime import datetime
        return datetime.utcfromtimestamp(timestamp/1000)


async def main(**kwargs):
    Client = BinanceClient
    async with Client(VERBOSITY, use_aiohttp=USE_AIOHTTP) as client:
        my_symbols = [await client.canonicalize_pair(s) for
                      s in "eth_btc ltc.btc".split()]
        futs = []
        futs.append(await client.get_volume_leaders(10))
        #
        futs += [dict(markets=client.markets)]
        futs.append({"conversions":
                     await client.get_market_conversion_pairs()})
        #
        for fs in asyncio.as_completed(map(client.get_symbols, my_symbols)):
            futs.append(await fs)
        #
        futs += await asyncio.gather(*map(client.subscribe_ticker,
                                          my_symbols))
        futs.append({s: client.ticker[s] for s in my_symbols})
        #
        # Move these to tests
        assert not any(True for v in client.symbols.values() if
                       v["curQ"] == "456")
        from datetime import timedelta, datetime
        now = datetime.utcnow()
        for sym in my_symbols:
            ts = client.make_date(client.ticker[sym]["time"])
            assert now - ts < timedelta(0, 2)
        #
        futs += await asyncio.gather(*map(client.unsubscribe_ticker,
                                          my_symbols))
    #
    futs.append(client.active_recv_Task.result())
    return futs


if __name__ == "__main__":
    import os
    VERBOSITY = int(os.getenv("VERBOSITY", VERBOSITY))
    USE_AIOHTTP = any(s == os.getenv("USE_AIOHTTP", str(USE_AIOHTTP)).lower()
                      for s in "1 yes true".split())
    #
    loop = asyncio.get_event_loop()
    sigs = ("SIGTERM", "SIGTERM")
    add_async_sig_handlers(*sigs, loop=loop)
    # TODO move this to a test
    add_async_sig_handlers(*remove_async_sig_handlers(*sigs, loop=loop))
    #
    try:
        ppj(loop.run_until_complete(main()))
    except RuntimeError as e:
        if "loop stopped before Future completed" not in str(e):
            raise
