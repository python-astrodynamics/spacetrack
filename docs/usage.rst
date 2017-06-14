*****
Usage
*****

.. code-block:: python

   import spacetrack.operators as op
   from spacetrack import SpaceTrackClient

   st = SpaceTrackClient(identity='user@example.com', password='password')

Request classes are presented as methods on the
:class:`~spacetrack.base.SpaceTrackClient` object. For example,
``st.tle_publish()``. Each request class is part of a request controller.
Since most request classes are only part of one request controller,
``spacetrack`` looks up the controller for you. It can be specified explicitly
in several ways. All the following are equivalent:

.. code-block:: python

    st.tle_publish()
    st.tle_publish(controller='basicspacedata')
    st.basicspacedata.tle_publish()
    st.generic_request('tle_publish')
    st.generic_request('tle_publish', controller='basicspacedata')

Request predicates are passed as keyword arguments. Valid
arguments can be checked using the
:meth:`~spacetrack.base.SpaceTrackClient.get_predicates` method. The following
are equivalent:

.. code-block:: python

    st.tle_publish.get_predicates()
    st.tle_publish.get_predicates(controller='basicspacedata')
    st.basicspacedata.tle_publish.get_predicates()
    st.basicspacedata.get_predicates('tle_publish')
    st.get_predicates('tle_publish')
    st.get_predicates('tle_publish', controller='basicspacedata')

Returned object:

.. code-block:: python

    [Predicate(name='publish_epoch', type_='datetime', nullable=False),
     Predicate(name='tle_line1', type_='str', nullable=False),
     Predicate(name='tle_line2', type_='str', nullable=False)]

Internally, the client uses this mechanism to verify the keyword arguments.
Types are not currently checked.

Streaming Downloads
===================

It is possible to stream responses by passing ``iter_content=True`` (100 KiB
chunks) or ``iter_lines=True`` to the request class methods.

Example
-------

The same example is shown below synchronously and asynchronously.

.. code-block:: python

    import spacetrack.operators as op
    from spacetrack import SpaceTrackClient

    st = SpaceTrackClient(identity='user@example.com', password='password')

    data = st.tle_latest(iter_lines=True, ordinal=1, epoch='>now-30',
                         mean_motion=op.inclusive_range(0.99, 1.01),
                         eccentricity=op.less_than(0.01), format='tle')

    with open('tle_latest.txt', 'w') as fp:
        for line in data:
            fp.write(line + '\n')

.. code-block:: python

    import asyncio

    import spacetrack.operators as op
    from spacetrack.aio import AsyncSpaceTrackClient


    async def download_latest_tles():
        st = AsyncSpaceTrackClient(identity='user@example.com',
                                   password='password')

        with st:
            data = await st.tle_latest(
                iter_lines=True, ordinal=1, epoch='>now-30',
                mean_motion=op.inclusive_range(0.99, 1.01),
                eccentricity=op.less_than(0.01), format='tle')

            with open('tle_latest.txt', 'w') as fp:
                async for line in data:
                    fp.write(line + '\n')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_latest_tles())


File Uploads
============

To use the `upload` request class, pass a `file` keyword argument with the
opened file:

.. code-block:: python

    from spacetrack import SpaceTrackClient

    st = SpaceTrackClient(identity='user@example.com', password='password')

    with open('somefile.txt', 'rb') as fp:
        st.upload(file=fp)


Rate Limiter
============

    "Space-track throttles API use in order to maintain consistent
    performance for all users. To avoid error messages, please limit your
    query frequency to less than 20 requests per minute."

The client will ensure that no more than 19 HTTP requests are sent per minute
by sleeping if the rate exceeds this. This will be logged to the spacetrack
module's logger. You can register a callback with the
:class:`~spacetrack.base.SpaceTrackClient` or
:class:`~spacetrack.aio.AsyncSpaceTrackClient` classes. It will be passed the
time that the module is sleeping until, in seconds since the epoch (as with
:func:`time.time`).

.. code-block:: python

    import time

    from spacetrack import SpaceTrackClient

    def mycallback(until):
        duration = int(round(until - time.time()))
        print('Sleeping for {:d} seconds.'.format(duration))

    st = SpaceTrackClient(identity='user@example.com', password='password')
    st.callback = mycallback

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
