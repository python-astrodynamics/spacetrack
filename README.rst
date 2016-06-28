spacetrack
-------------

|PyPI Version| |Documentation| |Travis| |Coverage| |Python Version| |MIT License|

spacetrack is a python module for `Space-Track <https://www.space-track.org>`__

Installation
~~~~~~~~~~~~

.. code:: bash

    $ pip install spacetrack

Example
~~~~~~~

.. code:: python

   >>> from spacetrack import SpaceTrackClient
   >>> st = SpaceTrackClient('identity', 'password')

   >>> print(st.tle_latest(norad_cat_id=[25544, 41335], ordinal=1, format='tle'))
   1 25544U 98067A   16179.00000000  .00000000  00000-0  00000-0 0  0000
   2 25544  00.0000   0.0000 0000000  00.0000 000.0000 00.00000000  0000
   1 41335U 16011A   16179.00000000  .00000000  00000-0  00000-0 0  0000
   2 41335  00.0000   0.0000 0000000  00.0000 000.0000 00.00000000  0000

   >>> # Operators, to save manual string formatting.
   >>> import spacetrack.operators as op
   >>> drange = op.inclusive_range(dt.datetime(2016, 6, 26),
   ...                             dt.datetime(2016, 6, 27))

   >>> # Streaming downloads line by line
   >>> lines = st.tle(iter_lines=True, publish_epoch=drange, orderby='TLE_LINE1', format='tle')
   >>> with open('tle.txt', 'w') as fp:
   ...     for line in lines:
   ...         fp.write(line)

   # Streaming downloads in chunk (note file is opened in binary mode)
   >>> content = st.download(iter_content=True, file_id=..., format='stream')
   >>> with open('file.txt', 'wb') as fp:
   ...     for chunk in content:
   ...         fp.write(chunk)

   >>> # Parameter checking, using Space-Track's modeldef API
   >>> st.tle_latest(onrad_cat_id=25544)
   TypeError: 'tle_latest' got an unexpected argument 'onrad_cat_id'

   >>> # Automatic rate limiting
   >>> for satno in my_satnos:
   ...     # Gets limited to <20 requests per minute automatically by blocking
   ...     st.tle(...)

Authors
~~~~~~~
- Frazer McLean <frazer@frazermclean.co.uk>

Documentation
~~~~~~~~~~~~~

For in-depth information, `visit the
documentation <http://spacetrack.readthedocs.org/en/latest/>`__!

Development
~~~~~~~~~~~

spacetrack uses `semantic versioning <http://semver.org>`__

.. |Travis| image:: http://img.shields.io/travis/python-astrodynamics/spacetrack/master.svg?style=flat-square&label=travis
   :target: https://travis-ci.org/python-astrodynamics/spacetrack
.. |PyPI Version| image:: http://img.shields.io/pypi/v/spacetrack.svg?style=flat-square
   :target: https://pypi.python.org/pypi/spacetrack/
.. |Python Version| image:: https://img.shields.io/badge/python-2.7%2C%203-brightgreen.svg?style=flat-square
   :target: https://www.python.org/downloads/
.. |MIT License| image:: http://img.shields.io/badge/license-MIT-blue.svg?style=flat-square
   :target: https://raw.githubusercontent.com/python-astrodynamics/spacetrack/master/LICENSE
.. |Coverage| image:: https://img.shields.io/codecov/c/github/python-astrodynamics/spacetrack/master.svg?style=flat-square
   :target: https://codecov.io/github/python-astrodynamics/spacetrack?branch=master
.. |Documentation| image:: https://img.shields.io/badge/docs-latest-brightgreen.svg?style=flat-square
	:target: http://spacetrack.readthedocs.org/en/latest/
