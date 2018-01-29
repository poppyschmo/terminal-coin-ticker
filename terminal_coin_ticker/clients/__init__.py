#!/bin/python3
# -*- coding: UTF-8 -*-
"""
Common client stuff goes here. Client classes need only only support those API
calls needed by the ticker. Non-ticker-specific utils, etc. should go in the
top-level init.
"""
# This file is part of <https://github.com/poppyschmo/terminal-coin-ticker>

import asyncio
import json
import os
import reprlib
import sys

try:
    import websockets
except ModuleNotFoundError:
    pass
try:
    import aiohttp
except ModuleNotFoundError:
    pass

from collections import namedtuple

USE_AIOHTTP = (False if "websockets" in globals() else
               True if "aiohttp" in globals() else None)
if USE_AIOHTTP is None:
    raise SystemExit("Please install websockets or aiohttp")

VERBOSITY = 6

Transmap = namedtuple("Transmap",
                      "sym time last volB volQ bid ask "
                      "open chg chgP curB curQ tick")

Background = namedtuple("Background",
                        "shade tint dark red mix_red green mix_green")

Foreground = namedtuple("Foreground",
                        "normal dim dark faint_shade faint_tint "
                        "red bright_red green bright_green head_alt")


default_bg = Background(*("\x1b[48;5;23%sm" % n for n in "6785555"))
default_fg = Foreground(*("\x1b[38;5;%sm" % n for n in
                          "253 250 243 237 236 95 167;1 65 83;1 228".split()))


class ExchangeClient:
    """
    These attrs must exist: {"exchange", "url", "url_vol", "trans"}
    """
    background_256 = default_bg
    foreground_256 = default_fg
    background_24 = None
    foreground_24 = None

    def __init__(self, verbosity=VERBOSITY, logfile=None,
                 use_aiohttp=USE_AIOHTTP):
        self.verbose = verbosity
        self.log = logfile if logfile else sys.stderr
        if use_aiohttp and "aiohttp" not in globals():
            self.echo("Can't find the aiohttp module. Trying websockets.", 3)
            use_aiohttp = False
        elif not use_aiohttp and "websockets" not in globals():
            use_aiohttp = True
        self.aio = use_aiohttp
        # Next two are kept separate so ticker data can be preserved and
        # updating is less complicated
        self.ticker = {}
        self.symbols = None
        self.markets = None
        self.conversions = None
        self.ticker_subscriptions = set()
        self._consumers = {self.consume_response: 0}
        self.consumers = [self.consume_response]  # Ranked version of above
        # These are only for logging send/recv raw message i/o
        try:
            reprlib.aRepr.maxstring = os.get_terminal_size().columns - 2
        except AttributeError:
            pass
        self.lrepr = reprlib.aRepr.repr

    async def __aenter__(self, url=None):
        if not url:
            url = self.url
        if self.aio:
            self._conn = aiohttp.ClientSession()
            self.websocket = await self._conn.ws_connect(url).__aenter__()
        else:
            self._conn = websockets.connect(url)
            self.websocket = await self._conn.__aenter__()
        # Start reading messages
        self.active_recv_Task = asyncio.ensure_future(self.recv_handler())
        return self

    async def __aexit__(self, *args, **kwargs):
        try:
            self.active_recv_Task.cancel()
            await self._conn.__aexit__(*args, **kwargs)
        except AttributeError:
            pass

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

    async def add_consumer(self, consumer, priority, update=False):
        if update:
            self._consumers[consumer] = priority
        else:
            self._consumers.setdefault(consumer, priority)
        self.consumers = [
            func for weight, func in
            sorted((weight, func) for func, weight in self._consumers.items())
        ]

    async def remove_consumer(self, consumer):
        try:
            del self._consumers[consumer]
        except KeyError:
            pass
        self.consumers = [
            func for weight, func in
            sorted((weight, func) for func, weight in self._consumers.items())
        ]

    async def consume_response(self, message):
        """
        Currently, this should return non-null to short-circuit (stop
        iteration) of the calling loop, meaning lesser-ranked consumers
        won't get called. Ugly and amateurish, for sure, but not sure
        how to do it right.
        """
        raise NotImplemented

    async def do_send(self, message):
        if self.verbose > 6:
            print("> {}".format(self.lrepr(message)), file=self.log)
        if self.aio:
            await self.websocket.send_str(message)
        else:
            await self.websocket.send(message)

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
                # Existing consumers are just regular subroutines for sorting
                # messages, and their non-null return vals go unused.  If the
                # point is to start these in order but wait till they all
                # return, then could try exceptions instead.
                for consumer in self.consumers:
                    if await consumer(message) is not None:
                        break  # <- skip lower priority handlers
        except asyncio.CancelledError:
            # Set value of ``self.active_recv_Task._result``
            return "recv_handler exited"

    async def get_symbols(self):
        """
        This must populate a dict called ``self.symbols`` and a set
        called ``self.markets``
        """
        raise NotImplemented

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
            base = self.symbols[pair]["curB"]
            quote = self.symbols[pair]["curQ"]
            return base, quote
        return pair

    async def get_market_conversion_pairs(self, quote=None):
        if not self.markets:
            await self.get_symbols()
        if not self.conversions:
            from itertools import permutations
            all_convs = {"".join(p) for p in permutations(self.markets, 2)}
            self.conversions = all_convs & self.symbols.keys()
        if quote:
            if "USD" in quote:
                return {p for p in self.conversions if
                        any(p.endswith(q) for q in ("USD", "USDT"))}
            else:
                return {p for p in self.conversions if p.endswith(quote)}
        else:
            return self.conversions

    async def get_volume_leaders(self, num=None):
        """
        Return a list of ``num`` leading products by trade volume.
        """
        if not self.markets:
            await self.get_symbols()
        import json
        import urllib.request
        from decimal import Decimal as Dec
        from urllib.error import HTTPError
        url = self.vol_url
        try:
            with urllib.request.urlopen(url) as f:
                data = json.load(f)
        except HTTPError as e:
            raise ConnectionError("Problem connecting; try again later")
        if "error" in data:
            raise ConnectionError(data["error"])
        tr = self.trans
        conv_d = {}
        for m in self.markets - {"USD", "USDT"}:
            for s in data:
                if s[tr.sym].startswith(m + "USD"):
                    conv_d[s[tr.sym]] = Dec(s[tr.last])
        #
        def _helper(d):  # noqa E306
            sym = d[tr.sym]
            if sym.endswith("USD") or sym.endswith("USDT"):
                in_usd = Dec(d[tr.volQ])
            else:
                try:
                    cQ = self.symbols[sym]["curQ"]
                    conv = conv_d.get(cQ + "USD") or conv_d[cQ + "USDT"]
                    in_usd = Dec(d[tr.volQ]) * conv
                except KeyError:
                    self.echo("Skipping %r" % sym)
                    return None
            return in_usd, sym
        #
        conv_it = sorted(filter(None, map(_helper, data)), reverse=True)
        if num is None:
            return (n for t, n in conv_it)
        else:
            return [t[1] for t, n in zip(conv_it, range(num))]


def _hex_to_rgb(hstr):
    """
    >>> _hex_to_rgb("#fafafa")
    (250, 250, 250)
    """
    return tuple(int(c) for c in bytes.fromhex(hstr.lstrip("#")))


def make_truecolor_palette(plane: str, *args, **kwargs):
    if plane.lower() in ("fg", "foreground"):
        template = "\x1b[38;2;{};{};{}m"
        maker = Foreground
    else:
        template = "\x1b[48;2;{};{};{}m"
        maker = Background
    if not kwargs:
        return maker(
            *(template.format(*_hex_to_rgb(x)) for x in args)
        )
    for field, value in dict(kwargs).items():
        kwargs[field] = template.format(*_hex_to_rgb(value))
    return maker(**kwargs)
