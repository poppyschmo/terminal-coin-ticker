#!/bin/python3
# -*- coding: UTF-8 -*-
"""
Usage::

    tc-ticker [NUM] [PAIR ...]

    Show NUM volume leaders and/or named PAIRs, which can take any of the
    following (case-insensitive) forms:

        basequote, base_quote, base/quote, "base quote"

    For now, all options are env-var based and subject to change

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
from enum import Enum

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))

from terminal_coin_ticker import (  # noqa E402
    add_async_sig_handlers, remove_async_sig_handlers, ppj, decimate
)
from terminal_coin_ticker.clients import hitbtc, binance  # noqa E402

# Env vars
EXCHANGE = "HitBTC"  # Or Binance (slim pickings, at the moment)
VOL_SORTED = True    # Sort all pairs by volume, AUTO_FILL'd or named
VOL_UNIT = "USD"     # BTC, ETH, etc., or null for base currencies
HAS_24 = False       # Override COLORTERM if outlawed in environment
PULSE = "normal"     # Flash style of "normal," "fast," or null (off)
PULSE_OVER = 0.125   # Flash threshold as % change in last price
HEADING = "normal"   # Also "hr_over," "hr_under," "full," and "slim"
AUTO_CULL = True     # Drop excess PAIRs, and warn instead of exiting
AUTO_FILL = True     # Absent NUM, add volume leaders till MAX_FILL
MAX_FILL = 24        # Or null/non-int to use term height (absent NUM)
STRICT_TIME = True   # Die when service notifications aren't updating
VERBOSITY = 6        # Ignored without LOGFILE (device, file, etc.)
USE_AIOHTTP = False  # Ignored unless ``websockets`` is also installed

# TTL vars
MAX_STALE = 0.5      # Tolerance threshold ratio of stale/all pairs
STALE_SECS = 15      # Max seconds pair data is considered valid
POLL_INTERVAL = 10   # Seconds to wait between checks


class Headings(Enum):
    slim = 1
    normal = hr_over = hr_under = 2
    full = 3


def _convert_volume(client, sym, base, quote, tickdict):
    """
    Return volume in target units. Assumptions:
    1. ``target`` exists in ``client.markets``
    2. ``sym`` is canonical (in correct format and confirmed available)
    3. ``tickdict`` has been decimated (digit strings to Decimal instances)
    """
    # XXX this might be better suited as a decorator that returns a
    # converter already primed with all the exchange particulars.
    target = VOL_UNIT
    #
    # At least for HitBTC, Symbol records have a "quoteCurrency" entry
    # that's always "USD", but some symbols end in "USDT"
    if sym.endswith(target) or (target == "USD" and sym.endswith("USDT")):
        return tickdict["volQ"]
    #
    assert client.conversions is not None
    if quote + target in client.conversions:
        rate = Dec(client.ticker[quote + target]["last"])
    else:
        rate = 1 / Dec(client.ticker[target + quote]["last"])
    return Dec(client.ticker[sym]["volQ"]) * rate


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
    nl = "\x1b[m\n"
    # heading background
    head_bg = bg.dark
    # heading foreground
    head_fg = fg.head_alt if HAS_24 else fg.dim
    # board
    board = (
        *(bg.dark if HAS_24 else bg.tint, " " * sum(widths),
          "\x1b[m\n") * (numrows - 1),
        bg.dark if HAS_24 else bg.tint, " " * sum(widths), "\x1b[m\x1b[K"
    )
    if HEADING == "normal":
        print(head_bg, " " * widths[0],  # heading background, left margin
              # exchange
              fg.dark, sitm,
              "{:<{w}}".format(client.exchange, w=widths[1]), ritm,
              # heading
              head_fg, head_fmt.format("Price", volstr, "Bid", "Ask",
                                       "Δ (24h)", ""), nl,
              # hr
              head_bg, fg.dark, "\x1b[4m", "─" * sum(widths), nl,
              # board
              *board, sep="", end="")
    elif "hr_" in HEADING:
        ex_hr = (head_bg, sitm, fg.faint_shade if HAS_24 else fg.dark,
                 "─" * widths[0], client.exchange,
                 "─" * (sum(widths) - len(client.exchange) - widths[0]), nl)
        heading = (head_bg, head_fg,
                   head_fmt.format("", "", "Price", volstr, "Bid", "Ask",
                                   "Δ (24h)", ""), nl)
        if HEADING == "hr_over":
            print(*ex_hr, *heading, *board, sep="", end="")
        else:
            print(*heading, *ex_hr, *board, sep="", end="")
    elif HEADING == "full":
        print(  # exchange
              head_bg, sitm, fg.faint_shade if HAS_24 else fg.dark,
              "─" * (sum(widths) - len(client.exchange) - widths[-1]),
              client.exchange, "─" * widths[-1], ritm, nl,
              # heading
              head_bg, head_fg,
              head_fmt.format("", "Pair", "Price", volstr, "Bid", "Ask",
                              "Δ (24h)", ""), nl,
              # hr
              head_bg, fg.faint_shade if HAS_24 else fg.dark,
              "\x1b[4m", "─" * sum(widths), nl,
              # board
              *board, sep="", end="")
    elif HEADING == "slim":
        print(head_bg, " " * widths[0],  # heading background, left margin
              # exchange
              fg.dark, sitm, "{:<{w}}".format(client.exchange, w=widths[1]),
              ritm if HAS_24 else "",
              # heading
              head_fg, head_fmt.format("Price", volstr, "Bid", "Ask",
                                       "Δ (24h)", ""), nl,
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
        ts_str = client.ticker[sym]["time"]
        if ts_str is None:
            continue
        diff = (datetime.utcnow() - client.make_date(ts_str)).seconds
        if diff > stale_secs:
            if LOGFILE:
                # Using ``*.call_soon`` doesn't seem to make a difference here
                client.echo("Stale timestamp for %r. Off by %d min %d secs" %
                            (sym, *divmod(diff, 60)), 5)
            stale_subs.add(sym)
            if strict and len(stale_subs) / len(all_subs) > max_stale:
                kill_handler(error="The number of pairs awaiting updates has "
                             "exceeded the maximum allowed",
                             msg="Killed by _check_timestamps")
                break
            else:
                client.ticker[sym]["time"] = None  # <- mark as stale
        else:
            stale_subs.discard(sym)
        try:
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            break
    client.echo("Exiting", 6)
    return "_check_timestamps cancelled"


async def _paint_ticker_line(client, lnum, sym, semaphore, snapshots, fmt,
                             colors, bq_pair, wait=1.0, pulse_over=PULSE_OVER):
    """
    The kwargs are tweakable and should perhaps be presented as global
    options. ``wait`` is the update period. ``pulse_over`` is the
    red/green flash threshold.
    """
    base, quote = bq_pair
    cbg, cfg = colors
    sep = "/"
    bg = cbg.shade if lnum % 2 else cbg.tint
    up = "\x1b[A" * lnum + "\r"
    down = "\x1b[B" * lnum
    tick = Dec(client.symbols[sym]["tick"])
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
        try:
            await asyncio.sleep(_wait)
        except asyncio.CancelledError:
            break
        _wait = wait
        if pulse:
            latest = last_seen
        else:
            latest = decimate(dict(client.ticker[sym]))
            if client.quantize is True:
                for key in ("last", "ask", "bid"):
                    latest[key] = latest[key].quantize(tick)
            if snapshots.get(sym) and snapshots[sym] == latest:
                continue
            last_seen = snapshots.setdefault(sym, latest)
            # Better to save as decimal quotient and only display as percent
            change = ((latest["last"] - latest["open"]) / latest["open"])
            latest["chg"] = change
            # Use explicit value for ``normal`` instead of ``\e[39m`` to reset
            clrs = dict(_beg=bg, _sym=cfg.dim, _sepl=cfg.normal,
                        _sepr=cfg.dim, _prc=cfg.normal, _vol=cfg.dim,
                        _chg="", _end="\x1b[m\x1b[K")
            clrs["_chg"] = (cfg.red if change < 0 else
                            cfg.green if change > 0 else clrs["_vol"])
        #
        volconv = None
        if VOL_UNIT:
            volconv = _convert_volume(client, sym, base, quote, latest)
        #
        if pulse:
            if HAS_24:
                clrs["_beg"] = (cbg.mix_green if
                                pulse == "+" else cbg.mix_red)
            else:
                clrs["_beg"] = bg
                clrs["_prc"] = clrs["_chg"] = (
                    cfg.bright_green if pulse == "+" else cfg.bright_red
                )
                clrs["_vol"] = cfg.green if pulse == "+" else cfg.red
            _wait = 0.124 if PULSE == "fast" else 0.0764
            pulse = None
        elif latest["time"] is None:
            clrs.update(dict(_sym=cfg.dark, _sepl="", _sepr="",
                             _prc=(cfg.faint_shade if lnum % 2 else
                                   cfg.faint_tint), _vol="", _chg=""))
            change, pulse = 0, None
        # Must divide by 100 because ``_pulse_over`` is a %
        elif (abs(abs(latest["last"]) - abs(last_seen["last"])) >
              abs(_pulse_over / 100 * last_seen["last"])):
            pulse = None
            _wait = 0.0764 if PULSE == "fast" else 0.124
            if change - last_seen["chg"] > 0:
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
        try:
            with await semaphore:
                print(up,
                      fmt.format("", "", base=base.lower(), sep=sep,
                                 quote=quote.lower(), **clrs, **latest,
                                 volconv=volconv),
                      down,
                      sep="", end="", flush=True)
        except asyncio.CancelledError:
            break
        last_seen.update(latest)
    #
    return "Cancelled _paint_ticker_line for: %s" % sym


async def do_run_ticker(ranked, client, loop, manage_subs=True,
                        manage_sigs=True):
    """
    Common keys::

        "ask", "bid", "last", "open", "volB",
        "volQ", "time", "sym", "chg", "chgP"

    The value of ``open`` is that of ``last`` from 24 hours ago and is
    continuous/"moving". This can't be gotten with the various ``*Candle``
    calls because the limit for ``period="M1"`` is 1000, but we'd need 1440.
    """
    if manage_sigs:
        # Actually unnecessary since existing uses default handler
        old_sig_info = remove_async_sig_handlers("SIGINT", loop=loop).pop()

        def rt_sig_cb(**kwargs):
            kwargs.setdefault("msg", "Received SIGINT, quitting")
            out_futs.update(kwargs)
            if not all(t.cancelled() for t in tasks):
                client.echo("Cancelling tasks")
                for task in tasks:
                    task.cancel()
            # Not sure if this can ever run. Thinking is if user sends multiple
            # SIGINTs in rapid succession. Tried naive test w. kill util.
            # Didn't trigger, but need to verify.
            else:
                client.echo("Already cancelled: %r" % gathered)
                loop.call_later(0.1,
                                client.echo, "Cancelled tasks: %r" % tasks)
            add_async_sig_handlers(old_sig_info, loop=loop)

        # No need to partialize since ``gathered``, which ``rt_sig_cb``
        # should have closure over once initialized below, will be the same
        # object when the trap is sprung
        add_async_sig_handlers(("SIGINT", rt_sig_cb), loop=loop)
    #
    c_fg = client.foreground_256
    c_bg = client.background_256
    if HAS_24:
        if client.foreground_24 is None:
            globals()["HAS_24"] = False
        else:
            c_fg = client.foreground_24
            c_bg = client.background_24
    #
    all_subs = set(ranked)
    # Ensure conversion pairs available for all volume units
    if VOL_UNIT:
        if "USD" not in VOL_UNIT and VOL_UNIT not in client.markets:
            # XXX should eventually move this block somewhere else
            return {"error": "%r is not a market currency supported by %s" %
                    (VOL_UNIT, client.exchange)}
        if manage_subs:
            if VOL_UNIT == "USD" and "USD" not in client.markets:
                assert "USDT" in client.markets
                globals()["VOL_UNIT"] = "USDT"
            all_subs |= await client.get_market_conversion_pairs(VOL_UNIT)
        else:
            client.echo("The ``VOL_UNIT`` option requires ``manage_subs``", 3)
            globals()["VOL_UNIT"] = None
    #
    # Results to return
    out_futs = {}
    #
    # Abbreviations
    cls, clt = client.symbols, client.ticker
    #
    if manage_subs:
        await asyncio.gather(*map(client.subscribe_ticker, all_subs))
        max_tries = 3
        while max_tries:
            if all(s in clt and s in cls for s in ranked):
                break
            await asyncio.sleep(1)
            max_tries -= 1
        else:
            out_futs["subs"] = await asyncio.gather(
                *map(client.unsubscribe_ticker, all_subs)
            )
            out_futs["error"] = "Problem subscribing to remote service"
            return out_futs
    #
    # TODO determine practicality of using existing volume rankings reaped
    # during arg parsing via in ``choose_pairs()``
    if VOL_UNIT and VOL_SORTED:
        vr = sorted((_convert_volume(client, s, cls[s]["curB"], cls[s]["curQ"],
                                     decimate(clt[s])), s)
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
        try:
            vprec = "USD ETH BTC".split().index(VOL_UNIT)
        except ValueError:
            vprec = 0  # Covers USDT and corners like BNB, XRP, BCH
    # Market (symbol) pairs will be "concatenated" (no intervening padding)
    sym_widths = (
        # Base
        max(len(cls[s]["curB"]) for s in ranked),
        # Sep
        len(sep),
        # Quote (corner case: left-justifying, so need padding)
        max(len(cls[s]["curQ"]) for s in ranked)
    )
    # Can't decide among exchange name, "" (blank), "Pair," and "Product"
    widths = (
        # 1: Exchange name
        max(sum(sym_widths), len(client.exchange)),
        # 2: Price
        max(len("{:.2f}".format(Dec(clt[s]["last"])) if
                "USD" in s else clt[s]["last"]) for s in ranked),
        # 3: Volume
        max(*(len("{:,.{pc}f}"
                  .format(_convert_volume(client, s, cls[s]["curB"],
                                          cls[s]["curQ"], decimate(clt[s])),
                          pc=vprec) if VOL_UNIT else clt[s]["volB"])
              for s in ranked), len(volstr)),
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
    del cls, clt
    #
    # Die nicely when needed width exceeds what's available
    if sum(widths) > os.get_terminal_size().columns:
        msg = ("Insufficient terminal width. Need %d more column(s)."
               % (sum(widths) - os.get_terminal_size().columns))
        out_futs["error"] = msg
        if manage_subs:
            out_futs["subs"] = await asyncio.gather(
                *map(client.unsubscribe_ticker, all_subs)
            )
        return out_futs
    # Format string for actual line items.
    fmt_parts = [
        "{_beg}{:%d}" % widths[0],
        "{_sym}{base}{_sepl}{sep}{_sepr}{quote:<{quote_w}}",
        "{_prc}{last:<%dg}" % widths[2],
        "{_vol}" + ("{volconv:>%d,.%df}%s" %
                    (widths[3] - pad, vprec, " " * pad) if
                    VOL_UNIT else "{volB:<%dg}" % widths[3]),
        "{bid:<%dg}" % widths[4],
        "{ask:<%dg}" % widths[5],
        "{_chg}{chg:>+%d.3%%}" % widths[6],
        "{:%d}{_end}" % widths[7]
    ]
    fmt = "".join(fmt_parts)
    #
    _print_heading(client, (c_bg, c_fg), widths, len(ranked), volstr)
    #
    semaphore = asyncio.Semaphore(1)
    snapshots = {}
    coros = []
    for lnum, sym in enumerate(ranked):
        base = client.symbols[sym]["curB"]
        quote = client.symbols[sym]["curQ"]
        fmt_nudge = (
            "".join(
                (fmt_parts[n].replace("g}", ".2f}") if n in (1, 4, 5) else
                 fmt_parts[n] for n in range(len(fmt_parts)))
            )
            if "USD" in quote and Dec(client.ticker[sym]["last"]) >= Dec(10)
            else fmt
        ).replace("{quote_w}", "%d" % (widths[1] - len(base) - len(sep)))
        #
        coros.append(_paint_ticker_line(
            client, lnum, sym, semaphore, snapshots, fmt_nudge,
            (c_bg, c_fg), (base, quote), wait=(0.1 * len(ranked)),
            pulse_over=(PULSE_OVER if PULSE else 100.0)
        ))
    # Should conversion pairs (all_subs) be included here if not displayed?
    ts_chk = _check_timestamps(all_subs, client, rt_sig_cb, STRICT_TIME)
    #
    tasks = [asyncio.ensure_future(c) for c in (*coros, ts_chk)]
    gathered = asyncio.gather(*tasks)
    #
    try:
        out_futs["gathered"] = await gathered
    except Exception as exc:
        # Repr of ``Future.exception`` only contains exc name
        out_futs["gathered"] = gathered.exception()
        from traceback import print_exc, format_exc
        if LOGFILE:
            print_exc(file=LOGFILE)
        elif not isinstance(exc, asyncio.CancelledError):
            out_futs["gathered"] = {"error": format_exc()}
    finally:
        if manage_subs:
            client.echo("Unsubscribing", 6)
            gunsubs = asyncio.gather(*map(client.unsubscribe_ticker, all_subs))
            try:
                out_futs["subs"] = await gunsubs
            # Catch network/inet errors, etc.
            except Exception:
                from traceback import print_exc, format_exc
                if LOGFILE:
                    out_futs["subs"] = gunsubs.exception()
                    print_exc(file=LOGFILE)
                else:
                    tb_str = format_exc()
                    if "ConnectionClosed" not in tb_str:
                        out_futs["subs"] = {"error": tb_str}
        if manage_sigs:
            add_async_sig_handlers(old_sig_info, loop=loop)
    return out_futs


async def choose_pairs(client):
    """
    If the length of named pairs alone exceeds the terminal height, trim
    from the end (rightmost args). Afterwards, reduce NUM leaders, as
    required. Print a warning for dropped syms if AUTO_CULL is on,
    otherwise raise a ValueError. Note: This will probably have to be
    redone when argparse stuff is added.
    """
    num = None
    syms = []
    msg = []
    #
    if len(sys.argv) == 1:
        num = min(MAX_FILL, MAX_HEIGHT)
    elif sys.argv[1].isdigit():
        num = int(sys.argv[1])
        if num == 0:  # Don't auto-fill regardless of AUTO_FILL
            num = None
        syms = sys.argv[2:]
    else:
        syms = sys.argv[1:]
        if AUTO_FILL:  # ... till MAX_FILL (or MAX_HEIGHT)
            num = 0
    #
    ranked = []
    num_skipped = 0
    # Need to preserve order, so can't use set union here
    for sym in reversed(syms):
        try:
            symbol = await client.canonicalize_pair(sym)
        except ValueError as e:
            # Could use ``warnings.warn`` for stuff like this
            msg += ["%r not found, removing..." % sym]
            if AUTO_FILL:
                num_skipped += 1
        else:
            if symbol not in ranked:
                ranked.append(symbol)
    #
    if len(ranked) > MAX_HEIGHT:
        msg += ["Too many pairs requested for current terminal height. "
                "Over by %d." % (len(ranked) - MAX_HEIGHT)]
        if not AUTO_CULL:
            raise ValueError(msg)
        culled = ranked[-1 * (len(ranked) - MAX_HEIGHT):]
        ranked = ranked[:-1 * len(culled)]
        msg += ["\nAUTO_CULL is on; dropping the following: "
                + ", ".join(culled).rstrip(", ")]
    #
    if num == 0:
        num = min(MAX_FILL, MAX_HEIGHT) - len(ranked)
    elif num is not None:
        if num + len(ranked) > MAX_HEIGHT:
            num = MAX_HEIGHT - len(ranked)
            msg += ["Too many NUM leaders requested for current terminal "
                    "height; reducing to %d" % num]
        elif num_skipped:
            num = min(num + num_skipped, MAX_HEIGHT - len(ranked))
    #
    if msg:
        if LOGFILE:
            client.echo("\n".join(msg))
        else:
            print(*msg, sep="\n", file=sys.stderr)
            from time import sleep
            sleep(1)
    #
    if not AUTO_FILL or not num:  # <- num might have been decremented to 0
        return ranked
    assert len(ranked) + num <= MAX_HEIGHT
    #
    # If VOL_SORTED is False, named pairs will be appear above ranked ones
    for symbol in await client.get_volume_leaders():
        if symbol not in ranked:
            ranked.append(symbol)
            num -= 1
        if num < 1:
            break
    return ranked


async def main(loop, Client):
    async with Client(VERBOSITY, LOGFILE, USE_AIOHTTP) as client:
        #
        ranked_syms = await choose_pairs(client)
        #
        rt_fut = do_run_ticker(ranked_syms, client, loop)
        return await rt_fut


def main_entry():
    global HAS_24, LOGFILE, PULSE, PULSE_OVER, HEADING, MAX_HEIGHT, \
            STRICT_TIME, VERBOSITY, VOL_SORTED, VOL_UNIT, USE_AIOHTTP, \
            AUTO_FILL, AUTO_CULL, EXCHANGE, MAX_FILL
    #
    if sys.platform != 'linux':
        raise SystemExit("Sorry, but this probably only works on Linux")
    if sys.version_info < (3, 6):
        raise SystemExit("Sorry, but this thing needs Python 3.6+")
    #
    if len(sys.argv) > 1 and sys.argv[1] in ("--help", "-h"):
        print(__doc__.partition("\nWarn")[0].partition("::\n")[-1])
        with open(__file__) as f:
            hunks = f.read().split("\n\n")
        lines = [p for p in hunks if
                 p.startswith("# Env vars")].pop().split("\n")[1:]
        from ast import literal_eval
        fmt = "{:<4}{:<12}{:<8}{:<9}{}"
        for line in lines:
            name, rest = line.split("=")
            val, doc = rest.split("#")
            typ = "<%s>" % type(literal_eval(val.strip())).__name__
            val = ("%s" % val.strip('" ').replace("True", "1")
                   .replace("False", "0").replace("None", "''"))
            print(fmt.format("", name.strip(), typ, val, doc.strip()))
        sys.exit()
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
    MAX_HEIGHT = os.get_terminal_size().lines - Headings[HEADING].value
    VOL_SORTED = any(s == os.getenv("VOL_SORTED", str(VOL_SORTED)).lower()
                     for s in "yes on true 1".split())
    VOL_UNIT = os.getenv("VOL_UNIT", VOL_UNIT)
    if VOL_UNIT.lower() in ("", "null", "none"):
        VOL_UNIT = None
    else:
        VOL_UNIT = VOL_UNIT.upper()
    AUTO_FILL = any(s == os.getenv("AUTO_FILL", str(AUTO_FILL)).lower()
                    for s in "yes on true 1".split())
    AUTO_CULL = any(s == os.getenv("AUTO_CULL", str(AUTO_CULL)).lower()
                    for s in "yes on true 1".split())
    MAX_FILL = os.getenv("MAX_FILL", str(MAX_FILL))
    if MAX_FILL.isdigit():
        MAX_FILL = int(MAX_FILL)
    else:
        MAX_FILL = MAX_HEIGHT
    #
    loop = asyncio.get_event_loop()
    add_async_sig_handlers("SIGINT SIGTERM".split(), loop=loop)
    #
    LOGFILE = os.getenv("LOGFILE", None)
    #
    # XXX should probably print message saying exchange not yet supported
    EXCHANGE = os.getenv("EXCHANGE", EXCHANGE).lower()
    if EXCHANGE == "binance":
        Client = binance.BinanceClient
    else:
        Client = hitbtc.HitBTCClient
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
    try:
        if LOGFILE and os.path.exists(LOGFILE):
            from contextlib import redirect_stderr
            with open(os.getenv("LOGFILE"), "w") as LOGFILE:
                with redirect_stderr(LOGFILE):
                    ppj(loop.run_until_complete(main(loop, Client)),
                        file=LOGFILE)
        else:
            VERBOSITY = 3
            results = loop.run_until_complete(main(loop, Client))
            for item in (results, results.get("gathered", {}),
                         results.get("subs", {})):
                try:
                    print("", item["error"], sep="\n", file=sys.stderr)
                except (TypeError, KeyError):
                    pass
    # XXX not sure why this was ever added
    except RuntimeError as e:
        if "loop stopped before Future completed" not in str(e):
            raise
        elif LOGFILE:
            print(e, file=LOGFILE)
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
