import asyncio
import time

import httpx
import sniffio

from .base import (
    BASE_URL,
    Event,
    IterContent,
    IterLines,
    NormalRequest,
    RateLimitWait,
    ReadResponse,
    SpaceTrackClient,
    logger,
)


class AsyncSpaceTrackClient(SpaceTrackClient):
    """Asynchronous SpaceTrack client class.

    It must be closed by calling
    :meth:`~spacetrack.aio.AsyncSpaceTrackClient.close`. Alternatively,
    instances of this class can be used as an async context manager.

    Refer to the :class:`~spacetrack.base.SpaceTrackClient` documentation for
    more information. Note that if passed, the ``httpx_client`` parameter must
    be an ``httpx.AsyncClient``.
    """

    def __init__(
        self,
        identity,
        password,
        base_url=BASE_URL,
        rush_store=None,
        rush_key_prefix="",
        httpx_client=None,
        additional_rate_limit=None,
    ):
        if httpx_client is None:
            httpx_client = httpx.AsyncClient()
        elif not isinstance(httpx_client, httpx.AsyncClient):
            raise TypeError("httpx_client must be an httpx.AsyncClient instance")
        super().__init__(
            identity=identity,
            password=password,
            base_url=base_url,
            rush_store=rush_store,
            rush_key_prefix=rush_key_prefix,
            httpx_client=httpx_client,
            additional_rate_limit=additional_rate_limit,
        )

    async def _handle_event(self, event):
        if isinstance(event, NormalRequest):
            return await self.client.send(
                event.request,
                follow_redirects=event.follow_redirects,
                stream=event.stream,
            )
        elif isinstance(event, ReadResponse):
            return await event.response.aread()
        elif isinstance(event, IterLines):
            return _iter_lines_generator(event.response)
        elif isinstance(event, IterContent):
            return _iter_content_generator(event.response, event.decode)
        elif isinstance(event, RateLimitWait):
            await self._ratelimit_wait(event.duration)
        else:
            raise RuntimeError(f"Unknown event type: {type(event)}")

    async def _run_event_generator(self, g):
        # Start generator by sending in None
        ret = None

        while True:
            try:
                event = g.send(ret)
            except StopIteration as exc:
                if isinstance(exc.value, Event):
                    return await self._handle_event(exc.value)

                return exc.value

            ret = await self._handle_event(event)

    async def authenticate(self):
        """Authenticate with Space-Track.

        Raises:
            spacetrack.base.AuthenticationError: Incorrect login details.

        .. note::

            This method is called automatically when required.
        """
        await self._run_event_generator(self._auth_generator())

    async def generic_request(
        self,
        class_,
        iter_lines=False,
        iter_content=False,
        controller=None,
        parse_types=False,
        **kwargs,
    ):
        r"""Generic Space-Track query.

        The request class methods use this method internally; the public
        API is as follows:

        .. code-block:: python

            st.tle_publish(*args, **kw)
            st.basicspacedata.tle_publish(*args, **kw)
            st.file(*args, **kw)
            st.fileshare.file(*args, **kw)
            st.spephemeris.file(*args, **kw)

        They resolve to the following calls respectively:

        .. code-block:: python

            st.generic_request('tle_publish', *args, **kw)
            st.generic_request('tle_publish', *args, controller='basicspacedata', **kw)
            st.generic_request('file', *args, **kw)
            st.generic_request('file', *args, controller='fileshare', **kw)
            st.generic_request('file', *args, controller='spephemeris', **kw)

        Parameters:
            class\_: Space-Track request class name
            iter_lines: Yield result line by line
            iter_content: Yield result in 100 KiB chunks.
            controller: Optionally specify request controller to use.
            parse_types: Parse string values in response according to type given
                in predicate information, e.g. ``'2017-01-01'`` ->
                ``datetime.date(2017, 1, 1)``.
            **kwargs: These keywords must match the predicate fields on
                Space-Track. You may check valid keywords with the following
                snippet:

                .. code-block:: python

                    spacetrack = SpaceTrackClient(...)
                    spacetrack.tle.get_predicates()
                    # or
                    spacetrack.get_predicates('tle')

                See :func:`~spacetrack.operators._stringify_predicate_value` for
                which Python objects are converted appropriately.

        Yields:
            Lines—stripped of newline characters—if ``iter_lines=True``

        Yields:
            100 KiB chunks if ``iter_content=True``

        Returns:
            Parsed JSON object, unless ``format`` keyword argument is passed.

            .. warning::

                Passing ``format='json'`` will return the JSON **unparsed**. Do
                not set ``format`` if you want the parsed JSON object returned!
        """
        return await self._run_event_generator(
            self._generic_request_generator(
                class_=class_,
                iter_lines=iter_lines,
                iter_content=iter_content,
                controller=controller,
                parse_types=parse_types,
                **kwargs,
            )
        )

    async def _ratelimit_callback(self, until):
        duration = int(round(until - time.monotonic()))
        logger.info("Rate limit reached. Sleeping for {:d} seconds.", duration)

        if self.callback is not None:
            await self.callback(until)

    async def _ratelimit_wait(self, duration):
        async_library = sniffio.current_async_library()
        if async_library == "asyncio":
            await self._ratelimit_wait_asyncio(duration)
        elif async_library == "trio":
            await self._ratelimit_wait_trio(duration)

    async def _ratelimit_wait_asyncio(self, duration):
        until = time.monotonic() + duration
        asyncio.ensure_future(self._ratelimit_callback(until))
        await asyncio.sleep(duration)

    async def _ratelimit_wait_trio(self, duration):
        import trio

        until = time.monotonic() + duration
        async with trio.open_nursery() as nursery:
            nursery.start_soon(self._ratelimit_callback, until)
            nursery.start_soon(trio.sleep, duration)

    async def get_predicates(self, class_, controller=None):
        """Get full predicate information for given request class, and cache
        for subsequent calls.
        """
        return await self._run_event_generator(
            self._get_predicates_generator(class_, controller)
        )

    def __enter__(self):
        raise TypeError("Use async with instead")

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        """Close aiohttp session."""
        await self.client.aclose()


async def _iter_lines_generator(response):
    async for line in response.aiter_lines():
        yield line.rstrip("\n")


async def _iter_content_generator(response, decode_unicode):
    """Generator used to yield 100 KiB chunks for a given response."""
    if decode_unicode:
        it = response.aiter_text()
    else:
        it = response.aiter_bytes()
    async for chunk in it:
        if decode_unicode:
            # Replace CRLF newlines with LF, Python will handle
            # platform specific newlines if written to file.
            chunk = chunk.replace("\r\n", "\n")
            # Chunk could be ['...\r', '\n...'], strip trailing \r
            chunk = chunk.rstrip("\r")
        yield chunk
