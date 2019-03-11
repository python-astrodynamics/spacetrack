Change Log
==========

.. _unreleasedunreleased:

`Unreleased <https://github.com/python-astrodynamics/spacetrack/compare/0.13.3...HEAD>`__
-----------------------------------------------------------------------------------------

N/A

`0.13.3 <https://github.com/python-astrodynamics/spacetrack/compare/0.13.2...0.13.3>`__
---------------------------------------------------------------------------------------

Fixed
~~~~~

-  The deprecation warning about importing ``Sequence`` or ``Mapping``
   from ``collections`` instead of ``collections.abc``.

.. _section-1:

`0.13.2 <https://github.com/python-astrodynamics/spacetrack/compare/0.13.1...0.13.2>`__
---------------------------------------------------------------------------------------

.. _fixed-1:

Fixed
~~~~~

-  The ``async`` extra installs aiohttp 2 because ``spacetrack`` is not
   yet aiohttp 3 compatible.
-  Deprecation warnings about invalid escape sequences.

.. _section-2:

`0.13.1 <https://github.com/python-astrodynamics/spacetrack/compare/0.13.0...0.13.1>`__
---------------------------------------------------------------------------------------

.. _fixed-2:

Fixed
~~~~~

-  ``spacetrack`` can be installed with setuptools v38.0+, which
   requires ``install_requires`` in ``setup.py`` to be ordered.

.. _section-3:

`0.13.0 <https://github.com/python-astrodynamics/spacetrack/compare/0.12.0...0.13.0>`__
---------------------------------------------------------------------------------------

Added
~~~~~

-  ``parse_types`` flag to optionally parse types as described by the
   ``modeldef`` API.
-  Compatibility with ``maneuver`` and ``maneuver_history`` request
   classes for ``expandedspacedata`` request controller.
-  Compatibility with ``upload`` and ``delete`` request classes for
   ``fileshare`` request controller. ### Fixed
-  Predicates with the enum type are parsed correctly. Previously,
   single-valued enums had ``None`` as a second value, and enums with
   more than two values only had the first and last value due to the
   regex match not capturing repeated groups. The values aren’t used by
   ``spacetrack``, so the bug went unnoticed.
-  Exception on Python 3.5+ in threads without an ``asyncio`` event loop
   (even using the normal ``SpaceTrackClient``). Fixed by requiring
   ``ratelimiter`` >= 1.2.0 ### Changed
-  Require aiohttp >= 2.0 for the ``async`` extra.

.. _section-4:

`0.12.0 <https://github.com/python-astrodynamics/spacetrack/compare/0.11.1...0.12.0>`__
---------------------------------------------------------------------------------------

.. _added-1:

Added
~~~~~

-  Request controller can be passed explicitly to methods that take a
   request class, because some request classes are present in more than
   one controller.
-  Request controller proxy attribute,
   e.g. \ ``SpaceTrackClient.fileshare.file()``, which is equivalent to
   ``SpaceTrackClient.generic_request('file', controller='fileshare')``.
-  ``dir(SpaceTrackClient(...))`` now includes the request controllers
   and request classes so it’s easier to see what can be called.

.. _fixed-3:

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

.. _section-5:

`0.11.1 <https://github.com/python-astrodynamics/spacetrack/compare/0.11.0...0.11.1>`__
---------------------------------------------------------------------------------------

.. _fixed-4:

Fixed
~~~~~

-  Bump `ratelimiter <https://pypi.python.org/pypi/ratelimiter>`__
   version to improve rate limiting for ``AsyncSpaceTrackClient``

.. _changed-1:

Changed
~~~~~~~

-  Documentation included in source distribution.

.. _section-6:

`0.11.0 <https://github.com/python-astrodynamics/spacetrack/compare/0.10.0...0.11.0>`__
---------------------------------------------------------------------------------------

.. _added-2:

Added
~~~~~

-  Some unit tests added for ``AsyncSpaceTrackClient``.

.. _fixed-5:

Fixed
~~~~~

-  ``\r\n`` to ``\n`` newline conversion for async chunk iterator.

.. _changed-2:

Changed
~~~~~~~

-  ``AsyncSpaceTrackClient`` can no longer be imported from the top
   level ``spacetrack`` module, since this would cause an error if
   optional dependency ``aiohttp`` was not installed. It must be
   imported from ``spacetrack.aio``.

.. _section-7:

`0.10.0 <https://github.com/python-astrodynamics/spacetrack/compare/0.9.0...0.10.0>`__ - 2016-02-04
---------------------------------------------------------------------------------------------------

.. _fixed-6:

Fixed
~~~~~

-  Compatibility with ``file`` and ``download`` request classes for
   ``fileshare`` request controller. ``upload`` request class removed,
   unable to test.
-  Rate limit violation HTTP status code 500 handled during predicate
   information request.

.. _changed-3:

Changed
~~~~~~~

-  ``iter_lines=True`` now raises ``ValueError`` if receiving binary
   data (currently only possible with ``download`` request class).
-  Removed internal method ``_get_predicate_fields``, set comprehension
   used inline instead.
-  ``Predicate`` class now has a ``default`` attribute.

.. _section-8:

`0.9.0 <https://github.com/python-astrodynamics/spacetrack/compare/e5fc088a96ec1557d44931e00500cdcef8349fad...0.9.0>`__ - 2016-01-28
------------------------------------------------------------------------------------------------------------------------------------

First release.
