*****
Usage
*****

.. code-block:: python

    import spacetrack.operators as op
    from spacetrack import SpaceTrackClient

    with SpaceTrackClient(identity="user@example.com", password="password") as st:
        ...

Request classes are presented as methods on the
:class:`~spacetrack.base.SpaceTrackClient` object. For example,
``st.tle_publish()``. Each request class is part of a request controller.
Since most request classes are only part of one request controller,
``spacetrack`` looks up the controller for you. It can be specified explicitly
in several ways. All the following are equivalent:

.. code-block:: python

    st.gp_history()
    st.gp_history(controller="basicspacedata")
    st.basicspacedata.gp_history()
    st.generic_request("gp_history")
    st.generic_request("gp_history", controller="basicspacedata")

Request predicates are passed as keyword arguments. Valid
arguments can be checked using the
:meth:`~spacetrack.base.SpaceTrackClient.get_predicates` method. The following
are equivalent:

.. code-block:: python

    st.gp_history.get_predicates()
    st.gp_history.get_predicates(controller="basicspacedata")
    st.basicspacedata.gp_history.get_predicates()
    st.basicspacedata.get_predicates("gp_history")
    st.get_predicates("gp_history")
    st.get_predicates("gp_history", controller="basicspacedata")

Returned object:

.. code-block:: python

    [
        Predicate(name='creation_date', type_='datetime', nullable=True, default=None),
        Predicate(name='object_name', type_='str', nullable=True, default=None),
        Predicate(name='eccentricity', type_='float', nullable=True, default=None),
        ... # and many more
    ]

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

    with SpaceTrackClient(identity="user@example.com", password="password") as st:
        data = st.gp(
            iter_lines=True,
            epoch=">now-30",
            mean_motion=op.inclusive_range(0.99, 1.01),
            eccentricity=op.less_than(0.01),
            format="tle",
        )

        with open("tle_latest.txt", "w") as fp:
            for line in data:
                fp.write(line + "\n")

.. code-block:: python

    import asyncio

    import spacetrack.operators as op
    from spacetrack.aio import AsyncSpaceTrackClient


    async def download_latest_tles():
        async with AsyncSpaceTrackClient(
            identity="user@example.com", password="password"
        ) as st:
            data = await st.gp(
                iter_lines=True,
                epoch=">now-30",
                mean_motion=op.inclusive_range(0.99, 1.01),
                eccentricity=op.less_than(0.01),
                format="tle",
            )

            with open("tle_latest.txt", "w") as fp:
                async for line in data:
                    fp.write(line + "\n")


    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_latest_tles())


File Uploads
============

To use the `upload` request class, pass a `file` keyword argument with the
opened file:

.. code-block:: python

    from spacetrack import SpaceTrackClient

    with SpaceTrackClient(identity="user@example.com", password="password") as st:
        with open("somefile.txt", "rb") as fp:
            st.upload(file=fp)

.. _rate-limiting:

Rate Limiting
=============

As quoted in the `Space-Track API Use Guidelines <st-api>`_:

    "Space-track throttles API use in order to maintain consistent
    performance for all users. To avoid error messages, please limit your
    query frequency."

    **Limit API queries to less than 30 requests per 1 minute(s) / 300 requests
    per 1 hour(s)**

.. _`st-api`: https://www.space-track.org/documentation#/api

.. important::

    While this library will manage the above rate limiting for you, it cannot
    help you with the other limits outlined in the `API Use Guidelines <st-api>`_
    such as how often you download certain data.

    Also consider that the above rate limiting is handled per process and cannot
    determine how often you start new processes or scripts using your account.
    The :class:`SpaceTrackClient.rush_store <spacetrack.base.SpaceTrackClient>`
    argument can be used to use a distributed cache for this purpose.

The client will ensure that no more requests than this are made by sleeping if
the rate exceeds this. This will be logged to the spacetrack module's logger.
You can register a callback with the :class:`~spacetrack.base.SpaceTrackClient`
or :class:`~spacetrack.aio.AsyncSpaceTrackClient` classes. It will be passed a
value to be compared against :func:`time.monotonic` to get the remaining time:

.. code-block:: python

    import time

    from spacetrack import SpaceTrackClient


    def mycallback(until):
        duration = int(round(until - time.monotonic()))
        print("Sleeping for {:d} seconds.".format(duration))


    with SpaceTrackClient(identity="user@example.com", password="password") as st:
        st.callback = mycallback

Sample Queries
==============

The Space-Track website lists some sample queries, which are shown here using
the Python module.

.. code-block:: python

   output = st.boxscore(format="csv")

.. code-block:: python

   decay_epoch = op.inclusive_range(date(2012, 7, 2), date(2012, 7, 9))
   st.decay(decay_epoch=decay_epoch, orderby=["norad_cat_id", "precedence"], format="xml")

.. code-block:: python

   st.satcat(launch=">now-7", current="Y", orderby="launch desc", format="html")

.. code-block:: python

   st.satcat(
       period=op.inclusive_range(1430, 1450),
       current="Y",
       decay=None,
       orderby="norad_cat_id",
       format="html",
   )

.. code-block:: python

   st.satcat(period=op.less_than(128), decay=None, current="Y")

.. code-block:: python

    st.gp(
       epoch=">now-30",
       mean_motion=op.inclusive_range(0.99, 1.01),
       eccentricity=op.less_than(0.01),
       format="tle",
    )

.. code-block:: python

   st.gp(
       epoch=">now-30", mean_motion=op.greater_than(11.25), format="3le"
   )

.. code-block:: python

   st.gp(
       norad_cat_id=[
           36000,
           op.inclusive_range(36001, 36004),
           op.like(36005),
           op.startswith(3600),
           36010,
       ],
       orderby="norad_cat_id",
       format="html",
   )

.. code-block:: python

   st.gp_history(norad_cat_id=25544, orderby="epoch desc", limit=22, format="tle")

.. code-block:: python

   st.gp_history(norad_cat_id=25544, orderby="epoch desc", limit=22, format="xml")

.. code-block:: python

   st.tip(norad_cat_id=[60, 38462, 38351], format="html")

.. code-block:: python

   st.cdm(constellation="iridium", limit=10, orderby="creation_date desc", format="html")

.. code-block:: python

   st.cdm(constellation="iridium", limit=10, orderby="creation_date desc", format="kvn")

.. code-block:: python

   st.cdm(
       constellation="intelsat",
       tca=">now",
       predicates=["message_for", "tca", "miss_distance"],
       orderby="miss_distance",
       format="html",
       metadata=True,
   )

.. code-block:: python

   st.cdm(
       constellation="intelsat",
       tca=">now",
       predicates=["message_for", "tca", "miss_distance"],
       orderby="miss_distance",
       format="kvn",
   )
