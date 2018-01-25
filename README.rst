####################
Terminal Coin Ticker
####################

Not much to this at the moment. Just a silly attempt at a basic coin ticker for
modern terminal emulators. Pass ``--help`` for usage. Python 3.6+ and (likely)
Linux only, for now.

Asciicasts
    +-------------+-------------+------------+-------------+
    | |24norm|    | |24fast|    | |256norm|  | |256fast|   |
    +-------------+-------------+------------+-------------+
    | |cts|       | |cts| |puf| | |msg|      | |puf|       |
    +-------------+-------------+------------+-------------+

.. |cts| replace:: ``COLORTERM=truecolor``
.. |puf| replace:: ``PULSE=fast``
.. |msg| replace:: *Better examples coming soon...*

.. |24norm| image:: https://asciinema.org/a/0eK0ZkV3vwOwQeLnoAaCpxh3i.png
   :target: https://asciinema.org/a/0eK0ZkV3vwOwQeLnoAaCpxh3i?size=medium&cols=73
   :width: 25 em
.. |24fast| image:: https://asciinema.org/a/RjDVhCu4124ZXPFlrIoTCKAGP.png
   :target: https://asciinema.org/a/RjDVhCu4124ZXPFlrIoTCKAGP?size=medium&cols=79
   :width: 25 em
.. |256norm| image:: https://asciinema.org/a/Nxvzi1WAwbnqijsQpIcBsTsOC.png
   :target: https://asciinema.org/a/Nxvzi1WAwbnqijsQpIcBsTsOC?size=medium&cols=73
   :width: 25 em
.. |256fast| image:: https://asciinema.org/a/gJXa6omitnqW7fxAIKay6a8bP.png
   :target: https://asciinema.org/a/gJXa6omitnqW7fxAIKay6a8bP?size=medium&cols=73
   :width: 25 em


Installation
    An executable wrapper, ``tc-ticker``, is available when installed via pip.
    Otherwise, ``/terminal_coin_ticker/ticker.py`` works as a file arg, so long
    as the Python interpreter being invoked can summon either websockets_ or
    aiohttp_.

.. _aiohttp: https://aiohttp.readthedocs.io
.. _websockets: https://websockets.readthedocs.io


Notes
    ``HAS_24`` can be used instead of ``COLORTERM`` in environments where the
    latter is forbidden. The board's width is determined by the price with the
    most decimal places (that with the smallest "tick size"). Prices exceeding
    $10 in the USD(T) market are rounded to cents.


TODO
    #. Migrate this list to one or multiple issues threads
    #. Support lower 3.x versions. Seems the only roadblocks are
       ``async``/``await`` and ``__aiter__``.
    #. Cache session args (pairs) for use easy reuse
    #. If sort-by-volume is on, re-order while running (might be disorienting,
       so maybe this should be optional)
    #. Convert env-var options to proper ``argparse``/``getopt`` options
    #. Use proper logging

.. _implement: https://github.com/ccxt/ccxt/pull/751
.. _plans: https://gist.github.com/kroitor/7dce1d23a10937ab8c07a5451f17ccf2
.. _ccxt: https://pypi.org/project/ccxt
.. _Bitfinex: https://bitfinex.readme.io/v2/reference#ws-public-ticker
.. _Binance: https://github.com/binance-exchange/binance-official-api-docs
   /blob/master/web-socket-streams.md
.. _Poloniex: https://poloniex.com/support/api/
.. _OKEx: https://www.okex.com/ws_api.html#spapi


Motivation
    Initially a favor for a friend, now more or less a renewed effort to make
    sense of this asyncio business.
