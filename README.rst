####################
Terminal Coin Ticker
####################

Not much to this at the moment. Just a silly attempt at a basic coin ticker for
modern terminal emulators. Pass ``--help`` for usage. Python 3.6+ and (likely)
Linux only.

   +--------------------------+--------------------------+
   | |24norm|                 | |24fast|                 |
   +--------------------------+--------------------------+
   | |cts|                    | |cts| |puf|              |
   +--------------------------+--------------------------+
   | |256norm|                | |256fast|                |
   +--------------------------+--------------------------+
   | Newer screenshots soon...| |puf|                    |
   +--------------------------+--------------------------+

.. |cts| replace:: ``COLORTERM=truecolor``
.. |ctu| replace:: ``COLORTERM=``
.. |pun| replace:: ``PULSE=normal``
.. |puf| replace:: ``PULSE=fast``
.. |24norm| image:: https://asciinema.org/a/0eK0ZkV3vwOwQeLnoAaCpxh3i.png
   :target: https://asciinema.org/a/0eK0ZkV3vwOwQeLnoAaCpxh3i?size=medium&cols=73
   :alt: 24-bit normal
   :width: 100 %
.. |24fast| image:: https://asciinema.org/a/RjDVhCu4124ZXPFlrIoTCKAGP.png
   :target: https://asciinema.org/a/RjDVhCu4124ZXPFlrIoTCKAGP?size=medium&cols=79
   :alt: 24-bit fast
   :width: 100 %
.. |256norm| image:: https://asciinema.org/a/Nxvzi1WAwbnqijsQpIcBsTsOC.png
   :target: https://asciinema.org/a/Nxvzi1WAwbnqijsQpIcBsTsOC?size=medium&cols=73
   :alt: 256-color normal
   :width: 100 %
.. |256fast| image:: https://asciinema.org/a/gJXa6omitnqW7fxAIKay6a8bP.png
   :target: https://asciinema.org/a/gJXa6omitnqW7fxAIKay6a8bP?size=medium&cols=73
   :alt: 256-color fast
   :width: 100 %


Installation
    An executable wrapper, ``tc-ticker``, is available when installed via pip.
    Otherwise, ``/terminal_coin_ticker/ticker.py`` works as a file arg, so long
    as the Python interpreter being invoked can summon either websockets_ or
    aiohttp_.

.. _aiohttp: https://aiohttp.readthedocs.io
.. _websockets: https://websockets.readthedocs.io


Notes
    ``HAS_24`` can be used instead of ``COLORTERM`` in environments where the
    latter is forbidden. The board's width is ultimately determined by the
    price with the most decimal places (that with the smallest "tick size").
    Prices exceeding $10 in the USD(T) market are rounded to cents.


TODO
    #. Move this list to one or multiple issues threads
    #. Decouple the ticker from the client in order to accommodate an
       alternate/fallback; these exchanges currently support websockets:
       Bitfinex_, Binance_, Poloniex_, OKEx_. Another option would be to use a
       separate library like ccxt_ (once they implement_ their websockets
       plans_). Probably also need some unit tests to ease the transition.
    #. Make compatible with lower 3.x versions. Seems the only roadblocks are
       ``async``/``await`` and ``__aiter__``.
    #. Cache session args (pairs) for use easy reuse
    #. If sort-by-volume is on, re-order while running (might be disorienting,
       so maybe this should be optional)
    #. Convert env vars to proper ``argparse``/``getopt`` options
    #. Investigate this further: as of late December, 2017, a big discrepancy
       exists between HitBTC's main ``/market-overview`` web page and its API
       ticker data for all Ether-market pairs. The site lists volumes roughly
       matching what ``volumeQuote`` would be if expressed in BTC.
       CoinMarketCap's mixed-market summary for the exchange honors the API's
       claim of ``{ "quoteCurrency": "ETH" }``. This seems consistent with
       trading activity on other exchanges.

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
