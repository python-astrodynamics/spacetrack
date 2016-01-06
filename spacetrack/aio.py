# coding: utf-8
from __future__ import absolute_import, division, print_function

import asyncio
import time
from collections.abc import AsyncIterator, Mapping

import aiohttp
from aiohttp.helpers import parse_mimetype

from .base import AuthenticationError, SpaceTrackClient, logger
from .operators import _stringify_predicate_value


class AsyncSpaceTrackClient(SpaceTrackClient):
    """Asynchronous SpaceTrack client class.

    This class should be considered experimental.

    It must be closed by calling
    :meth:`~spacetrack.aio.AsyncSpaceTrackClient.close`. Alternatively,
    instances of this class can be used as a context manager.

    Parameters:
        identity: Space-Track username.
        password: Space-Track password.

    For more information, refer to the `Space-Track documentation`_.

    .. _`Space-Track documentation`: https://www.space-track.org/documentation
        #api-requestClasses
    """
    @staticmethod
    def _create_session():
        return aiohttp.ClientSession()

    async def _ratelimit_callback(self, until):
        duration = int(round(until - time.time()))
        logger.info('Rate limit reached. Sleeping for {:d} seconds.', duration)

        if self.callback is not None:
            await self.callback(until)

    async def authenticate(self):
        if not self._authenticated:
            login_url = self.base_url + 'ajaxauth/login'
            data = {'identity': self.identity, 'password': self.password}
            resp = await self.session.post(login_url, data=data)

            # If login failed, we get a JSON response with {'Login': 'Failed'}
            resp_data = await resp.json()
            if isinstance(resp_data, Mapping):
                if resp_data.get('Login', None) == 'Failed':
                    raise AuthenticationError()

            self._authenticated = True

    async def generic_request(self, class_, iter_lines=False,
                              iter_content=False, **kwargs):
        """Generic Space-Track query coroutine.

        The request class methods use this method internally; the following
        two lines are equivalent:

        .. code-block:: python

            await spacetrack.tle_publish(*args, **kwargs)
            await spacetrack.generic_request('tle_publish', *args, **kwargs)

        Parameters:
            class_: Space-Track request class name
            iter_lines: Yield result line by line
            iter_content: Yield result in 100 KiB chunks.
            **kwargs: These keywords must match the predicate fields on
                Space-Track. You may check valid keywords with the following
                snippet:

                .. code-block:: python

                    spacetrack = AsyncSpaceTrackClient(...)
                    await spacetrack.tle.get_predicates()
                    # or
                    await spacetrack.get_predicates('tle')

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
        if iter_lines and iter_content:
            raise ValueError('iter_lines and iter_content cannot both be True')

        if class_ not in self.request_classes:
            raise ValueError("Unknown request class '{}'".format(class_))

        await self.authenticate()

        controller = self.request_classes[class_]
        url = ('{0}{1}/query/class/{2}'
               .format(self.base_url, controller, class_))

        predicate_fields = await self._get_predicate_fields(class_)
        valid_fields = predicate_fields | {p.name for p in self.rest_predicates}

        for key, value in kwargs.items():
            if key not in valid_fields:
                raise TypeError(
                    "'{class_}' got an unexpected argument '{key}'"
                    .format(class_=class_, key=key))

            value = _stringify_predicate_value(value)

            url += '/{key}/{value}'.format(key=key, value=value)

        logger.info(url)

        async with self._ratelimiter:
            resp = await self.session.get(url)

        # It's possible that Space-Track will return HTTP status 500 with a
        # query rate limit violation. This can happen if a script is cancelled
        # before it has finished sleeping to satisfy the rate limit and it is
        # started again.
        #
        # Let's catch this specific instance and retry once if it happens.
        if resp.status == 500:
            text = await resp.text()

            # Let's only retry if the error page tells us it's a rate limit
            # violation.in
            if 'violated your query rate limit' in text:
                # Mimic the RateLimiter callback behaviour.
                until = time.time() + self._ratelimiter.period
                asyncio.ensure_future(self._ratelimit_callback(until))
                await asyncio.sleep(self._ratelimiter.period)

                # Now retry
                async with self._ratelimiter:
                    resp = await self.session.get(url)

        _raise_for_status(resp)

        decode = (controller != 'fileshare')

        if iter_lines:
            return _AsyncLineIterator(resp, decode_unicode=decode)
        elif iter_content:
            return _AsyncChunkIterator(resp, decode_unicode=decode)
        else:
            # If format is specified, return that format unparsed. Otherwise,
            # parse the default JSON response.
            if 'format' in kwargs:
                # Replace CRLF newlines with LF, Python will handle platform
                # specific newlines if written to file.
                text = await resp.text()
                return text.replace('\r', '')
            else:
                return await resp.json()

    async def _get_predicate_fields(self, class_):
        """Get valid predicate fields which can be passed as keyword arguments."""
        predicates = await self.get_predicates(class_)
        return {p.name for p in predicates}

    async def _download_predicate_data(self, class_):
        """Get raw predicate information for given request class, and cache for
        subsequent calls.
        """
        await self.authenticate()
        controller = self.request_classes[class_]

        url = ('{0}{1}/modeldef/class/{2}'
               .format(self.base_url, controller, class_))

        async with self._ratelimiter:
            resp = await self.session.get(url)
        resp_json = await resp.json()
        return resp_json['data']

    async def get_predicates(self, class_):
        """Get full predicate information for given request class, and cache
        for subsequent calls.
        """
        if class_ not in self._predicates:
            predicates_data = await self._download_predicate_data(class_)
            predicate_objects = self._parse_predicates_data(predicates_data)
            self._predicates[class_] = predicate_objects

        return self._predicates[class_]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close aiohttp session."""
        self.session.close()


class _AsyncContentIteratorMixin(AsyncIterator):
    """Asynchronous iterator mixin for Space-Track aiohttp response."""
    def __init__(self, response, decode_unicode):
        self.response = response
        self.decode_unicode = decode_unicode

    def get_encoding(self):
        ctype = self.response.headers.get('content-type', '').lower()
        mtype, stype, _, params = parse_mimetype(ctype)

        # Fallback to UTF-8
        return params.get('charset', 'UTF-8')


class _AsyncLineIterator(_AsyncContentIteratorMixin):
    """Asynchronous line iterator for Space-Track streamed responses."""
    async def __anext__(self):
        try:
            data = await self.response.content.__anext__()
        except StopAsyncIteration:
            self.response.close()
            raise

        if self.decode_unicode:
            data = data.decode(self.get_encoding())
            # Strip newlines
            data = data.rstrip('\r\n')
        return data


class _AsyncChunkIterator(_AsyncContentIteratorMixin):
    """Asynchronous chunk iterator for Space-Track streamed responses."""
    def __init__(self, *args, chunk_size=100 * 1024, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunk_size = chunk_size

    async def __anext__(self):
        content = self.response.content
        try:
            data = await content.iter_chunked(self.chunk_size).__anext__()
        except StopAsyncIteration:
            self.response.close()
            raise

        if self.decode_unicode:
            data = data.decode(self.get_encoding())
            # Strip newlines
            data = data.strip('\r')
        return data


def _raise_for_status(response):
    """Raise an appropriate error for a given response.

    Arguments:
      response (:py:class:`aiohttp.ClientResponse`): The API response.

    Raises:
      :py:class:`aiohttp.web_exceptions.HTTPException`: The appropriate
        error for the response's status.

    This function was taken from the aslack project and modified. The original
    copyright notice:

    Copyright (c) 2015, Jonathan Sharpe

    Permission to use, copy, modify, and/or distribute this software for any
    purpose with or without fee is hereby granted, provided that the above
    copyright notice and this permission notice appear in all copies.

    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
    WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
    MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
    ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
    WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
    ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
    OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
    """
    if 400 <= response.status < 600:
        for err_name in aiohttp.web_exceptions.__all__:
            err = getattr(aiohttp.web_exceptions, err_name)
            if err.status_code == response.status:
                payload = dict(
                    headers=response.headers,
                    reason=response.reason,
                )
                if issubclass(err, aiohttp.web_exceptions._HTTPMove):
                    raise err(response.headers['Location'], **payload)
                raise err(**payload)
