#!/bin/python3
# -*- coding: UTF-8 -*-
"""
Yeah, there's only one client, so far. And it's only partially implemented,
meaning it only supports those calls needed by the ticker. Glaring omissions
include candle subscriptions and all the trading/order/account stuff.

"""
# This file is part of <https://github.com/poppyschmo/terminal-coin-ticker>

import asyncio
import json
import os
import reprlib
import signal
import sys

try:
    import websockets
except ModuleNotFoundError:
    pass
try:
    import aiohttp
except ModuleNotFoundError:
    pass

from decimal import Decimal
from functools import partial

USE_AIOHTTP = (False if "websockets" in globals() else
               True if "aiohttp" in globals() else None)
if USE_AIOHTTP is None:
    raise SystemExit("Please install websockets or aiohttp")

VERBOSITY = 6


class HitBTCWebSocketsClient:
    exchange = "HitBTC"
    url = "wss://api.hitbtc.com/api/2/ws"
    errors_reference = {
        403:    (401,   "Action is forbidden for account"),
        429:    (429,   "Too many requests. Action is being rate limited "
                        "for account"),
        500:    (500,   "Internal Server Error"),
        503:    (503,   "Service Unavailable. Try it again later"),
        504:    (504,   "Gateway Timeout. Check the result of your request "
                        "later"),
        1001:   (401,   "Authorisation required"),
        1002:   (401,   "Authorisation failed"),
        1003:   (403,   "Action is forbidden for this API key. "
                        "Check permissions for API key"),
        1004:   (401,   "Unsupported authorisation method. Use Basic "
                        "authentication"),
        2001:   (400,   "Symbol not found"),
        2002:   (400,   "Currency not found "),
        20001:  (400,   "Insufficient funds. Insufficient funds for creating "
                        "order or any account operation"),
        20002:  (400,   "Order not found. Attempt to get active order that "
                        "not existing: filled, canceled or expired. Attempt "
                        "to cancel not existing order. Attempt to cancel "
                        "already filled or expired order."),
        20003:  (400,   "Limit exceeded. Withdrawal limit exceeded"),
        20004:  (400,   "Transaction not found. Requested transaction not "
                        "found"),
        20005:  (400,   "Payout not found"),
        20006:  (400,   "Payout already committed"),
        20007:  (400,   "Payout already rolled back"),
        20008:  (400,   "Duplicate clientOrderId"),
        10001:  (400,   "Validation error. Input not valid, see more in "
                        "message field")
    }

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
        self.verbose = verbosity
        self.log = logfile if logfile else sys.stderr
        if use_aiohttp and "aiohttp" not in globals():
            self.echo("Can't find the aiohttp module. Trying websockets.", 3)
            use_aiohttp = False
        elif not use_aiohttp and "websockets" not in globals():
            use_aiohttp = True
        self.aio = use_aiohttp
        self.rqids = iter(range(1, sys.maxsize))
        self.replies = {}
        # Next two are kept separate so ticker data can be preserved and
        # updating is less complicated
        self.ticker = {}
        self.symbols = None
        self.markets = None
        self.ticker_subscriptions = set()
        self.consumers = {self.consume_response: 0}
        # These are only for logging send/recv raw message i/o
        try:
            reprlib.aRepr.maxstring = os.get_terminal_size().columns - 2
        except AttributeError:
            pass
        self.lrepr = reprlib.aRepr.repr

    def echo(self, msg, level=6):
        if (level > self.verbose):
            return
        from datetime import datetime
        from inspect import stack
        fr = stack()[1]
        fparts = []
        if "self" in fr.frame.f_locals:
            fparts = [(self.__class__.__name__), "."]
        fparts += [stack()[1].function, "()"]
        funcname = "".join(fparts)
        if hasattr(os, "isatty") and os.isatty(sys.stdout.fileno()):
            fmtstr = "[\x1b[38;5;244m{}\x1b[m] \x1b[38;5;249m{}\x1b[m: {}"
        else:
            fmtstr = "[{}] {}: {}"
        print(fmtstr.format(datetime.now(), funcname, msg), file=self.log)

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
            if code in self.errors_reference:
                message["error"].update(zip("status docs".split(),
                                            self.errors_reference[code]))
            return message["error"]
        rqid = message.get("id")
        if rqid is None:
            return
        rqid = int(rqid)
        result = message.get("result", message.get("error"))
        self.replies.update({rqid: result})

    async def consume_ticker_notes(self, message):
        if not self.ticker_subscriptions:
            del self.consumers[self.consume_ticker_notes]
            return None
        if message.get("method", message.get("channel")) != "ticker":
            return None
        params = message.get("params", message.get("data"))
        symbol = params.get("symbol")
        self.ticker.update({symbol: params})
        return params

    async def __aenter__(self):
        if self.aio:
            self._conn = aiohttp.ClientSession()
            self.websocket = await self._conn.ws_connect(self.url).__aenter__()
        else:
            self._conn = websockets.connect(self.url)
            self.websocket = await self._conn.__aenter__()
        # Start reading messages
        self.active_recv_Task = asyncio.ensure_future(self.recv_handler())
        return self

    async def __aexit__(self, *args, **kwargs):
        """Should probably close receive task as well"""
        await self._conn.__aexit__(*args, **kwargs)

    async def do_send(self, message):
        if self.verbose > 6:
            print("> {}".format(self.lrepr(message)), file=self.log)
        if self.aio:
            await self.websocket.send_str(message)
        else:
            await self.websocket.send(message)

    async def check_replies(self, rqid):
        while rqid not in self.replies:
            await asyncio.sleep(0.1)
        result = self.replies[rqid]
        del self.replies[rqid]
        return result

    async def recv_handler(self):
        if self.verbose:
            self.echo("Starting receive handler")
            if self.aio:
                self.echo("Using aiohttp instead of websockets")
        try:
            async for raw_message in self.websocket:
                if self.aio:
                    raw_message = raw_message.data
                if self.verbose > 6:
                    print("< {}".format(self.lrepr(raw_message)),
                          file=self.log)
                message = json.loads(raw_message)
                for __, consumer in sorted((weight, func) for func, weight
                                           in self.consumers.items()):
                    if await consumer(message) is not None:
                        break
        except asyncio.CancelledError:
            # pass
            return "recv_handler exited"

    async def get_currency(self, currency=None):
        payload = {}
        if currency is not None:
            payload.update(currency=currency)
        rqid, message = self.prep_request("getCurrency", payload)
        await self.do_send(message)
        return await self.check_replies(rqid)

    async def get_symbols(self, symbol=None, cache_result=True):
        if self.symbols is None:
            rqid, message = self.prep_request("getSymbols", {})
            await self.do_send(message)
            result = await self.check_replies(rqid)
            self.symbols = {s["id"]: s for s in result}
            self.markets = {v["quoteCurrency"] for v in self.symbols.values()}
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
        self.consumers.setdefault(self.consume_ticker_notes, 5)
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

    async def authenticate(self, public_key, secret_key):
        """
        This is confusing. HS256 is symmetric, so what's with the key pair?
        """
        import hmac
        import secrets
        nonce = secrets.token_urlsafe()
        sig = hmac.new(secret_key.encode(),
                       nonce.encode(), "SHA256").digest().hex()
        payload = dict(algo="HS256", pKey=public_key, nonce=nonce,
                       signature=sig)
        rqid, message = self.prep_request("login", payload)
        await self.do_send(message)
        result = await self.check_replies(rqid)
        return result

    async def get_trading_balance(self):
        rqid, message = self.prep_request("getTradingBalance", {})
        await self.do_send(message)
        return await self.check_replies(rqid)

    async def get_active_orders(self):
        rqid, message = self.prep_request("getOrders", {})
        await self.do_send(message)
        return await self.check_replies(rqid)

    async def canonicalize_pair(self, pair, as_tuple=False):
        # Unfortunately, base/quote currency ids are not always the same as the
        # concatenated pair, e.g., "BXTUSDT" != "BXT" + "USD". So probably best
        # to only return one kind per invocation. Exchange's "currency" market
        # data market seems to use Tether and USD interchangeably.
        if self.symbols is None:
            await self.get_symbols()
            assert self.symbols is not None
        if as_tuple is False and pair in self.symbols:
            return pair
        if not pair.isalnum():
            sep = [c for c in pair if not c.isalnum()].pop()
            pair = pair.replace(sep, "")
        pair = pair.upper()
        if pair not in self.symbols:
            if pair.endswith("USD") and pair + "T" in self.symbols:
                pair += "T"
            else:
                raise ValueError("%r not found in client.symbols" % pair)
        if as_tuple:
            base = self.symbols[pair]["baseCurrency"]
            quote = self.symbols[pair]["quoteCurrency"]
            return base, quote
        return pair


def remove_async_sig_handlers(sigs, loop):
    outlist = []
    for sig in sigs:
        sig_obj = getattr(signal, sig)
        existing = loop._signal_handlers.get(sig_obj)
        if existing:
            outlist.append(existing)
        loop.remove_signal_handler(sig_obj)
        assert sig_obj not in loop._signal_handlers
    return outlist


def add_async_sig_handlers(sigs, loop, callback=None):
    """``callbacks`` is a dict of the form {sig: callback, ...}"""
    _callback = callback

    def handle_sig(signame):
        # assert "loop" in locals()
        print("Got a signal: %r" % signame, file=sys.stderr)
        loop.stop()

    for sig in sigs:
        if _callback is None:
            # Must partialize the ``signames`` param here by freezing current
            # ``sig`` "for" obvious reasons, but ``loop`` is safe
            callback = partial(handle_sig, signame=sig)
        loop.add_signal_handler(getattr(signal, sig), callback)


def decimate(inobj):
    """
    Convert numbers and numeric strings in native JSON-like objects to
    Decimal instances.
    """
    from collections.abc import Mapping, MutableSequence
    if isinstance(inobj, Mapping):
        outobj = dict(inobj)
        for k, v in inobj.items():
            if (isinstance(v, str) and
                    v.lstrip("-").replace(".", "", 1).isdigit()):
                outobj[k] = Decimal(v)
            elif isinstance(v, (int, float)):
                outobj[k] = Decimal(repr(v))  # covers inf, nan
            elif isinstance(v, (Mapping, MutableSequence)):
                outobj[k] = decimate(v)
    elif isinstance(inobj, MutableSequence):
        outobj = [decimate(item) for item in inobj]
    else:
        return inobj
    return outobj


def ppj(obj, *args, **kwargs):
    """
    Prints collections containing the results of futures.
    """
    try:
        print(json.dumps(obj, indent=2), *args, **kwargs)
    except TypeError:
        import pprint
        pprint.pprint(obj, indent=2, stream=sys.stderr)


async def apply_many(func, args: list):
    tasks = []
    for arg in args:
        tasks.append(asyncio.ensure_future(func(arg)))
    return await asyncio.gather(*tasks)


async def main(**kwargs):
    Client = HitBTCWebSocketsClient
    async with Client(VERBOSITY, use_aiohttp=USE_AIOHTTP) as client:
        my_currencies = "ETH BCH BTC".split()
        my_symbols = "ETHBTC BCHBTC".split()
        ppj(await apply_many(client.get_currency, my_currencies))
        #
        # public = "baadac1dbaadac1dbaadac1dbaadac1d"
        # secret = "feedbeefdeadbabefeedbabedeadbeef"
        # ppj(await client.authenticate(public, secret))
        # ppj(await client.get_active_orders())
        #
        client.echo("Starting subscription cycle demo")
        futs = await apply_many(client.subscribe_ticker, my_symbols)
        futs.append(await asyncio.sleep(5, result="Did stuff"))  # ← do stuff
        futs += await apply_many(client.unsubscribe_ticker, my_symbols)
        client.active_recv_Task.cancel()
        futs.append(await asyncio.wait_for(client.active_recv_Task,
                                           timeout=None))
        client.echo("All done...")
        ppj(client.ticker)
        return dict(futs=futs)


if __name__ == "__main__":
    VERBOSITY = int(os.getenv("VERBOSITY", VERBOSITY))
    USE_AIOHTTP = any(s == os.getenv("USE_AIOHTTP", str(USE_AIOHTTP)).lower()
                      for s in "1 yes true".split())
    #
    loop = asyncio.get_event_loop()
    sigs = "sigint sigterm".upper().split()
    teardown_cbs = {}
    add_async_sig_handlers(sigs, loop)
    try:
        ppj(loop.run_until_complete(main()))
    except RuntimeError as e:
        if "loop stopped before Future completed" not in str(e):
            raise
