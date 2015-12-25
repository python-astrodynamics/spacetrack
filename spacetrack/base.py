# coding: utf-8
from __future__ import absolute_import, division, print_function

from collections import Mapping
from functools import partial

import requests
from logbook import Logger
from represent import ReprHelper

from .operators import _stringify_predicate_value

logger = Logger('spacetrack')


class AuthenticationError(Exception):
    """Space-Track authentication error."""


class SpaceTrack(object):
    base_url = 'https://www.space-track.org/'

    # Mapping of request classes to request controllers
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

    rest_predicates = {
        'predicates', 'metadata', 'limit', 'orderby', 'distinct', 'format',
        'emptyresult', 'favorites'}

    def __init__(self, identity, password):
        self.session = self._create_session()
        self.identity = identity
        self.password = password

        self._authenticated = False
        self._predicate_fields = dict()

    @staticmethod
    def _create_session():
        return requests.Session()

    def authenticate(self):
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

    def _generic_request(self, class_, iter_lines=False, iter_content=False,
                         **kwargs):
        """Generic Space-Track query.

        Parameters:
            class_: Space-Track request class name
            iter_lines: Yield result line by line
            iter_content: Yield result in 1 KiB chunks.
        """

        if iter_lines and iter_content:
            raise ValueError('iter_lines and iter_content cannot both be True')

        self.authenticate()

        controller = self.request_classes[class_]
        url = ('{0}{1}/query/class/{2}'
               .format(self.base_url, controller, class_))

        predicate_fields = self.get_predicate_fields(class_)
        valid_fields = predicate_fields | self.rest_predicates
        if 'stream' in predicate_fields:
            # I don't expect this to happen, but prevent swallowing a predicate
            # that would otherwise be correctly passes to Space-Track
            raise RuntimeError(
                "Predicate field 'stream' clashes with function keyword.")

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

        decode = (controller != 'fileshare')
        if iter_lines:
            return (line for line in resp.iter_lines(decode_unicode=decode))
        elif iter_content:
            def generator():
                for chunk in resp.iter_content(1024, decode_unicode=decode):
                    if decode:
                        # Replace CRLF newlines with LF, Python will handle
                        # platform specific newlines if written to file.
                        chunk = chunk.strip('\r')
                    yield chunk
            return generator()
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

        function = partial(self._generic_request, attr)
        function.get_predicate_fields = partial(self.get_predicate_fields, attr)
        return function

    def get_predicate_fields(self, class_):
        """Get valid predicate fields which can be passed as keyword arguments.

        The field names are fetched from Space-Track, and cached in memory.
        """
        if class_ not in self._predicate_fields:
            predicates = self._get_predicates(class_)
            data = predicates['data']
            fields = {d['Field'].lower() for d in data}
            self._predicate_fields[class_] = fields

        return self._predicate_fields[class_]

    def _get_predicates(self, class_):
        self.authenticate()
        controller = self.request_classes[class_]

        url = ('{0}{1}/modeldef/class/{2}'
               .format(self.base_url, controller, class_))

        resp = self.session.get(url)
        resp.raise_for_status()
        return resp.json()

    def __repr__(self):
        r = ReprHelper(self)
        r.parantheses = ('<', '>')
        r.keyword_from_attr('identity')
        return str(r)
