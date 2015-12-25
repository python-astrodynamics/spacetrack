# coding: utf-8
from __future__ import absolute_import, division, print_function

from collections import Mapping

import aiohttp
from aiohttp.helpers import parse_mimetype

from .base import AuthenticationError, SpaceTrackClient, logger
from .operators import _stringify_predicate_value


class AsyncSpaceTrackClient(SpaceTrackClient):
    """Asynchronous SpaceTrack client class.

    Parameters:
        identity: Space-Track username.
        password: Space-Track password.

    For how to query the API, see https://www.space-track.org/documentation#/api
    """
    @staticmethod
    def _create_session():
        return aiohttp.ClientSession()

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
        await self.authenticate()

        controller = self.request_classes[class_]
        url = ('{0}{1}/query/class/{2}'
               .format(self.base_url, controller, class_))

        predicate_fields = await self.get_predicate_fields(class_)
        valid_fields = predicate_fields | self.rest_predicates

        for key, value in kwargs.items():
            if key not in valid_fields:
                raise TypeError(
                    "'{class_}' got an unexpected argument '{key}'"
                    .format(class_=class_, key=key))

            value = _stringify_predicate_value(value)

            url += '/{key}/{value}'.format(key=key, value=value)

        logger.info(url)

        resp = await self.session.get(url)

        decode = (controller != 'fileshare')

        if iter_lines:
            return AsyncLineIterator(resp, decode_unicode=decode)
        elif iter_content:
            return AsyncChunkIterator(resp, decode_unicode=decode)
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

    async def get_predicate_fields(self, class_):
        """Get valid predicate fields which can be passed as keyword arguments.

        The field names are fetched from Space-Track, and cached in memory.
        """
        if class_ not in self._predicate_fields:
            predicates = await self._get_predicates(class_)
            data = predicates['data']
            fields = {d['Field'].lower() for d in data}
            self._predicate_fields[class_] = fields

        return self._predicate_fields[class_]

    async def _get_predicates(self, class_):
        await self.authenticate()
        controller = self.request_classes[class_]

        url = ('{0}{1}/modeldef/class/{2}'
               .format(self.base_url, controller, class_))

        resp = await self.session.get(url)
        return await resp.json()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.session.close()


class AsyncContentIteratorMixin:
    """Asynchronous iterator mixin for Space-Track aiohttp response."""
    def __init__(self, response, decode_unicode):
        self.response = response
        self.decode_unicode = decode_unicode

    async def __aiter__(self):
        return self

    def get_encoding(self):
        ctype = self.response.headers.get('content-type', '').lower()
        mtype, stype, _, params = parse_mimetype(ctype)

        # Fallback to UTF-8
        return params.get('charset', 'UTF-8')


class AsyncLineIterator(AsyncContentIteratorMixin):
    """Asynchronous line iterator for Space-Track streamed responses."""
    async def __anext__(self):
        data = await self.response.content.__anext__()
        if self.decode_unicode:
            data = data.decode(self.get_encoding())
            # Strip newlines
            data = data.rstrip('\r\n')
        return data


class AsyncChunkIterator(AsyncContentIteratorMixin):
    """Asynchronous chunk iterator for Space-Track streamed responses."""
    def __init__(self, *args, chunk_size=1024, **kwargs):
        super().__init__(*args, **kwargs)
        self.chunk_size = chunk_size

    async def __anext__(self):
        content = self.response.content
        data = await content.iter_chunked(self.chunk_size).__anext__()
        if self.decode_unicode:
            data = data.decode(self.get_encoding())
            # Strip newlines
            data = data.strip('\r')
        return data
