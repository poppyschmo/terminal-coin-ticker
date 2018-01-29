#!/bin/python3
# -*- coding: UTF-8 -*-

import signal
import sys


def remove_async_sig_handlers(*sigs, loop=None):
    """
    Returns a list of tuples, each of the form::

        (signal.Signals, asyncio.events.Handle._callback)

    Note: ^^^^^^^^^^^^^ is the signal (enum object) not its name. Also,
    can't just return the ``asyncio.events.Handle`` object, because
    these don't preserve any reference to the original signal number.
    """
    outlist = []
    if loop is None:
        import asyncio
        loop = asyncio.get_event_loop()
    for item in sigs:
        # Look up Enums like so: signal.Signals["SIGINT"] == signal.Signals(2)
        if isinstance(item, str):
            sig = signal.Signals[item]
        elif isinstance(item, int):
            sig = signal.Signals(sig)
        else:
            assert isinstance(item, signal.Signals)
            sig = item
        existing = loop._signal_handlers.get(sig)
        if existing:
            outlist.append((sig, existing._callback))
        if not loop.remove_signal_handler(sig):
            assert sig not in loop._signal_handlers
    return outlist


def add_async_sig_handlers(*sigs, loop=None):
    """
    ``sigs`` can be signals, names, numbers, or tuples of the form::

        (signal/name, callback_func)

    """
    from functools import partial
    if loop is None:
        import asyncio
        loop = asyncio.get_event_loop()

    def handle_sig(signame):
        print("Got a signal: %r" % signame, file=sys.stderr)
        loop.stop()

    for item in sigs:
        if isinstance(item, (str, signal.Signals)):
            sig = item
            callback = None
        else:
            sig, callback = item
        #
        if isinstance(sig, str):
            sig = getattr(signal, sig)
        elif isinstance(sig, int):
            # Reverse lookups made easy with enum
            sig = signal.Signals(sig)
        else:
            assert isinstance(sig, signal.Signals)
        #
        if not callable(callback):
            callback = partial(handle_sig, signame=sig.name)
        loop.add_signal_handler(sig, callback)
        callback = None


def decimate(inobj):
    """
    Convert numbers and numeric strings in native JSON-like objects to
    Decimal instances.
    """
    from decimal import Decimal
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
    import json
    try:
        print(json.dumps(obj, indent=2), *args, **kwargs)
    except TypeError:
        import pprint
        pprint.pprint(obj, indent=2, stream=sys.stderr)
