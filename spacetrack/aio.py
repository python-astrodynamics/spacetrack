import asyncio
import ssl
import time
from collections.abc import Mapping

import aiohttp
import aiohttp.web_exceptions
import requests.certs
from aiohttp.helpers import parse_mimetype

from .base import RATELIMIT_KEY, AuthenticationError, SpaceTrackClient, logger
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
        base_url: May be overridden to use e.g. https://testing.space-track.org/

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
        connector = aiohttp.TCPConnector(ssl=ctx)
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
                    f'Unknown request controller {controller!r}')
            if class_ not in classes:
                raise ValueError(
                    f'Unknown request class {class_!r} for controller {controller!r}')

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

        url = f'{self.base_url}{controller}/query/class/{class_}'

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
                    f"'{class_}' got an unexpected argument '{key}'")

            value = _stringify_predicate_value(value)

            url += f'/{key}/{value}'

        logger.debug(url)

        resp = await self._ratelimited_get(url)

        await _raise_for_status(resp)

        if iter_lines:
            return _iter_lines_generator(resp, decode_unicode=decode)
        elif iter_content:
            return _iter_content_generator(resp, decode_unicode=decode)
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
        minute_limit = self._per_minute_throttle.check(RATELIMIT_KEY, 1)
        hour_limit = self._per_hour_throttle.check(RATELIMIT_KEY, 1)

        sleep_time = 0

        if minute_limit.limited:
            sleep_time = minute_limit.retry_after.total_seconds()

        if hour_limit.limited:
            sleep_time = max(sleep_time, hour_limit.retry_after.total_seconds())

        if sleep_time > 0:
            await self._ratelimit_wait(sleep_time)

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
                # It seems that only the per-minute rate limit causes an HTTP
                # 500 error. Breaking the per-hour limit seems to result in an
                # email from Space-Track instead.
                await self._ratelimit_wait(60)
                resp = await self.session.get(*args, **kwargs)

        return resp

    async def _ratelimit_wait(self, duration):
        until = time.monotonic() + duration
        asyncio.ensure_future(self._ratelimit_callback(until))
        await asyncio.sleep(duration)

    async def _download_predicate_data(self, class_, controller):
        """Get raw predicate information for given request class, and cache for
        subsequent calls.
        """
        await self.authenticate()

        url = f'{self.base_url}{controller}/modeldef/class/{class_}'

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
                        f'Unknown request controller {controller!r}')
                if class_ not in classes:
                    raise ValueError(
                        f'Unknown request class {class_!r}')

            predicates_data = await self._download_predicate_data(
                class_, controller)
            predicate_objects = self._parse_predicates_data(predicates_data)
            self._predicates[class_] = predicate_objects

        return self._predicates[class_]

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
        await self.session.close()


def get_encoding(response):
    ctype = response.headers.get('content-type', '').lower()
    mimetype = parse_mimetype(ctype)

    # Fallback to UTF-8
    return mimetype.parameters.get('charset', 'UTF-8')


async def _iter_content_generator(response, decode_unicode):
    encoding = None

    if decode_unicode:
        ctype = response.headers.get('content-type', '').lower()
        mimetype = parse_mimetype(ctype)

        # Fallback to UTF-8
        encoding = mimetype.parameters.get('charset', 'UTF-8')

    async for chunk in response.content.iter_chunked(100 * 1024):
        if decode_unicode:
            chunk = chunk.decode(encoding)
            # Replace CRLF newlines with LF, Python will handle
            # platform specific newlines if written to file.
            chunk = chunk.replace('\r\n', '\n')
            # Chunk could be ['...\r', '\n...'], strip trailing \r
            chunk = chunk.rstrip('\r')
        yield chunk


async def _iter_lines_generator(response, decode_unicode):
    pending = None
    async for chunk in _iter_content_generator(response, decode_unicode):
        if pending is not None:
            chunk = pending + chunk

        lines = chunk.splitlines()

        if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
            pending = lines.pop()
        else:
            pending = None

        for line in lines:
            yield line

    if pending is not None:
        yield pending


async def _raise_for_status(response):
    """Raise an appropriate error for a given response.

    Arguments:
      response (:py:class:`aiohttp.ClientResponse`): The API response.

    Raises:
      :py:class:`aiohttp.ClientResponseError`: The appropriate
        error for the response's status.
    """

    if 400 <= response.status:
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

        raise aiohttp.ClientResponseError(
            response.request_info,
            response.history,
            status=response.status,
            message=reason,
            headers=response.headers)
