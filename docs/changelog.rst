Change Log
==========

`Unreleased <https://github.com/python-astrodynamics/spacetrack/compare/0.9.0...HEAD>`__
----------------------------------------------------------------------------------------

N/A

`0.10.0 <ttps://github.com/python-astrodynamics/spacetrack/compare/0.9.0...0.10.0>`__ - 2016-02-04
--------------------------------------------------------------------------------------------------

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

`0.9.0 <https://github.com/python-astrodynamics/spacetrack/compare/e5fc088a96ec1557d44931e00500cdcef8349fad...0.9.0>`__ - 2016-01-28
------------------------------------------------------------------------------------------------------------------------------------

First release.
