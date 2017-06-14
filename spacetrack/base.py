# coding: utf-8
from __future__ import absolute_import, division, print_function

import datetime as dt
import re
import threading
import time
import weakref
from collections import Mapping, OrderedDict
from functools import partial

import requests
from logbook import Logger
from ratelimiter import RateLimiter
from represent import ReprHelper, ReprHelperMixin

from .operators import _stringify_predicate_value

logger = Logger('spacetrack')

type_re = re.compile('(\w+)')
enum_re = re.compile("""
    enum\(
        '(\w+)'      # First value
        (?:,         # Subsequent values optional
            '(\w+)'  # Capture string
        )*
    \)
""", re.VERBOSE)


class AuthenticationError(Exception):
    """Space-Track authentication error."""


class Predicate(ReprHelperMixin, object):
    """Hold Space-Track predicate information.

    The current goal of this class is to print the repr for the user.
    """
    def __init__(self, name, type_, nullable=False, default=None, values=None):
        self.name = name
        self.type_ = type_
        self.nullable = nullable
        self.default = default

        # Values can be set e.g. for enum predicates
        self.values = values

    def _repr_helper_(self, r):
        r.keyword_from_attr('name')
        r.keyword_from_attr('type_')
        r.keyword_from_attr('nullable')
        r.keyword_from_attr('default')
        if self.values is not None:
            r.keyword_from_attr('values')

    def parse(self, value):
        if value is None:
            return value

        if self.type_ == 'float':
            return float(value)
        elif self.type_ == 'int':
            return int(value)
        elif self.type_ == 'datetime':
            return dt.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        elif self.type_ == 'date':
            return dt.datetime.strptime(value, '%Y-%m-%d').date()
        else:
            return value


class SpaceTrackClient(object):
    """SpaceTrack client class.

    Parameters:
        identity: Space-Track username.
        password: Space-Track password.

    For more information, refer to the `Space-Track documentation`_.

    .. _`Space-Track documentation`: https://www.space-track.org/documentation
        #api-requestClasses

    .. data:: request_controllers

        Ordered dictionary of request controllers and their request classes in
        the following order.

        - `basicspacedata`
        - `expandedspacedata`
        - `fileshare`
        - `spephemeris`

        For example, if the ``spacetrack.file`` method is used without
        specifying which controller, the client will choose the `fileshare`
        controller (which comes before `spephemeris`).

        .. note::

            If new request classes and/or controllers are added to the
            Space-Track API but not yet to this library, you can safely
            subclass :class:`SpaceTrackClient` with a copy of this ordered
            dictionary to add them.

            That said, please open an issue on `GitHub`_ for me to add them to
            the library.

            .. _`GitHub`: https://github.com/python-astrodynamics/spacetrack
    """
    base_url = 'https://www.space-track.org/'

    # "request class" methods will be looked up by request controller in this
    # order
    request_controllers = OrderedDict.fromkeys([
        'basicspacedata',
        'expandedspacedata',
        'fileshare',
        'spephemeris',
    ])

    request_controllers['basicspacedata'] = {
        'tle',
        'tle_latest',
        'tle_publish',
        'omm',
        'boxscore',
        'satcat',
        'launch_site',
        'satcat_change',
        'satcat_debut',
        'decay',
        'tip',
        'announcement',
    }

    request_controllers['expandedspacedata'] = {
        'cdm',
        'organization',
        'maneuver',
        'maneuver_history',
    }

    request_controllers['fileshare'] = {
        'file',
        'download',
        'upload',
        'delete',
    }

    request_controllers['spephemeris'] = {
        'download',
        'file',
        'file_history',
    }

    # List of (class, controller) tuples for
    # requests which do not return a modeldef
    offline_predicates = {
        ('upload', 'fileshare'): {'folder_id', 'file'},
    }

    # These predicates are available for every request class.
    rest_predicates = {
        Predicate('predicates', 'str'),
        Predicate('metadata', 'enum', values=('true', 'false')),
        Predicate('limit', 'str'),
        Predicate('orderby', 'str'),
        Predicate('distinct', 'enum', values=('true', 'false')),
        Predicate(
            'format', 'enum',
            values=('json', 'xml', 'html', 'csv', 'tle', '3le', 'kvn', 'stream')),
        Predicate('emptyresult', 'enum', values=('show',)),
        Predicate('favorites', 'str'),
    }

    def __init__(self, identity, password):
        #: :class:`requests.Session` instance. It can be mutated to configure
        #: e.g. proxies.
        self.session = self._create_session()
        self.identity = identity
        self.password = password

        # If set, this will be called when we sleep for the rate limit.
        self.callback = None

        self._authenticated = False
        self._predicates = dict()
        self._controller_proxies = dict()

        # "Space-track throttles API use in order to maintain consistent
        # performance for all users. To avoid error messages, please limit
        # your query frequency to less than 20 requests per minute."
        self._ratelimiter = RateLimiter(
            max_calls=19, period=60, callback=self._ratelimit_callback)

    def _ratelimit_callback(self, until):
        duration = int(round(until - time.time()))
        logger.info('Rate limit reached. Sleeping for {:d} seconds.', duration)

        if self.callback is not None:
            self.callback(until)

    @staticmethod
    def _create_session():
        """Create session for accessing the web.

        This method is overridden in
        :class:`spacetrac.aio.AsyncSpaceTrackClient` to use :mod:`aiohttp`
        instead of :mod:`requests`.
        """
        return requests.Session()

    def authenticate(self):
        """Authenticate with Space-Track.

        Raises:
            spacetrack.base.AuthenticationError: Incorrect login details.

        .. note::

            This method is called automatically when required.
        """
        if not self._authenticated:
            login_url = self.base_url + 'ajaxauth/login'
            data = {'identity': self.identity, 'password': self.password}
            resp = self.session.post(login_url, data=data)

            _raise_for_status(resp)

            # If login failed, we get a JSON response with {'Login': 'Failed'}
            resp_data = resp.json()
            if isinstance(resp_data, Mapping):
                if resp_data.get('Login', None) == 'Failed':
                    raise AuthenticationError()

            self._authenticated = True

    def generic_request(self, class_, iter_lines=False, iter_content=False,
                        controller=None, parse_types=False, **kwargs):
        """Generic Space-Track query.

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

        self.authenticate()

        url = ('{0}{1}/query/class/{2}'
               .format(self.base_url, controller, class_))

        offline_check = (class_, controller) in self.offline_predicates
        valid_fields = {p.name for p in self.rest_predicates}
        predicates = None

        if not offline_check:
            # Validate keyword argument names by querying valid predicates from
            # Space-Track
            predicates = self.get_predicates(class_, controller)
            predicate_fields = {p.name for p in predicates}
            valid_fields |= predicate_fields
        else:
            valid_fields |= self.offline_predicates[(class_, controller)]

        for key, value in kwargs.items():
            if key not in valid_fields:
                raise TypeError(
                    "'{class_}' got an unexpected argument '{key}'"
                    .format(class_=class_, key=key))

            if class_ == 'upload' and key == 'file':
                continue

            value = _stringify_predicate_value(value)

            url += '/{key}/{value}'.format(key=key, value=value)

        logger.debug(url)

        if class_ == 'upload':
            if 'file' not in kwargs:
                raise TypeError("missing keyword argument: 'file'")

            resp = self.session.post(url, files={'file': kwargs['file']})
        else:
            resp = self._ratelimited_get(url, stream=iter_lines or iter_content)

        _raise_for_status(resp)

        if resp.encoding is None:
            resp.encoding = 'UTF-8'

        if iter_lines:
            return _iter_lines_generator(resp, decode_unicode=decode)
        elif iter_content:
            return _iter_content_generator(resp, decode_unicode=decode)
        else:
            # If format is specified, return that format unparsed. Otherwise,
            # parse the default JSON response.
            if 'format' in kwargs:
                if decode:
                    data = resp.text
                    # Replace CRLF newlines with LF, Python will handle platform
                    # specific newlines if written to file.
                    data = data.replace('\r\n', '\n')
                else:
                    data = resp.content
                return data
            else:
                data = resp.json()

                if predicates is None or not parse_types:
                    return data
                else:
                    return self._parse_types(data, predicates)

    @staticmethod
    def _parse_types(data, predicates):
        predicate_map = {p.name: p for p in predicates}

        for obj in data:
            for key, value in obj.items():
                if key.lower() in predicate_map:
                    obj[key] = predicate_map[key.lower()].parse(value)

        return data

    def _ratelimited_get(self, *args, **kwargs):
        """Perform get request, handling rate limiting."""
        with self._ratelimiter:
            resp = self.session.get(*args, **kwargs)

        # It's possible that Space-Track will return HTTP status 500 with a
        # query rate limit violation. This can happen if a script is cancelled
        # before it has finished sleeping to satisfy the rate limit and it is
        # started again.
        #
        # Let's catch this specific instance and retry once if it happens.
        if resp.status_code == 500:
            # Let's only retry if the error page tells us it's a rate limit
            # violation.
            if 'violated your query rate limit' in resp.text:
                # Mimic the RateLimiter callback behaviour.
                until = time.time() + self._ratelimiter.period
                t = threading.Thread(target=self._ratelimit_callback, args=(until,))
                t.daemon = True
                t.start()
                time.sleep(self._ratelimiter.period)

                # Now retry
                with self._ratelimiter:
                    resp = self.session.get(*args, **kwargs)

        return resp

    def __getattr__(self, attr):
        if attr in self.request_controllers:
            controller_proxy = self._controller_proxies.get(attr)
            if controller_proxy is None:
                controller_proxy = _ControllerProxy(self, attr)
                self._controller_proxies[attr] = controller_proxy
            return controller_proxy

        try:
            controller = self._find_controller(attr)
        except ValueError:
            raise AttributeError(
                "'{name}' object has no attribute '{attr}'"
                .format(name=self.__class__.__name__, attr=attr))

        # generic_request can resolve the controller itself, but we
        # pass it because we have to check if the class_ is owned
        # by a controller here anyway.
        function = partial(
            self.generic_request, class_=attr, controller=controller)
        function.get_predicates = partial(
            self.get_predicates, class_=attr, controller=controller)
        return function

    def __dir__(self):
        """Include request controllers and request classes."""
        attrs = list(self.__dict__)
        request_classes = {
            class_ for classes in self.request_controllers.values()
            for class_ in classes}

        attrs += list(request_classes)
        attrs += list(self.request_controllers)

        return sorted(attrs)

    def _find_controller(self, class_):
        """Find first controller that matches given request class.

        Order is specified by the keys of
        ``SpaceTrackClient.request_controllers``
        (:class:`~collections.OrderedDict`)
        """
        for controller, classes in self.request_controllers.items():
            if class_ in classes:
                return controller
        else:
            raise ValueError('Unknown request class {!r}'.format(class_))

    def _download_predicate_data(self, class_, controller):
        """Get raw predicate information for given request class, and cache for
        subsequent calls.
        """
        self.authenticate()

        url = ('{0}{1}/modeldef/class/{2}'
               .format(self.base_url, controller, class_))

        logger.debug(url)

        resp = self._ratelimited_get(url)

        _raise_for_status(resp)

        return resp.json()['data']

    def get_predicates(self, class_, controller=None):
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

            predicates_data = self._download_predicate_data(class_, controller)
            predicate_objects = self._parse_predicates_data(predicates_data)
            self._predicates[class_] = predicate_objects

        return self._predicates[class_]

    def _parse_predicates_data(self, predicates_data):
        predicate_objects = []
        for field in predicates_data:
            full_type = field['Type']
            type_match = type_re.match(full_type)
            if not type_match:
                raise ValueError(
                    "Couldn't parse field type '{}'".format(full_type))

            type_name = type_match.group(1)
            field_name = field['Field'].lower()
            nullable = (field['Null'] == 'YES')
            default = field['Default']

            types = {
                # Strings
                'char': 'str',
                'varchar': 'str',
                'longtext': 'str',
                # varbinary only used for 'file' request class, for the
                # 'file_link' predicate.
                'varbinary': 'str',
                # Integers
                'bigint': 'int',
                'int': 'int',
                'tinyint': 'int',
                'smallint': 'int',
                'mediumint': 'int',
                # Floats
                'decimal': 'float',
                'float': 'float',
                'double': 'float',
                # Date/Times
                'date': 'date',
                'timestamp': 'datetime',
                'datetime': 'datetime',
                # Enum
                'enum': 'enum',
                # Bytes
                'longblob': 'bytes',
            }

            if type_name not in types:
                raise ValueError("Unknown predicate type '{}'."
                                 .format(type_name))

            predicate = Predicate(
                name=field_name,
                type_=types[type_name],
                nullable=nullable,
                default=default)

            if type_name == 'enum':
                enum_match = enum_re.match(full_type)
                if not enum_match:
                    raise ValueError(
                        "Couldn't parse enum type '{}'".format(full_type))

                # match.groups() doesn't work for repeating groups, use findall
                predicate.values = tuple(re.findall(r"'(\w+)'", full_type))

            predicate_objects.append(predicate)

        return predicate_objects

    def __repr__(self):
        r = ReprHelper(self)
        r.parantheses = ('<', '>')
        r.keyword_from_attr('identity')
        return str(r)


class _ControllerProxy(object):
    """Proxies request class methods with a preset request controller."""
    def __init__(self, client, controller):
        # The client will cache _ControllerProxy instances, so only store
        # a weak reference to it.
        self.client = weakref.proxy(client)
        self.controller = controller

    def __getattr__(self, attr):
        if attr not in self.client.request_controllers[self.controller]:
            raise AttributeError(
                "'{self!r}' object has no attribute '{attr}'"
                .format(self=self, attr=attr))

        function = partial(
            self.client.generic_request, class_=attr,
            controller=self.controller)
        function.get_predicates = partial(
            self.client.get_predicates, class_=attr,
            controller=self.controller)

        return function

    def __repr__(self):
        r = ReprHelper(self)
        r.parantheses = ('<', '>')
        r.keyword_from_attr('controller')
        return str(r)

    def get_predicates(self, class_):
        """Proxy ``get_predicates`` to client with stored request
        controller.
        """
        return self.client.get_predicates(
            class_=class_, controller=self.controller)


def _iter_content_generator(response, decode_unicode):
    """Generator used to yield 100 KiB chunks for a given response."""
    for chunk in response.iter_content(100 * 1024, decode_unicode=decode_unicode):
        if decode_unicode:
            # Replace CRLF newlines with LF, Python will handle
            # platform specific newlines if written to file.
            chunk = chunk.replace('\r\n', '\n')
            # Chunk could be ['...\r', '\n...'], stril trailing \r
            chunk = chunk.rstrip('\r')
        yield chunk


def _iter_lines_generator(response, decode_unicode):
    """Iterates over the response data, one line at a time.  When
    stream=True is set on the request, this avoids reading the
    content at once into memory for large responses.

    The function is taken from :meth:`requests.models.Response.iter_lines`, but
    modified to use our :func:`~spacetrack.base._iter_content_generator`. This
    is because Space-Track uses CRLF newlines, so :meth:`str.splitlines` can
    cause us to yield blank lines if one chunk ends with CR and the next one
    starts with LF.

    .. note:: This method is not reentrant safe.
    """
    pending = None

    for chunk in _iter_content_generator(response, decode_unicode=decode_unicode):

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


def _raise_for_status(response):
    """Raises stored :class:`HTTPError`, if one occurred.

    This is the :meth:`requests.models.Response.raise_for_status` method,
    modified to add the response from Space-Track, if given.
    """

    http_error_msg = ''

    if 400 <= response.status_code < 500:
        http_error_msg = '%s Client Error: %s for url: %s' % (
            response.status_code, response.reason, response.url)

    elif 500 <= response.status_code < 600:
        http_error_msg = '%s Server Error: %s for url: %s' % (
            response.status_code, response.reason, response.url)

    if http_error_msg:
        spacetrack_error_msg = None

        try:
            json = response.json()
            if isinstance(json, Mapping):
                spacetrack_error_msg = json['error']
        except (ValueError, KeyError):
            pass

        if not spacetrack_error_msg:
            spacetrack_error_msg = response.text

        if spacetrack_error_msg:
            http_error_msg += '\nSpace-Track response:\n' + spacetrack_error_msg

        raise requests.HTTPError(http_error_msg, response=response)
