####################
Terminal Coin Ticker
####################

*Update 2019:* This project has been retired. PM if you want the PyPI name.

Not much to this at the moment. Just a silly attempt at a basic coin ticker for
modern terminal emulators. Pass ``--help`` for usage. Python 3.6+ and (likely)
Linux only, for now.

|screenshot|

- The plan is to have color schemes adopt exchange branding on `24-bit terms`_
- Additional asciicasts showing current/future options coming soon:

  - (|one|_) |two|_
  - (|three|_) |four|_

.. |screenshot| image:: https://user-images.githubusercontent.com
   /12665556/35732616-f16a300e-07ce-11e8-8379-8bed137f1b83.gif
.. _24-bit terms: https://gist.github.com/XVilka/8346728

.. |one| replace:: |cts|
.. |two| replace:: |puf|
.. |three| replace:: |def|
.. |four| replace:: |puf|

.. |cts| replace:: ``COLORTERM=truecolor``
.. |puf| replace:: ``PULSE=fast``
.. |def| replace:: default/256-color

.. _one: https://asciinema.org/a/0eK0ZkV3vwOwQeLnoAaCpxh3i?size=medium&cols=73
.. _two: https://asciinema.org/a/RjDVhCu4124ZXPFlrIoTCKAGP?size=medium&cols=79
.. _three: https://asciinema.org/a/Nxvzi1WAwbnqijsQpIcBsTsOC?size=medium&cols=73
.. _four: https://asciinema.org/a/gJXa6omitnqW7fxAIKay6a8bP?size=medium&cols=73


Installation
    An executable wrapper called ``tc-ticker`` is available when installed via
    pip.  Otherwise, ``/terminal_coin_ticker/ticker.py`` works as a file arg,
    so long as Python can summon websockets_ or aiohttp_.

.. _aiohttp: https://aiohttp.readthedocs.io
.. _websockets: https://websockets.readthedocs.io


Notes
    ``HAS_24`` can be used instead of ``COLORTERM`` in environments where the
    latter is forbidden. The board's width is determined by the price with the
    most decimal places (that with the smallest "tick size"). Prices exceeding
    $10 in the USD(T) market are rounded to cents.


TODO
    #. Migrate this list to one or multiple issues threads
    #. Support 3.4+. Seems the only roadblocks are ``async``/``await`` and
       ``__aiter__``
    #. Cache session args (pairs) for use easy reuse
    #. If sort-by-volume is on, re-order while running (might be disorienting,
       so maybe this should be optional)
    #. Convert env-var options to proper ``argparse``/``getopt`` options
    #. Use proper logging
    #. Fill the entire width of the terminal window with the relevant background
       color and distribute the remaining space evenly

Motivation
    Initially a favor for a friend, now more or less a renewed effort to make
    sense of this asyncio business.
