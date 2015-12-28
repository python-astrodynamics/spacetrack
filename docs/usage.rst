*****
Usage
*****

.. code-block:: python

   import spacetrack.operators as op
   from spacetrack import SpaceTrackClient

   st = SpaceTrackClient(identity='user@example.com', password='password')

Sample Queries
==============

The Space-Track website lists some sample queries, which are shown here using
the Python module.

.. code-block:: python

   output = st.boxscore(format='csv')

.. code-block:: python

   decay_epoch = op.inclusive_range(date(2012, 7, 2), date(2012, 7, 9))
   st.decay(decay_epoch=decay_epoch, orderby=['norad_cat_id', 'precedence'], format='xml')

.. code-block:: python

   st.satcat(launch='>now-7', current='Y', orderby='launch desc', format='html')

.. code-block:: python

   st.satcat(period=op.inclusive_range(1430, 1450), current='Y',
             decay=None, orderby='norad_cat_id', format='html')

.. code-block:: python

   st.satcat(period=op.less_than(128), decay=None, current='Y')

.. code-block:: python

   st.tle_latest(ordinal=1, epoch='>now-30',
                 mean_motion=op.inclusive_range(0.99, 1.01),
                 eccentricity=op.less_than(0.01), format='tle')

.. code-block:: python

   st.tle_latest(ordinal=1, epoch='>now-30', mean_motion=op.greater_than(11.25),
                 format='3le')

.. code-block:: python

   st.tle_latest(favorites='Amateur', ordinal=1, epoch='>now-30', format='3le')

.. code-block:: python

   st.tle_latest(
       ordinal=1,
       norad_cat_id=[
           36000,
           op.inclusive_range(36001, 36004),
           op.like(36005),
           op.startswith(3600),
           36010
       ],
       orderby='norad_cat_id',
       format='html')

.. code-block:: python

   st.tle(norad_cat_id=25544, orderby='epoch desc', limit=22, format='tle')

.. code-block:: python

   st.omm(norad_cat_id=25544, orderby='epoch desc', limit=22, format='xml')

.. code-block:: python

   st.tip(norad_cat_id=[60, 38462, 38351], format='html')

.. code-block:: python

   st.cdm(constellation='iridium', limit=10, orderby='creation_date desc', format='html')

.. code-block:: python

   st.cdm(constellation='iridium', limit=10, orderby='creation_date desc', format='kvn')

.. code-block:: python

   st.cdm(
       constellation='intelsat', tca='>now',
       predicates=['message_for', 'tca', 'miss_distance'],
       orderby='miss_distance', format='html', metadata=True)

.. code-block:: python

   st.cdm(
       constellation='intelsat', tca='>now',
       predicates=['message_for', 'tca', 'miss_distance'],
       orderby='miss_distance', format='kvn')
