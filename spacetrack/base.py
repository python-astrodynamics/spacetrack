# coding: utf-8
from __future__ import absolute_import, division, print_function

import re
from collections import Mapping
from functools import partial

import requests
from logbook import Logger
from represent import ReprHelper, ReprHelperMixin

from .operators import _stringify_predicate_value

logger = Logger('spacetrack')


class AuthenticationError(Exception):
    """Space-Track authentication error."""


class Predicate(ReprHelperMixin, object):
    """Hold Space-Track predicate information.

    The current goal of this class is to print the repr for the user.
    """
    def __init__(self, name, type_, nullable=False, values=None):
        self.name = name
        self.type_ = type_
        self.nullable = nullable

        # Values can be set e.g. for enum predicates
        self.values = values

    def _repr_helper_(self, r):
        r.keyword_from_attr('name')
        r.keyword_from_attr('type_')
        r.keyword_from_attr('nullable')
        if self.values is not None:
            r.keyword_from_attr('values')


class SpaceTrackClient(object):
    """SpaceTrack client class.

    Parameters:
        identity: Space-Track username.
        password: Space-Track password.

    For more information, refer to the `Space-Track documentation`_.

    .. _`Space-Track documentation`: https://www.space-track.org/documentation
        #api-requestClasses
    """
    base_url = 'https://www.space-track.org/'

    # This dictionary is a mapping of request classes to request controllers.
    # Each class is accessible as a method on this class.
    request_classes = {
        'tle': 'basicspacedata',
        'tle_latest': 'basicspacedata',
        'tle_publish': 'basicspacedata',
        'omm': 'basicspacedata',
        'boxscore': 'basicspacedata',
        'satcat': 'basicspacedata',
        'launch_site': 'basicspacedata',
        'satcat_change': 'basicspacedata',
        'satcat_debut': 'basicspacedata',
        'decay': 'basicspacedata',
        'tip': 'basicspacedata',
        'announcement': 'basicspacedata',
        'cdm': 'expandedspacedata',
        'organization': 'expandedspacedata',
        'file': 'fileshare',
        'download': 'fileshare',
        'upload': 'fileshare',
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
        self.session = self._create_session()
        self.identity = identity
        self.password = password

        self._authenticated = False
        self._predicates = dict()

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
        """
        if not self._authenticated:
            login_url = self.base_url + 'ajaxauth/login'
            data = {'identity': self.identity, 'password': self.password}
            resp = self.session.post(login_url, data=data)

            resp.raise_for_status()

            # If login failed, we get a JSON response with {'Login': 'Failed'}
            resp_data = resp.json()
            if isinstance(resp_data, Mapping):
                if resp_data.get('Login', None) == 'Failed':
                    raise AuthenticationError()

            self._authenticated = True

    def generic_request(self, class_, iter_lines=False, iter_content=False,
                        **kwargs):
        """Generic Space-Track query.

        The request class methods use this method internally; the following
        two lines are equivalent:

        .. code-block:: python

            spacetrack.tle_publish(*args, **kwargs)
            spacetrack.generic_request('tle_publish', *args, **kwargs)

        Parameters:
            class_: Space-Track request class name
            iter_lines: Yield result line by line
            iter_content: Yield result in 100 KiB chunks.
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

        if class_ not in self.request_classes:
            raise ValueError("Unknown request class '{}'".format(class_))

        self.authenticate()

        controller = self.request_classes[class_]
        url = ('{0}{1}/query/class/{2}'
               .format(self.base_url, controller, class_))

        # Validate keyword argument names by querying valid predicates from
        # Space-Track
        predicate_fields = self._get_predicate_fields(class_)
        valid_fields = predicate_fields | {p.name for p in self.rest_predicates}

        for key, value in kwargs.items():
            if key not in valid_fields:
                raise TypeError(
                    "'{class_}' got an unexpected argument '{key}'"
                    .format(class_=class_, key=key))

            value = _stringify_predicate_value(value)

            url += '/{key}/{value}'.format(key=key, value=value)

        logger.info(url)

        resp = self.session.get(url, stream=iter_lines or iter_content)
        resp.raise_for_status()

        if resp.encoding is None:
            resp.encoding = 'UTF-8'

        # Decode unicode unless controller is fileshare, including conversion of
        # CRLF newlines to LF.
        decode = (controller != 'fileshare')
        if iter_lines:
            return (line for line in resp.iter_lines(decode_unicode=decode))
        elif iter_content:
            return _iter_content_generator(resp, decode_unicode=decode)
        else:
            # If format is specified, return that format unparsed. Otherwise,
            # parse the default JSON response.
            if 'format' in kwargs:
                text = resp.text
                if decode:
                    # Replace CRLF newlines with LF, Python will handle platform
                    # specific newlines if written to file.
                    text = text.replace('\r\n', '\n')
                return text
            else:
                return resp.json()

    def __getattr__(self, attr):
        if attr not in self.request_classes:
            raise AttributeError(
                "'{name}' object has no attribute '{attr}'"
                .format(name=self.__class__.__name__, attr=attr))

        function = partial(self.generic_request, attr)
        function.get_predicates = partial(self.get_predicates, attr)
        return function

    def _get_predicate_fields(self, class_):
        """Get valid predicate fields which can be passed as keyword arguments."""
        predicates = self.get_predicates(class_)
        return {p.name for p in predicates}

    def _download_predicate_data(self, class_):
        """Get raw predicate information for given request class, and cache for
        subsequent calls.
        """
        self.authenticate()
        controller = self.request_classes[class_]

        url = ('{0}{1}/modeldef/class/{2}'
               .format(self.base_url, controller, class_))

        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()['data']

    def get_predicates(self, class_):
        """Get full predicate information for given request class, and cache
        for subsequent calls.
        """
        if class_ not in self._predicates:
            predicates_data = self._download_predicate_data(class_)
            predicate_objects = self._parse_predicates_data(predicates_data)
            self._predicates[class_] = predicate_objects

        return self._predicates[class_]

    def _parse_predicates_data(self, predicates_data):
        type_re = re.compile('(\w+)')
        enum_re = re.compile("""
            enum\(
                '(\w+)'      # First value
                (?:,         # Subsequent values optional
                    '(\w+)'  # Capture string
                )*
            \)
        """, re.VERBOSE)

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

            types = {
                # Strings
                'char': 'str',
                'varchar': 'str',
                'longtext': 'str',
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
            }

            if type_name not in types:
                raise ValueError("Unknown predicate type '{}'."
                                 .format(type_name))

            predicate = Predicate(field_name, types[type_name], nullable)
            if type_name == 'enum':
                enum_match = enum_re.match(full_type)
                if not enum_match:
                    raise ValueError(
                        "Couldn't parse enum type '{}'".format(full_type))

                predicate.values = enum_match.groups()

            predicate_objects.append(predicate)

        return predicate_objects

    def __repr__(self):
        r = ReprHelper(self)
        r.parantheses = ('<', '>')
        r.keyword_from_attr('identity')
        return str(r)


def _iter_content_generator(response, decode_unicode):
    """Generator used to yield 100 KiB chunks for a given response."""
    for chunk in response.iter_content(100 * 1024, decode_unicode=decode_unicode):
        print(decode_unicode, chunk)
        if decode_unicode:
            # Replace CRLF newlines with LF, Python will handle
            # platform specific newlines if written to file.
            chunk = chunk.strip('\r')
        yield chunk
