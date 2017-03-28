# coding: utf-8
from __future__ import absolute_import, division, print_function

import asyncio
import ssl
import time
from collections.abc import AsyncIterator, Mapping

import aiohttp
import aiohttp.web_exceptions
import requests.certs
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

    .. attribute:: session

        :class:`aiohttp.ClientSession` instance.
    """
    @staticmethod
    def _create_session():
        # Use requests/certifi CA file
        ctx = ssl.create_default_context(cafile=requests.certs.where())
        connector = aiohttp.TCPConnector(ssl_context=ctx)
        return aiohttp.ClientSession(connector=connector)

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

            await _raise_for_status(resp)

            # If login failed, we get a JSON response with {'Login': 'Failed'}
            resp_data = await resp.json()
            if isinstance(resp_data, Mapping):
                if resp_data.get('Login', None) == 'Failed':
                    raise AuthenticationError()

            self._authenticated = True

    async def generic_request(self, class_, iter_lines=False, iter_content=False,
                              controller=None, parse_types=False, **kwargs):
        """Generic Space-Track query coroutine.

        The request class methods use this method internally; the public
        API is as follows:

        .. code-block:: python

            st.tle_publish(*args, **st)
            st.basicspacedata.tle_publish(*args, **st)
            st.file(*args, **st)
            st.fileshare.file(*args, **st)
            st.spephemeris.file(*args, **st)

        They resolve to the following calls respectively:

        .. code-block:: python

            st.generic_request('tle_publish', *args, **st)
            st.generic_request('tle_publish', *args, controller='basicspacedata', **st)
            st.generic_request('file', *args, **st)
            st.generic_request('file', *args, controller='fileshare', **st)
            st.generic_request('file', *args, controller='spephemeris', **st)

        Parameters:
            class_: Space-Track request class name
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

        if 'format' in kwargs and parse_types:
            raise ValueError('parse_types can only be used if format is unset.')

        if controller is None:
            controller = self._find_controller(class_)
        else:
            classes = self.request_controllers.get(controller, None)
            if classes is None:
                raise ValueError(
                    'Unknown request controller {!r}'.format(controller))
            if class_ not in classes:
                raise ValueError(
                    'Unknown request class {!r} for controller {!r}'
                    .format(class_, controller))

        # Decode unicode unless class == download, including conversion of
        # CRLF newlines to LF.
        decode = (class_ != 'download')
        if not decode and iter_lines:
            error = (
                'iter_lines disabled for binary data, since CRLF newlines '
                'split over chunk boundaries would yield extra blank lines. '
                'Use iter_content=True instead.')
            raise ValueError(error)

        await self.authenticate()

        url = ('{0}{1}/query/class/{2}'
               .format(self.base_url, controller, class_))

        offline_check = (class_, controller) in self.offline_predicates
        valid_fields = {p.name for p in self.rest_predicates}
        predicates = None

        if not offline_check:
            predicates = await self.get_predicates(class_)
            predicate_fields = {p.name for p in predicates}
            valid_fields = predicate_fields | {p.name for p in self.rest_predicates}
        else:
            valid_fields |= self.offline_predicates[(class_, controller)]

        for key, value in kwargs.items():
            if key not in valid_fields:
                raise TypeError(
                    "'{class_}' got an unexpected argument '{key}'"
                    .format(class_=class_, key=key))

            value = _stringify_predicate_value(value)

            url += '/{key}/{value}'.format(key=key, value=value)

        logger.debug(url)

        resp = await self._ratelimited_get(url)

        await _raise_for_status(resp)

        if iter_lines:
            return _AsyncLineIterator(resp, decode_unicode=decode)
        elif iter_content:
            return _AsyncChunkIterator(resp, decode_unicode=decode)
        else:
            # If format is specified, return that format unparsed. Otherwise,
            # parse the default JSON response.
            if 'format' in kwargs:
                if decode:
                    # Replace CRLF newlines with LF, Python will handle platform
                    # specific newlines if written to file.
                    data = await resp.text()
                    data = data.replace('\r', '')
                else:
                    data = await resp.read()
                return data
            else:
                data = await resp.json()

                if predicates is None or not parse_types:
                    return data
                else:
                    return self._parse_types(data, predicates)

    async def _ratelimited_get(self, *args, **kwargs):
        async with self._ratelimiter:
            resp = await self.session.get(*args, **kwargs)

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
                    resp = await self.session.get(*args, **kwargs)

        return resp

    async def _download_predicate_data(self, class_, controller):
        """Get raw predicate information for given request class, and cache for
        subsequent calls.
        """
        await self.authenticate()

        url = ('{0}{1}/modeldef/class/{2}'
               .format(self.base_url, controller, class_))

        resp = await self._ratelimited_get(url)

        await _raise_for_status(resp)

        resp_json = await resp.json()
        return resp_json['data']

    async def get_predicates(self, class_, controller=None):
        """Get full predicate information for given request class, and cache
        for subsequent calls.
        """
        if class_ not in self._predicates:
            if controller is None:
                controller = self._find_controller(class_)
            else:
                classes = self.request_controllers.get(controller, None)
                if classes is None:
                    raise ValueError(
                        'Unknown request controller {!r}'.format(controller))
                if class_ not in classes:
                    raise ValueError(
                        'Unknown request class {!r}'.format(class_))

            predicates_data = await self._download_predicate_data(
                class_, controller)
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

    async def __anext__(self):
        raise NotImplementedError


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
            # Replace CRLF newlines with LF, Python will handle
            # platform specific newlines if written to file.
            data = data.replace('\r\n', '\n')
            # Chunk could be ['...\r', '\n...'], strip trailing \r
            data = data.rstrip('\r')
        return data


async def _raise_for_status(response):
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

    try:
        response.raise_for_status()
    except aiohttp.ClientResponseError as exc:
        reason = response.reason

        spacetrack_error_msg = None

        try:
            json = await response.json()
            if isinstance(json, Mapping):
                spacetrack_error_msg = json['error']
        except (ValueError, KeyError, aiohttp.ClientResponseError):
            pass

        if not spacetrack_error_msg:
            spacetrack_error_msg = await response.text()

        if spacetrack_error_msg:
            reason += '\nSpace-Track response:\n' + spacetrack_error_msg

        payload = dict(
            code=response.status,
            message=reason,
            headers=response.headers,
        )

        # history attribute is only aiohttp >= 2.1
        try:
            payload['history'] = exc.history
        except AttributeError:
            pass

        raise aiohttp.ClientResponseError(**payload)
