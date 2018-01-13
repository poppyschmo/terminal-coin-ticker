#!/bin/python3
# -*- coding: UTF-8 -*-
"""
Usage::

    tc-ticker [NUM] [PAIR ...]

    Show NUM leading products, by volume, and/or PAIRs taking one of the
    following (case-insensitive) forms:

        basequote base_quote base/quote "base quote"

    Env-var-based options are listed atop the main script.

Warning
-------
Whether due to my own failings or those of the exchange, the market data
displayed is often inaccurate and should be considered untrustworthy.

"""
# Author: Jane Soko
# License: Apache 2.0

import asyncio
import os
import sys
from decimal import Decimal as Dec

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))

from terminal_coin_ticker.clients import (  # noqa
    HitBTCWebSocketsClient, apply_many, add_async_sig_handlers, decimate,
    remove_async_sig_handlers, ppj
)

SHOW_FIRST = 24

# Env vars
VERBOSITY = 6        # Ignored unless LOGFILE is also exported
USE_AIOHTTP = False  # Ignored unless websockets is also installed
VOL_SORTED = True    # Sort all pairs by volume, auto-selected or named
VOL_UNIT = "USD"     # BTC, ETH, or None for per-pair base currencies
HAS_24 = False       # For apps and utils that outlaw COLORTERM
STRICT_TIME = True   # Die when service notifications aren't updating
PULSE = "normal"     # Flash style of "normal," "fast," or null
PULSE_OVER = 0.125   # Flash threshold as percent change since last update
HEADING = "normal"   # Also "hr_over," "hr_under," "full," and "slim"

# TTL vars
MAX_STALE = 0.5      # Tolerance threshold ratio of stale/all pairs
STALE_SECS = 15      # Max seconds pair data is considered valid
POLL_INTERVAL = 10   # Seconds to wait between checks


def _rank_by_volume():
    """
    Query server via http GET request for the latest ticker data on all
    traded pairs. Return (pair, volume in USD).

    Note
    ----
    Even though this is hardwired to HitBTC, should still probably
    obtain a list of supported markets and loop through them. Although
    an actual upstream change in available markets would break plenty of
    stuff elsewhere.
    """
    import json
    import urllib.request
    from urllib.error import HTTPError
    from operator import itemgetter
    url = "https://api.hitbtc.com/api/2/public/ticker"
    try:
        with urllib.request.urlopen(url) as f:
            data = json.load(f)
    except HTTPError as e:
        raise ConnectionError("Problem connecting to server, try again later")
    if "error" in data:
        raise ConnectionError(data["error"])
    eth_usd = Dec([s["last"] for s in data if s["symbol"] == "ETHUSD"].pop())
    btc_usd = Dec([s["last"] for s in data if s["symbol"] == "BTCUSD"].pop())

    def _helper(d):
        if d["symbol"].endswith("USD") or d["symbol"].endswith("USDT"):
            in_usd = Dec(d["volumeQuote"])
        elif d["symbol"].endswith("ETH"):
            in_usd = Dec(d["volumeQuote"]) * eth_usd
        elif d["symbol"].endswith("BTC"):
            in_usd = Dec(d["volumeQuote"]) * btc_usd
        else:
            raise ValueError("Could not convert %s" % d["symbol"])
        return d["symbol"], in_usd

    for sym, vol in sorted(map(_helper, data), key=itemgetter(1),
                           reverse=True):
        yield sym


def _get_top_markets(num):
    """
    Return a list of ``num`` leading products by trade volume.
    """
    sym_gen = _rank_by_volume()
    return list(next(sym_gen) for n in range(num))


def _make_date(timestamp):
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
    from datetime import datetime
    return datetime.strptime(timestamp, fmt)


def _hex_to_rgb(hstr):
    """
    >>> _hex_to_rgb("#fafafa")
    (250, 250, 250)
    """
    return tuple(int(c) for c in bytes.fromhex(hstr.lstrip("#")))


def _convert_volume(sym, base, quote, tickdict, ticker):
    """
    Return volume in target units. Assumptions:
    1. ``target`` is one of BTC, ETH, USD
    2. ``sym`` is canonical (in correct format and confirmed available)
    3. ``tickdict`` has been decimated (digit strings to Decimal instances)
    4. ``quote`` is never "USDT"

    Update: API recently added ``volumeQuote``, so it's probably better
    to just combine this with ``_rank_by_volume.<locals>._helper``
    """
    target = VOL_UNIT
    if sym.endswith(target) or (target == "USD" and sym.endswith("USDT")):
        return tickdict["volumeQuote"]
    if target == "USD" or quote == "ETH":
        rate = Dec(ticker[quote + target]["last"])
    else:
        rate = 1 / Dec(ticker[target + quote]["last"])
    return Dec(ticker[sym]["volumeQuote"]) * rate


def _print_heading(client, colors, widths, numrows, volstr):
    from subprocess import check_output
    try:
        sitm = check_output(["tput", "sitm"]).decode()
        ritm = check_output(["tput", "ritm"]).decode()
    except FileNotFoundError:
        sitm = ritm = ""
    else:
        if not ritm:
            sitm = ""
    #
    bg, fg = colors
    #
    align_chars = ("<", ">" if VOL_UNIT else "<", "<", "<", ">", "")
    if HEADING not in ("normal", "slim"):
        align_chars = ("", "<") + align_chars
    #
    _w = widths[2:] if HEADING in ("normal", "slim") else widths
    head_fmt = "".join("{:%s%d}" % (a, w) for a, w in zip(align_chars, _w))
    #
    # heading background
    head_bg = bg.dark
    # heading foreground
    head_fg = fg.head_alt if HAS_24 else fg.dim
    # board
    board = (
        # background
        bg.dark if HAS_24 else bg.tint,
        # rows
        (" " * sum(widths) + "\n") * (numrows - 1),
        " " * sum(widths), "\x1b[m\x1b[K"
    )
    if HEADING == "normal":
        print(head_bg, " " * widths[0],  # heading background, left margin
              # exchange
              fg.dark, sitm,
              "{:<{w}}".format(client.exchange, w=widths[1]), ritm,
              # heading
              head_fg, head_fmt.format("Price", volstr, "Bid", "Ask",
                                       "Δ (24h)", ""), "\n",
              # hr
              fg.dark, "\x1b[4m", "─" * sum(widths), "\x1b[m", "\n",
              # board
              *board, sep="", end="")
    elif "hr_" in HEADING:
        ex_hr = (sitm, fg.faint_shade if HAS_24 else fg.dark,
                 "─" * widths[0], client.exchange,
                 "─" * (sum(widths) - len(client.exchange) - widths[0]), "\n")
        heading = (head_fg, head_fmt.format("", "", "Price", volstr, "Bid",
                                            "Ask", "Δ (24h)", ""), "\n")
        if HEADING == "hr_over":
            print(head_bg, *ex_hr, *heading, *board, sep="", end="")
        else:
            print(head_bg, *heading, *ex_hr, *board, sep="", end="")
    elif HEADING == "full":
        print(head_bg,  # heading background
              # exchange
              sitm, fg.faint_shade if HAS_24 else fg.dark,
              "─" * (sum(widths) - len(client.exchange) - widths[-1]),
              client.exchange, "─" * widths[-1], ritm, "\n",
              # heading
              head_fg, head_fmt.format("", "Pair", "Price", volstr, "Bid",
                                       "Ask", "Δ (24h)", ""), "\n",
              # hr
              fg.faint_shade if HAS_24 else fg.dark,
              "\x1b[4m", "─" * sum(widths), "\x1b[m", "\n",
              # board
              *board, sep="", end="")
    elif HEADING == "slim":
        print(head_bg, " " * widths[0],  # heading background, left margin
              # exchange
              fg.dark, sitm, "{:<{w}}".format(client.exchange, w=widths[1]),
              ritm if HAS_24 else "",
              # heading
              head_fg, head_fmt.format("Price", volstr, "Bid", "Ask",
                                       "Δ (24h)", ""), "\n",
              # board
              *board, sep="", end="")


async def _check_timestamps(all_subs, client, kill_handler, strict=True,
                            max_stale=MAX_STALE, stale_secs=STALE_SECS,
                            poll_interval=POLL_INTERVAL):
    """
    Iterate over latest ticker entries and check timestamps against ttl
    threshold.  Like ``_paint_ticker_line()``, it doesn't make sense to
    return a value for this function because it can only die if its
    outer future is cancelled.

    Sending ``SIGINT`` to pid 0 raises ``BlockingIOError`` (errno 11).
    Raising a ``KeyboardInterrupt`` works, but the teardown handlers
    registered for ``SIGINT`` won't run.

    Note: The API docs imply that ``channel`` notifications are only
    pushed when a change in price has occurred. Simply juxtaposing the
    website's ticker with this one pretty much debunks this. Never mind
    that for many notification updates, only the timestamps have
    changed. For now, assume push consistency is governed by network
    load and other operating factors. Other APIs present
    heartbeat-related options that probably require an actual
    understanding of websockets standards/conventions.
    """
    from itertools import cycle
    from datetime import datetime
    while not client.ticker_subscriptions:
        await asyncio.sleep(poll_interval)
    stale_subs = set()
    for sym in cycle(all_subs):
        ts_str = client.ticker[sym]["timestamp"]
        if ts_str is None:
            continue
        ts = _make_date(ts_str)
        diff = (datetime.utcnow() - ts).seconds
        if diff > stale_secs:
            m = diff // stale_secs
            s = diff % stale_secs
            client.echo("Stale timestamp for %r. "
                        "Off by %d min %d secs" % (sym, m, s), 5)
            stale_subs.add(sym)
            if strict and len(stale_subs) / len(all_subs) > max_stale:
                kill_handler(error="The number of pairs awaiting updates has "
                             "exceeded the maximum allowed")
            else:
                client.ticker[sym]["timestamp"] = None  # <- mark as stale
        else:
            stale_subs.discard(sym)
        await asyncio.sleep(poll_interval)
    client.echo("Exiting", 6)


async def _paint_ticker_line(lnum, sym, semaphore, snapshots, ticker, fmt,
                             colors, bq_pair, wait=1.0, pulse_over=PULSE_OVER):
    """
    The kwargs are tweakable and should perhaps be presented as global
    options. ``wait`` is the update period. ``pulse_over`` is the
    red/green flash threshold.
    """
    base, quote = bq_pair
    if quote == "USD" and Dec(ticker.get(sym, {}).get("last", 0)) >= 10:
        for _s in ("_vol", "ask", "_chg"):
            fmt = fmt.replace("f}{%s" % _s, ".2f}{%s" % _s)
    #
    cbg, cfg = colors
    sep = "/"
    bg = cbg.shade if lnum % 2 else cbg.tint
    up = "\x1b[A" * lnum + "\r"
    down = "\x1b[B" * lnum
    last_seen = {}
    #
    # Delay pulsing while staggering initial update
    pulse_over, pulse_delay, pulse = Dec(pulse_over), 5, None
    _pulse_over = Dec(pulse_over + pulse_delay)
    from random import random
    #
    while True:
        # Without this, pulses get backlogged/front-loaded and fire in a
        # fusillade on init, sometimes after a short hang. Not sure why.
        if _pulse_over > pulse_over:
            _pulse_over -= Dec(1)
            _wait = random()
        await asyncio.sleep(_wait)
        _wait = wait
        if pulse:
            latest = last_seen
        else:
            latest = decimate(dict(ticker.get(sym)))
            if snapshots.get(sym) and snapshots[sym] == latest:
                continue
            last_seen = snapshots.setdefault(sym, latest)
            # Better to save as decimal quotient and only display as percent
            change = ((latest["last"] - latest["open"]) / latest["open"])
            latest["change"] = change
            # Use explicit value for ``normal`` instead of ``\e[39m`` to reset
            clrs = dict(_beg=bg, _sym=cfg.dim, _sepl=cfg.normal,
                        _sepr=cfg.dim, _prc=cfg.normal, _vol=cfg.dim,
                        _chg="", _end="\x1b[m\x1b[K")
            clrs["_chg"] = (cfg.red if change < 0 else
                            cfg.green if change > 0 else clrs["_vol"])
        #
        volconv = None
        if VOL_UNIT:
            volconv = _convert_volume(sym, base, quote, latest, ticker)
        #
        with await semaphore:
            print(up, end="")
            if pulse:
                if HAS_24:
                    clrs["_beg"] = (cbg.mix_green if
                                    pulse == "+" else cbg.mix_red)
                else:
                    clrs["_beg"] = bg
                    clrs["_prc"] = clrs["_chg"] = \
                        cfg.bright_green if pulse == "+" else cfg.bright_red
                    clrs["_vol"] = cfg.green if pulse == "+" else cfg.red
                _wait = 0.124 if PULSE == "fast" else 0.0764
                pulse = None
            elif latest["timestamp"] is None:
                clrs.update(dict(_sym=cfg.dark, _sepl="", _sepr="",
                                 _prc=(cfg.faint_shade if lnum % 2 else
                                       cfg.faint_tint), _vol="", _chg=""))
                change, pulse = 0, None
            # Must divide by 100 because ``_pulse_over`` is a %
            elif (abs(abs(latest["last"]) - abs(last_seen["last"])) >
                  abs(_pulse_over / 100 * last_seen["last"])):
                pulse = None
                _wait = 0.0764 if PULSE == "fast" else 0.124
                if change - last_seen["change"] > 0:
                    pulse = "+"
                    clrs["_beg"] = cbg.green
                    if not HAS_24:
                        clrs.update(dict(_sym=cfg.green, _sepl="", _sepr="",
                                         _vol="", _prc="", _chg=""))
                else:
                    pulse = "-"
                    clrs["_beg"] = cbg.red
                    if not HAS_24:
                        clrs.update(dict(_sym=cfg.red, _sepl="", _sepr="",
                                         _vol="", _prc="", _chg=""))
            print(fmt.format("", "",
                             base=base.lower(), sep=sep, quote=quote.lower(),
                             **clrs, **latest, volconv=volconv),
                  down, sep="", end="", flush=True)
        last_seen.update(latest)


async def do_run_ticker(syms, client, loop, manage_subs=True,
                        manage_sigs=True):
    """
    Only works with ansi/vt terminals. Keys returned by api call::

        "ask", "bid", "last", "open", "low", "high", "volume",
        "volumeQuote", "timestamp", "symbol"

    The value of ``open`` is that of ``last`` from 24 hours ago and is
    continuous/"moving". This can't be gotten with the various ``*Candle``
    calls because the limit for ``period="M1"`` is 1000, but we'd need 1440.
    """
    if manage_sigs:
        # Actually unnecessary since existing uses default handler
        old_sig_info = remove_async_sig_handlers("SIGINT", loop=loop).pop()

        def rt_sig_cb(**kwargs):
            if not gathered.cancelled():
                kwargs.setdefault("msg", "Cancelling gathered")
                try:
                    gathered.set_result(kwargs)
                except asyncio.futures.InvalidStateError:
                    # Not sure if the repr displays exception if set
                    client.echo("Already done: %r" % gathered)
                else:
                    client.echo("gathered: %r" % gathered)
                finally:
                    add_async_sig_handlers(old_sig_info, loop=loop)
            # XXX Is this obsolete? See related note for last try/except below
            else:
                client.echo("Already cancelled: %r" % gathered)

        # No need to partialize since ``gathered``, which ``rt_sig_cb``
        # should have closure over once initialized below, will be the same
        # object when the trap is sprung
        add_async_sig_handlers(("SIGINT", rt_sig_cb), loop=loop)
    #
    from collections import namedtuple
    c_bg_nt = namedtuple("background_colors",
                         "shade tint dark red mix_red green mix_green")
    c_fg_nt = namedtuple("foreground_colors",
                         "normal dim dark faint_shade faint_tint "
                         "red bright_red green bright_green head_alt")
    tc_bg_tmpl, tc_fg_tmpl = "\x1b[48;2;{};{};{}m", "\x1b[38;2;{};{};{}m"
    # Pulse blends (shade, tint): red(#293a49, #2a3d4d), gr(#12464f, #134953)
    # These tones are too similar to justify defining separately
    if HAS_24:
        c_bg = c_bg_nt(*(tc_bg_tmpl.format(*_hex_to_rgb(x)) for x in
                         "#14374A #163E53 #153043 "
                         "#3E3D48 #293a49 #105554 #12464f".split()))
        c_fg = c_fg_nt(*(tc_fg_tmpl.format(*_hex_to_rgb(x)) for x in
                         "#d3d7cf #a1b5c1 #325a6a #224a5a #153043 "
                         "#BF4232 #E55541 #01A868 #0ACD8A #507691".split()))
    else:
        c_bg = c_bg_nt(*("\x1b[48;5;23%sm" % n for n in "6785555"))
        c_fg = c_fg_nt(*("\x1b[38;5;%sm" % n for n in
                         "253 250 243 237 236 95 167;1 65 83;1 228".split()))
    #
    ranked = []
    # Need to preserve order, so can't use set union here
    for sym in reversed(syms):
        try:
            symbol = await client.canonicalize_pair(sym)
        except ValueError as e:
            # Could use ``warnings.warn`` for stuff like this
            print(e, "Removing...", file=sys.stderr)
        else:
            if symbol not in ranked:
                ranked.append(symbol)
    #
    # TODO need auto-culling option  crap shoot
    if len(ranked) > MAX_HEIGHT:
        msg = ("Too many pairs requested for current terminal height. "
               "Over by %d." % (len(ranked) - MAX_HEIGHT))
        return {"error": msg}
    #
    all_subs = set(ranked)
    # Ensure conversion pairs available for all volume units
    if VOL_UNIT:
        if manage_subs:
            all_subs |= {"BTCUSD", "ETHUSD"}
        else:
            client.echo("The ``VOL_UNIT`` option requires ``manage_subs``", 3)
            globals()["VOL_UNIT"] = None
    #
    # Results to return
    out_futs = {}
    #
    # Abbreviations
    _cv, cls, clt = _convert_volume, client.symbols, client.ticker
    bC, qC = "baseCurrency", "quoteCurrency"
    #
    if manage_subs:
        await apply_many(client.subscribe_ticker, all_subs)
        max_tries = 3
        while max_tries:
            if all(s in clt and s in cls for s in ranked):
                break
            await asyncio.sleep(1)
            max_tries -= 1
        else:
            out_futs["subs"] = await apply_many(client.unsubscribe_ticker,
                                                all_subs)
            out_futs["error"] = "Problem subscribing to remote service"
            return out_futs
    #
    if VOL_UNIT and VOL_SORTED:
        vr = sorted((_cv(s, cls[s][bC], cls[s][qC], decimate(clt[s]), clt), s)
                    for s in ranked)
        ranked = [s for v, s in vr]
    #
    # Arbitrarily assume biggest volume and/or change could grow 10x between
    # open/close, so +1 for those.
    #
    # TODO move all this widths figuring to a separate coro that updates some
    # shared location at regular intervals. If max column width is exceeded,
    # just lower precision for the offending item. So, if some "change" value
    # were to grow from 99.99 to 100.00, make it 100.0 instead.
    sep = "/"
    volstr = "Vol (%s)" % (VOL_UNIT or "base") + ("  " if VOL_UNIT else "")
    if VOL_UNIT:
        vprec = "USD ETH BTC".split().index(VOL_UNIT)
    # Market (symbol) pairs will be "concatenated" (no intervening padding)
    sym_widths = (
        # Base
        max(len(cls[s][bC]) for s in ranked),
        # Sep
        len(sep),
        # Quote (corner case: left-justifying, so need padding)
        max(len(cls[s][qC]) for s in ranked)
    )
    # Can't decide among exchange name, "" (blank), "Pair," and "Product"
    widths = (
        # 1: Exchange name
        max(sum(sym_widths), len(client.exchange)),
        # 2: Price
        max(len("{:.2f}".format(Dec(clt[s]["last"])) if
                "USD" in s else clt[s]["last"]) for s in ranked),
        # 3: Volume
        max(*(len("{:,.{pc}f}".format(_cv(s, cls[s][bC], cls[s][qC],
                                          decimate(clt[s]), clt), pc=vprec) if
                  VOL_UNIT else clt[s]["volume"]) for s in ranked),
            len(volstr)),
        # 4: Bid
        max(len("{:.2f}".format(Dec(clt[s]["bid"])) if
                "USD" in s else clt[s]["bid"]) for s in ranked),
        # 5: Ask
        max(len("{:.2f}".format(Dec(clt[s]["ask"])) if
                "USD" in s else clt[s]["ask"]) for s in ranked),
        # 6: Change (should maybe do max++ for breathing room)
        max(len("{:+.3f}%".format(
            (Dec(clt[s]["last"]) - Dec(clt[s]["open"])) / Dec(clt[s]["open"])
        )) for s in ranked),
    )
    pad = 2
    widths = (pad,  # <- 0: Left padding
              *(l + pad for l in widths),
              pad)  # <- 7: Right padding
    del _cv, cls, clt, bC, qC
    #
    # Die nicely when needed width exceeds what's available
    if sum(widths) > os.get_terminal_size().columns:
        msg = ("Insufficient terminal width. Need %d more column(s)."
               % (sum(widths) - os.get_terminal_size().columns))
        out_futs["error"] = msg
        if manage_subs:
            out_futs["subs"] = await apply_many(client.unsubscribe_ticker,
                                                all_subs)
        return out_futs
    # Format string for actual line items
    fmt = "".join(("{_beg}{:%d}" % widths[0],
                   "{_sym}{base}{_sepl}{sep}{_sepr}{quote:<{quote_w}}",
                   "{_prc}{last:<%df}" % widths[2],
                   "{_vol}",
                   ("{volconv:>%d,.%df}%s" % (widths[3] - pad, vprec,
                                              " " * pad) if
                    VOL_UNIT else "{volume:<%df}" % widths[3]),
                   "{bid:<%df}" % widths[4],
                   "{ask:<%df}" % widths[5],
                   "{_chg}{change:>+%d.3%%}" % widths[6],
                   "{:%d}{_end}" % widths[7]))
    #
    _print_heading(client, (c_bg, c_fg), widths, len(ranked), volstr)
    #
    semaphore = asyncio.Semaphore(1)
    snapshots = {}
    coros = []
    for lnum, sym in enumerate(ranked):
        base = client.symbols[sym]["baseCurrency"]
        quote = client.symbols[sym]["quoteCurrency"]
        fmt_nudge = fmt.replace("{quote_w}", "%d" %
                                (len(quote) + sym_widths[0] - len(base) + pad))
        coros.append(_paint_ticker_line(
            lnum, sym, semaphore, snapshots, client.ticker, fmt_nudge,
            (c_bg, c_fg), (base, quote), wait=(0.1 * len(ranked)),
            pulse_over=(PULSE_OVER if PULSE else 100.0)
        ))
    # Should conversion pairs (all_subs) be included here if not displayed?
    ts_chk = _check_timestamps(all_subs, client, rt_sig_cb, STRICT_TIME)
    #
    gathered = asyncio.gather(*coros, ts_chk)
    #
    try:
        out_futs["gathered"] = await gathered
    # XXX this means ``gathered`` has been cancelled, but how would this
    # ever run? None of the signal handlers calls ``cancel()``. Seems a
    # holdover from early experimenting. Same for the check in ``rt_sig_cb``.
    except asyncio.CancelledError as e:
        out_futs["error"] = e
    finally:
        if manage_subs:
            client.echo("Unsubscribing", 6)
            out_futs["subs"] = await apply_many(client.unsubscribe_ticker,
                                                all_subs)
        if manage_sigs:
            add_async_sig_handlers(old_sig_info, loop=loop)
    return out_futs


async def main(loop, syms):
    Client = HitBTCWebSocketsClient
    async with Client(VERBOSITY, LOGFILE, USE_AIOHTTP) as client:
        #
        rt_fut = do_run_ticker(syms, client, loop)
        # ``asyncio.CancelledError`` is not raised when interrupting
        # ``run_ticker`` with ^C. Seems like it's only raised by calling
        # ``Future.result()`` or "Future.cancel()" or ``Task.cancel()``
        return await rt_fut


def main_entry():
    global HAS_24, LOGFILE, PULSE, PULSE_OVER, HEADING, MAX_HEIGHT, \
            STRICT_TIME, VERBOSITY, VOL_SORTED, VOL_UNIT, USE_AIOHTTP
    #
    if sys.platform != 'linux':
        raise SystemExit("Sorry, but this probably only works on Linux")
    if sys.version_info < (3, 6):
        raise SystemExit("Sorry, but this thing needs Python 3.6+")
    #
    from enum import Enum

    class Headings(Enum):
        slim = 1
        normal = hr_over = hr_under = 2
        full = 3
    #
    VERBOSITY = int(os.getenv("VERBOSITY", VERBOSITY))
    USE_AIOHTTP = any(s == os.getenv("USE_AIOHTTP", str(USE_AIOHTTP)).lower()
                      for s in "yes true 1".split())
    HAS_24 = (
        any(s == os.getenv("COLORTERM", "") for s in ("24bit", "truecolor")) or
        any(s == os.getenv("HAS_24", str(HAS_24)).lower() for
            s in "24bit truecolor yes on true 1".split())
    )
    STRICT_TIME = any(s == os.getenv("STRICT_TIME", str(STRICT_TIME)).lower()
                      for s in "yes on true 1".split())
    PULSE = os.getenv("PULSE", PULSE)
    if PULSE.lower() in "0 off false no null none".split():
        PULSE = None
    PULSE_OVER = float(os.getenv("PULSE_OVER", PULSE_OVER))
    _heading = os.getenv("HEADING", HEADING)
    HEADING = (_heading if _heading in Headings.__members__ else HEADING)
    VOL_SORTED = any(s == os.getenv("VOL_SORTED", str(VOL_SORTED)).lower()
                     for s in "yes on true 1".split())
    VOL_UNIT = os.getenv("VOL_UNIT", VOL_UNIT)
    if VOL_UNIT.lower() in ("", "null", "none"):
        VOL_UNIT = None
    #
    num, syms = None, []
    # TODO combine this stuff with the max-rows check in do_run()
    MAX_HEIGHT = os.get_terminal_size().lines - Headings[HEADING].value
    if len(sys.argv) == 1:
        num = min(MAX_HEIGHT, SHOW_FIRST)
    elif sys.argv[1] in ("--help", "-h"):
        print(__doc__.partition("\nWarn")[0].partition("::\n")[-1])
        sys.exit()
    elif sys.argv[1].isdigit():
        num = int(sys.argv[1])
        syms = sys.argv[2:]
    else:
        syms = sys.argv[1:]
    if num:
        syms += _get_top_markets(num)
    if not syms:
        raise ValueError("Could not determine trading pairs to display")
    #
    loop = asyncio.get_event_loop()
    add_async_sig_handlers("SIGINT SIGTERM".split(), loop=loop)
    #
    LOGFILE = os.getenv("LOGFILE", None)
    #
    # Since this doesn't use curses, shell out to get cursor vis
    # escape sequences, if supported (absent in ansi and vt100).
    civis = cnorm = ""
    from subprocess import check_output
    try:
        civis = check_output(["tput", "civis"]).decode()
        cnorm = check_output(["tput", "cnorm"]).decode()
    except FileNotFoundError:
        pass
    else:
        print(civis, end="", flush=True)
    #
    if LOGFILE and os.path.exists(LOGFILE):
        from contextlib import redirect_stderr
        # Multi-context comma syntax doesn't scope left to right, so must nest:
        with open(os.getenv("LOGFILE"), "w") as LOGFILE:
            with redirect_stderr(LOGFILE):
                try:
                    ppj(loop.run_until_complete(main(loop, syms)),
                        file=LOGFILE)
                except RuntimeError as e:
                    if "loop stopped before Future completed" not in str(e):
                        raise
                finally:
                    print(cnorm, "\x1b[K")
    else:
        VERBOSITY = 3
        try:
            results = loop.run_until_complete(main(loop, syms))
        except RuntimeError as e:
            if "loop stopped before Future completed" not in str(e):
                raise
        else:
            if "error" in results:
                print(results["error"], file=sys.stderr)
            if "error" in results.get("gathered", {}):
                print(results["gathered"]["error"], file=sys.stderr)
        finally:
            print(cnorm, "\x1b[K")


if __name__ == "__main__":
    sys.exit(main_entry())

# Copyright 2017 Jane Soko <boynamedjane@misled.ml>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
