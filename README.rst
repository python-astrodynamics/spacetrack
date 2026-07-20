spacetrack
-------------

|PyPI Version| |Documentation| |CI Status| |Coverage| |Python Version| |MIT License|

spacetrack is a Python client for `Space-Track <https://www.space-track.org>`__.

Installation
~~~~~~~~~~~~

.. code:: bash

    $ pip install spacetrack

Example
~~~~~~~

.. code:: python

   >>> from spacetrack import SpaceTrackClient
   >>> st = SpaceTrackClient('identity', 'password')

   >>> print(st.gp(norad_cat_id=[25544, 41335], format='tle'))
   1 25544U 98067A   16179.00000000  .00000000  00000-0  00000-0 0  0000
   2 25544  00.0000   0.0000 0000000  00.0000 000.0000 00.00000000  0000
   1 41335U 16011A   16179.00000000  .00000000  00000-0  00000-0 0  0000
   2 41335  00.0000   0.0000 0000000  00.0000 000.0000 00.00000000  0000

   >>> # Operators, to save manual string formatting.
   >>> import spacetrack.operators as op
   >>> from datetime import datetime
   >>> drange = op.inclusive_range(datetime(2016, 6, 26), datetime(2016, 6, 27))

   >>> # Streaming downloads line by line
   >>> lines = st.gp_history(iter_lines=True, creation_date=drange, orderby='TLE_LINE1', format='tle')
   >>> with open('tle.txt', 'w') as fp:
   ...     for line in lines:
   ...         fp.write(line)

   >>> # Streaming downloads in chunk (note file is opened in binary mode)
   >>> content = st.download(iter_content=True, file_id=..., format='stream')
   >>> with open('file.txt', 'wb') as fp:
   ...     for chunk in content:
   ...         fp.write(chunk)

   >>> # Parameter checking, using Space-Track's modeldef API
   >>> st.gp(onrad_cat_id=25544)
   TypeError: 'gp' got an unexpected argument 'onrad_cat_id'

   >>> # Automatic rate limiting
   >>> for satno in my_satnos:
   ...     # Gets limited to <30 requests per minute automatically by blocking
   ...     st.gp(...)

   >>> # Log out and close connections
   >>> st.close()

Authors
~~~~~~~
- Frazer McLean <frazer@frazermclean.co.uk>

Documentation
~~~~~~~~~~~~~

For in-depth information, `visit the
documentation <https://spacetrack.readthedocs.io/en/latest/>`__!

Development
~~~~~~~~~~~

spacetrack uses `semantic versioning <https://semver.org>`__.

.. |CI Status| image:: https://github.com/python-astrodynamics/spacetrack/actions/workflows/ci.yml/badge.svg?branch=main
   :target: https://github.com/python-astrodynamics/spacetrack/actions/workflows/ci.yml
.. |PyPI Version| image:: https://img.shields.io/pypi/v/spacetrack.svg?style=flat-square
   :target: https://pypi.org/project/spacetrack/
.. |Python Version| image:: https://img.shields.io/pypi/pyversions/spacetrack.svg?style=flat-square
   :target: https://pypi.org/project/spacetrack/
.. |MIT License| image:: https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square
   :target: https://raw.githubusercontent.com/python-astrodynamics/spacetrack/main/LICENSE.txt
.. |Coverage| image:: https://codecov.io/gh/python-astrodynamics/spacetrack/branch/main/graph/badge.svg
   :target: https://codecov.io/gh/python-astrodynamics/spacetrack
.. |Documentation| image:: https://readthedocs.org/projects/spacetrack/badge/?version=latest
   :target: https://spacetrack.readthedocs.io/en/latest/
