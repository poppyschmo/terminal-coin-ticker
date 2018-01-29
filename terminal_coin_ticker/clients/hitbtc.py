#!/bin/python3
# -*- coding: UTF-8 -*-
"""
API docs_ and interactive explorer_:

.. _docs: https://api.hitbtc.com
.. _explorer: https://api.hitbtc.com/api/2/explore

"""
# This file is part of <https://github.com/poppyschmo/terminal-coin-ticker>

import asyncio
import json
import sys

from terminal_coin_ticker import (
    add_async_sig_handlers, remove_async_sig_handlers, ppj
)
from terminal_coin_ticker.clients import (
    USE_AIOHTTP, Transmap, make_truecolor_palette, ExchangeClient
)

VERBOSITY = 6

tmap = Transmap(
    sym="symbol",
    time="timestamp",
    last="last",
    volB="volume",
    volQ="volumeQuote",
    bid="bid",
    ask="ask",
    open="open",
    chg=None,
    chgP=None,
    curB="baseCurrency",
    curQ="quoteCurrency",
    tick="tickSize"
)

errors_reference = {
    403:    (401, "Action is forbidden for account"),
    429:    (429, "Too many requests. Action is being rate limited for "
                  "account"),
    500:    (500, "Internal Server Error"),
    503:    (503, "Service Unavailable. Try it again later"),
    504:    (504, "Gateway Timeout. Check the result of your request later"),
    1001:   (401, "Authorisation required"),
    1002:   (401, "Authorisation failed"),
    1003:   (403, "Action is forbidden for this API key. "
                  "Check permissions for API key"),
    1004:   (401, "Unsupported authorisation method. Use Basic "
                  "authentication"),
    2001:   (400, "Symbol not found"),
    2002:   (400, "Currency not found "),
    20001:  (400, "Insufficient funds. Insufficient funds for creating "
                  "order or any account operation"),
    20002:  (400, "Order not found. Attempt to get active order that "
                  "not existing: filled, canceled or expired. Attempt "
                  "to cancel not existing order. Attempt to cancel "
                  "already filled or expired order."),
    20003:  (400, "Limit exceeded. Withdrawal limit exceeded"),
    20004:  (400, "Transaction not found. Requested transaction not found"),
    20005:  (400, "Payout not found"),
    20006:  (400, "Payout already committed"),
    20007:  (400, "Payout already rolled back"),
    20008:  (400, "Duplicate clientOrderId"),
    10001:  (400, "Validation error. Input not valid, see more in message "
                  "field")
}

background = {
    "shade":        "#14374A",
    "tint":         "#163E53",
    "dark":         "#153043",
    "red":          "#3E3D48",
    "mix_red":      "#293a49",
    "green":        "#105554",
    "mix_green":    "#12464f"
}

foreground = {
    "normal":       "#d3d7cf",
    "dim":          "#a1b5c1",
    "dark":         "#325a6a",
    "faint_shade":  "#224a5a",
    "faint_tint":   "#153043",
    "red":          "#BF4232",
    "bright_red":   "#E55541",
    "green":        "#01A868",
    "bright_green": "#0ACD8A",
    "head_alt":     "#507691"
}

truecolor_bg = make_truecolor_palette("background", **background)
truecolor_fg = make_truecolor_palette("foreground", **foreground)


class HitBTCClient(ExchangeClient):
    exchange = "HitBTC"
    url = "wss://api.hitbtc.com/api/2/ws"
    vol_url = "https://api.hitbtc.com/api/2/public/ticker"
    trans = tmap
    background_24 = truecolor_bg
    foreground_24 = truecolor_fg

    def __init__(self, verbosity=VERBOSITY, logfile=None,
                 use_aiohttp=USE_AIOHTTP):
        """
        Neither the jsonrpc spec nor the api docs mention max size for
        ``id``. If they did, it'd probably be better to catch
        ``StopIteration`` and remake the ws connection when approaching
        this limit. Or, if the server resets its cache at that point,
        use ``itertools.cycle`` and keep on going. If the server simply
        forgets the ids of fulfilled requests and/or overwrites
        duplicates, then this is pointless.
        .. _: http://www.jsonrpc.org/specification
        """
        self.rqids = iter(range(1, sys.maxsize))
        self.replies = {}
        super().__init__(verbosity, logfile, use_aiohttp)

    def prep_request(self, method, payload, rqid=None):
        # Can also use channel variant, e.g.:
        #   {channel: 'ticker', event: 'unsub', params:{symbol: pair}}
        if rqid is None:
            rqid = next(self.rqids)
        outdict = dict(method=method, params=payload, id=rqid)
        # No need for bytes
        return rqid, json.dumps(outdict)

    async def consume_response(self, message):
        if "error" in message:
            self.echo(message["error"], level=3)
            # To prevent other consumers from running, should return an actual
            # Exception
            code = message["error"].get("code")
            if code in errors_reference:
                message["error"].update(zip("status docs".split(),
                                            errors_reference[code]))
            return message["error"]
        rqid = message.get("id")
        if rqid is None:
            return
        rqid = int(rqid)
        result = message.get("result", message.get("error"))
        self.replies.update({rqid: result})

    async def consume_ticker_notes(self, message):
        """
        Native keys::

            # Retained
            "ask", "bid", "last", "open", "volume", "volumeQuote",
            "timestamp": "2018-01-30T05:23:51.979Z"

            # Omitted
            "symbol", "low", "high"
        """
        if not self.ticker_subscriptions:
            await self.remove_consumer(self.consume_ticker_notes)
            return None
        if message.get("method", message.get("channel")) != "ticker":
            return None
        new_data = message.get("params", message.get("data"))
        existing = self.ticker.setdefault(new_data["symbol"], {})
        # Deltas complicate this key translation business
        keys = ("time", "volB", "volQ", "last", "open", "ask", "bid")
        # This'll fail if any json vals arrive as non-quoted zeros.
        from operator import itemgetter
        tr = self.trans._asdict()
        filtered = filter(itemgetter(1),
                          ((k, new_data.get(tr[k])) for k in keys))
        # In which case should replace with::
        #
        #     lambda item: item[1] is not None
        #
        existing.update(dict(filtered))
        return existing

    async def check_replies(self, rqid):
        while rqid not in self.replies:
            await asyncio.sleep(0.1)
        result = self.replies[rqid]
        del self.replies[rqid]
        return result

    async def get_symbols(self, symbol=None, cache_result=True):
        if self.symbols is None:
            rqid, message = self.prep_request("getSymbols", {})
            await self.do_send(message)
            result = await self.check_replies(rqid)
            self.symbols = {s["id"]: dict(curB=s[self.trans.curB],
                                          curQ=s[self.trans.curQ],
                                          tick=s[self.trans.tick])
                            for s in result}
            self.markets = {v["curQ"] for v in self.symbols.values()}
        if symbol is None:
            return list(self.symbols.values())
        else:
            return self.symbols[symbol]

    async def subscribe_ticker(self, symbol):
        if symbol in self.ticker_subscriptions:
            self.echo("Already subscribed to %r" % symbol, level=4)
            return None
        payload = {"symbol": symbol}
        rqid, message = self.prep_request("subscribeTicker", payload)
        if self.verbose:
            self.echo("adding %s to ticker_sub...s for id %d" %
                      (symbol, rqid))
        self.ticker_subscriptions.add(symbol)
        await self.add_consumer(self.consume_ticker_notes, 5)
        await self.do_send(message)
        result = await self.check_replies(rqid)
        return ("subscribe_ticker(%r) exited" % symbol, result)

    async def unsubscribe_ticker(self, symbol):
        if symbol not in self.ticker_subscriptions:
            self.echo("Already unsubscribed from %r" % symbol, level=4)
            return None
        payload = {"symbol": symbol}
        rqid, message = self.prep_request("unsubscribeTicker", payload)
        await self.do_send(message)
        result = await self.check_replies(rqid)
        self.ticker_subscriptions.discard(symbol)
        return ("unsubscribe_ticker(%r) exited" % symbol, result)

    def make_date(self, timestamp):
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        from datetime import datetime
        dts = datetime.strptime(timestamp, fmt)
        return dts


async def main():
    Client = HitBTCClient
    async with Client(VERBOSITY, use_aiohttp=USE_AIOHTTP) as client:
        # XRP/USD pair is included because it's anomalous (ends in USDT)
        my_symbols = [await client.canonicalize_pair(s) for
                      s in "eth_btc bch.btc xrp/usd".split()]
        futs = []
        futs += await asyncio.gather(*map(client.get_symbols, my_symbols))
        futs.append({"markets": client.markets})
        futs.append(await client.get_volume_leaders(10))
        #
        client.echo("Starting subscription cycle...")
        futs += await asyncio.gather(*map(client.subscribe_ticker, my_symbols))
        futs.append(await asyncio.sleep(5, result="Did stuff"))  # ← do stuff
        futs += await asyncio.gather(*map(client.unsubscribe_ticker,
                                          my_symbols))
        client.echo("All done...")
        ppj(client.ticker)
    futs.append(client.active_recv_Task.result())
    return dict(futs=futs)


if __name__ == "__main__":
    import os
    VERBOSITY = int(os.getenv("VERBOSITY", VERBOSITY))
    USE_AIOHTTP = any(s == os.getenv("USE_AIOHTTP", str(USE_AIOHTTP)).lower()
                      for s in "1 yes true".split())
    #
    loop = asyncio.get_event_loop()
    sigs = "sigint sigterm".upper().split()
    teardown_cbs = {}
    add_async_sig_handlers(*sigs, loop=loop)
    # TODO move this to a test
    add_async_sig_handlers(*remove_async_sig_handlers(*sigs, loop=loop))
    #
    try:
        ppj(loop.run_until_complete(main()))
    except RuntimeError as e:
        if "loop stopped before Future completed" not in str(e):
            raise
