Change Log
==========

Unreleased_
-----------

N/A

1.2.0_ - 2023-11-25
-------------------

Added
~~~~~

- ``additional_rate_limit`` argument to
  :class:`~spacetrack.base.SpaceTrackClient`.

Fixed
~~~~~

- Since version 1.0, the value passed to ``SpaceTrackClient.callback``, if set,
  is from :func:`time.monotonic` but the documentation was not updated to reflect
  this.

1.1.0_ - 2023-10-15
-------------------

Added
~~~~~

- ``dirs`` and ``download`` request classes for the ``publicfiles`` request
  controller.
- Support for Python 3.12


Removed
~~~~~~~

- **Support for Python 3.7**


1.0.1_ - 2023-05-23
-------------------

Fixed
~~~~~

- requests which should have been streamed (e.g. ``iter_content=True``) were
  not.
- requests which need to follow redirects work again.

1.0.0_ - 2023-05-22
-------------------

Added
~~~~~

- :class:`~spacetrack.aio.AsyncSpaceTrackClient` supports Trio_ in addition to
  asyncio.

.. _Trio: https://trio.readthedocs.io/en/stable/

Changed
~~~~~~~

- The sync and async clients share the same sans-io core.
- The underlying HTTP library used is now httpx_ (formerly ``requests`` for
  :class:`~spacetrack.base.SpaceTrackClient` and ``aiohttp`` for
  :class:`~spacetrack.aio.AsyncSpaceTrackClient`). Users will need to change
  any exception handling to catch `httpx exceptions`_.

.. _httpx: https://www.python-httpx.org
.. _`httpx exceptions`: https://www.python-httpx.org/exceptions/

Removed
~~~~~~~

- The ``async`` extra no longer exists because the
  :class:`~spacetrack.aio.AsyncSpaceTrackClient` is available by default.
- **Support for Python 3.6**

Fixed
~~~~~

- The modeldef for the fileshare/download class was deprecated by Space-Track,
  so the client no longer uses this API.

0.16.0_ - 2021-01-03
--------------------

Added
~~~~~

-  Support for the `car`, `folder`, and `satellite` classes.
- A `rush storage backend`_ can be provided to a new ``rush_store`` argument to
  coordinate rate limiting across multiple instances.
- ``rush_key_prefix`` to optionally prefix keys used in the rush storage
  backend.

.. _`rush storage backend`: https://rush.readthedocs.io/en/stable/storage.html

Fixed
~~~~~

- When ``parse_types`` is used, dates are parsed using an ISO 8601 parser,
  which fixes the parsing of date formats returned by newer request classes
  (e.g. gp).

0.15.0_ - 2020-09-25
--------------------

Added
~~~~~

-  Support for the `cdm_public` and `gp_history` classes.

0.14.0_ - 2020-06-21
--------------------

Added
~~~~~

-  Support for Space-Track’s per-hour rate limit in addition to the
   per-minute limit.

Changed
~~~~~~~

-  The per-minute rate limit was increased to 30 as documented by
   Space-Track.
-  Require aiohttp 3 for the ``async`` extra.
-  :class:`~spacetrack.aio.AsyncSpaceTrackClient` is now an asynchronous
   context manager. Use ``async with`` instead of ``with``.

Removed
~~~~~~~

-  **Support for Python 2.7, 3.4, and 3.5**.

0.13.7_ - 2020-06-20
--------------------

Added
~~~~~

-  Support for the general perturbations (gp) class.

0.13.6_ - 2020-03-20
--------------------

Fixed
~~~~~

-  Regression in 0.13 that prevented ``spephemeris/download`` from
   working by trying to load a model definition which it doesn’t have.

0.13.5_ - 2020-03-18
--------------------

Fixed
~~~~~

-  The ‘text’ predicate type is now understood.
-  Unknown predicate types issue a warning instead of raising an
   exception.

0.13.4_ - 2019-12-24
--------------------

Added
~~~~~

-  ``SpaceTrackClient`` gained a ``base_url`` parameter to allow the use
   of an alternate Space-Track server.

0.13.3_ - 2019-03-11
--------------------

Fixed
~~~~~

-  The deprecation warning about importing ``Sequence`` or ``Mapping``
   from ``collections`` instead of ``collections.abc``.

0.13.2_ - 2018-12-31
--------------------

Fixed
~~~~~

-  The ``async`` extra installs aiohttp 2 because ``spacetrack`` is not
   yet aiohttp 3 compatible.
-  Deprecation warnings about invalid escape sequences.

0.13.1_ - 2018-01-18
--------------------

Fixed
~~~~~

-  ``spacetrack`` can be installed with setuptools v38.0+, which
   requires ``install_requires`` in ``setup.py`` to be ordered.

0.13.0_ - 2017-06-17
--------------------

Added
~~~~~

-  ``parse_types`` flag to optionally parse types as described by the
   ``modeldef`` API.
-  Compatibility with ``maneuver`` and ``maneuver_history`` request
   classes for ``expandedspacedata`` request controller.
-  Compatibility with ``upload`` and ``delete`` request classes for
   ``fileshare`` request controller.

Fixed
~~~~~

-  Predicates with the enum type are parsed correctly. Previously,
   single-valued enums had ``None`` as a second value, and enums with
   more than two values only had the first and last value due to the
   regex match not capturing repeated groups. The values aren’t used by
   ``spacetrack``, so the bug went unnoticed.
-  Exception on Python 3.5+ in threads without an ``asyncio`` event loop
   (even using the normal ``SpaceTrackClient``). Fixed by requiring
   ``ratelimiter`` >= 1.2.0

Changed
~~~~~~~

-  Require aiohttp >= 2.0 for the ``async`` extra.

0.12.0_ - 2016-06-28
--------------------

Added
~~~~~

-  Request controller can be passed explicitly to methods that take a
   request class, because some request classes are present in more than
   one controller.
-  Request controller proxy attribute,
   e.g. ``SpaceTrackClient.fileshare.file()``, which is equivalent to
   ``SpaceTrackClient.generic_request('file', controller='fileshare')``.
-  ``dir(SpaceTrackClient(...))`` now includes the request controllers
   and request classes so it’s easier to see what can be called.

Fixed
~~~~~

-  ``/modeldef`` API not queried if no predicates are passed. This
   allows ``spephemeris/download`` to be used, which doesn’t have a
   model definition.

Changed
~~~~~~~

-  Calling request class methods uses first request controller that
   matches. The order is stored in the keys of the
   ``SpaceTrackClient.request_controllers`` ordered dict, currently
   ``basicspacedata``, ``expandedspacedata``, ``fileshare``,
   ``spephemeris``. Any new request controllers will be added to the
   end, to preserve lookup order. New request classes that would change
   the order will accompany a major version bump.
-  ``AsyncSpaceTrackClient`` uses requests’ CA file for same experience
   with both clients.

0.11.1_ - 2016-03-01
--------------------

Fixed
~~~~~

-  Bump `ratelimiter <https://pypi.python.org/pypi/ratelimiter>`__
   version to improve rate limiting for ``AsyncSpaceTrackClient``

Changed
~~~~~~~

-  Documentation included in source distribution.

0.11.0_ - 2016-02-21
--------------------

Added
~~~~~

-  Some unit tests added for ``AsyncSpaceTrackClient``.

Fixed
~~~~~

-  ``\r\n`` to ``\n`` newline conversion for async chunk iterator.

Changed
~~~~~~~

-  ``AsyncSpaceTrackClient`` can no longer be imported from the top
   level ``spacetrack`` module, since this would cause an error if
   optional dependency ``aiohttp`` was not installed. It must be
   imported from ``spacetrack.aio``.

0.10.0_ - 2016-02-04
--------------------

Fixed
~~~~~

-  Compatibility with ``file`` and ``download`` request classes for
   ``fileshare`` request controller. ``upload`` request class removed,
   unable to test.
-  Rate limit violation HTTP status code 500 handled during predicate
   information request.

Changed
~~~~~~~

-  ``iter_lines=True`` now raises ``ValueError`` if receiving binary
   data (currently only possible with ``download`` request class).
-  Removed internal method ``_get_predicate_fields``, set comprehension
   used inline instead.
-  ``Predicate`` class now has a ``default`` attribute.

0.9.0_ - 2016-01-28
-------------------

First release.

.. _Unreleased: https://github.com/python-astrodynamics/spacetrack/compare/1.2.0...HEAD
.. _1.2.0: https://github.com/python-astrodynamics/spacetrack/compare/1.1.0...1.2.0
.. _1.1.0: https://github.com/python-astrodynamics/spacetrack/compare/1.0.1...1.1.0
.. _1.0.1: https://github.com/python-astrodynamics/spacetrack/compare/1.0.0...1.0.1
.. _1.0.0: https://github.com/python-astrodynamics/spacetrack/compare/0.16.0...1.0.0
.. _0.16.0: https://github.com/python-astrodynamics/spacetrack/compare/0.15.0...0.16.0
.. _0.15.0: https://github.com/python-astrodynamics/spacetrack/compare/0.14.0...0.15.0
.. _0.14.0: https://github.com/python-astrodynamics/spacetrack/compare/0.13.7...0.14.0
.. _0.13.7: https://github.com/python-astrodynamics/spacetrack/compare/0.13.6...0.13.7
.. _0.13.6: https://github.com/python-astrodynamics/spacetrack/compare/0.13.5...0.13.6
.. _0.13.5: https://github.com/python-astrodynamics/spacetrack/compare/0.13.4...0.13.5
.. _0.13.4: https://github.com/python-astrodynamics/spacetrack/compare/0.13.3...0.13.4
.. _0.13.3: https://github.com/python-astrodynamics/spacetrack/compare/0.13.2...0.13.3
.. _0.13.2: https://github.com/python-astrodynamics/spacetrack/compare/0.13.1...0.13.2
.. _0.13.1: https://github.com/python-astrodynamics/spacetrack/compare/0.13.0...0.13.1
.. _0.13.0: https://github.com/python-astrodynamics/spacetrack/compare/0.12.0...0.13.0
.. _0.12.0: https://github.com/python-astrodynamics/spacetrack/compare/0.11.1...0.12.0
.. _0.11.1: https://github.com/python-astrodynamics/spacetrack/compare/0.11.0...0.11.1
.. _0.11.0: https://github.com/python-astrodynamics/spacetrack/compare/0.10.0...0.11.0
.. _0.10.0: https://github.com/python-astrodynamics/spacetrack/compare/0.9.0...0.10.0
.. _0.9.0: https://github.com/python-astrodynamics/spacetrack/compare/e5fc088a96ec1557d44931e00500cdcef8349fad...0.9.0
