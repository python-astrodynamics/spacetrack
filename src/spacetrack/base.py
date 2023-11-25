import re
import sys
import threading
import time
import warnings
import weakref
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime
from functools import partial
from urllib.parse import quote

import attr
import httpx
from logbook import Logger
from represent import ReprHelper, ReprHelperMixin
from rush.limiters.periodic import PeriodicLimiter
from rush.quota import Quota
from rush.stores.dictionary import DictionaryStore as RushDictionaryStore
from rush.throttle import Throttle

from .operators import _stringify_predicate_value

if sys.version_info >= (3, 11):
    isoparse = datetime.fromisoformat
else:
    from dateutil.parser import isoparse

logger = Logger("spacetrack")

type_re = re.compile(r"(\w+)")
enum_re = re.compile(
    r"""
    enum\(
        '(\w+)'      # First value
        (?:,         # Subsequent values optional
            '(\w+)'  # Capture string
        )*
    \)
""",
    re.VERBOSE,
)

BASE_URL = "https://www.space-track.org/"


class AuthenticationError(Exception):
    """Space-Track authentication error."""


class UnknownPredicateTypeWarning(RuntimeWarning):
    """Used to warn when a predicate type is unknown."""


class Event:
    pass


@attr.s(slots=True)
class NormalRequest(Event):
    request = attr.ib()
    stream = attr.ib(default=False)
    follow_redirects = attr.ib(default=False)


@attr.s(slots=True)
class ReadResponse(Event):
    response = attr.ib()


@attr.s(slots=True)
class IterLines(Event):
    response = attr.ib()


@attr.s(slots=True)
class IterContent(Event):
    response = attr.ib()
    decode = attr.ib()


@attr.s(slots=True)
class RateLimitWait(Event):
    duration = attr.ib()


class Predicate(ReprHelperMixin):
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
        r.keyword_from_attr("name")
        r.keyword_from_attr("type_")
        r.keyword_from_attr("nullable")
        r.keyword_from_attr("default")
        if self.values is not None:
            r.keyword_from_attr("values")

    def parse(self, value):
        if value is None:
            return value

        if self.type_ == "float":
            return float(value)
        elif self.type_ == "int":
            return int(value)
        elif self.type_ == "datetime":
            return isoparse(value)
        elif self.type_ == "date":
            return isoparse(value).date()
        else:
            return value


class SpaceTrackClient:
    """SpaceTrack client class.

    Parameters:
        identity: Space-Track username.
        password: Space-Track password.
        base_url: May be overridden to use e.g. https://testing.space-track.org/
        rush_store: A :mod:`rush` storage backend. By default, a
            :class:`~rush.stores.dictionary.DictionaryStore` is used. You may
            wish to use :class:`~rush.stores.dictionary.RedisStore` to
            follow rate limits from multiple instances.
        rush_key_prefix: You may choose a prefix for the keys that will be
            stored in `rush_store`, e.g. to avoid conflicts in a redis db.
        httpx_client: Provide a custom ``httpx.Client` instance.
            ``SpaceTrackClient`` takes ownership of the httpx client. You should
            only provide your own client if you need to configure it first (e.g.
            for a proxy).
        additional_rate_limit: Optionally, a :class:`rush.quota.Quota` if you
            want to restrict the rate limit further than the defaults.

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

    # "request class" methods will be looked up by request controller in this
    # order
    request_controllers = OrderedDict.fromkeys(
        [
            "basicspacedata",
            "expandedspacedata",
            "fileshare",
            "spephemeris",
            "publicfiles",
        ]
    )

    request_controllers["basicspacedata"] = {
        "announcement",
        "boxscore",
        "cdm_public",
        "decay",
        "gp",
        "gp_history",
        "launch_site",
        "omm",
        "satcat",
        "satcat_change",
        "satcat_debut",
        "tip",
        "tle",
        "tle_latest",
        "tle_publish",
    }

    request_controllers["expandedspacedata"] = {
        "car",
        "cdm",
        "maneuver",
        "maneuver_history",
        "organization",
        "satellite",
    }

    request_controllers["fileshare"] = {
        "delete",
        "download",
        "file",
        "folder",
        "upload",
    }

    request_controllers["spephemeris"] = {
        "download",
        "file",
        "file_history",
    }

    request_controllers["publicfiles"] = {
        "dirs",
        "download",
    }

    # List of (class, controller) tuples for
    # requests which do not return a modeldef
    offline_predicates = {
        ("download", "fileshare"): {"file_id", "folder_id", "recursive"},
        ("upload", "fileshare"): {"folder_id", "file"},
        ("download", "spephemeris"): set(),
        ("dirs", "publicfiles"): set(),
        ("download", "publicfiles"): set(),
    }
    param_fields = {
        ("download", "publicfiles"): {"name"},
    }

    # These predicates are available for every request class.
    rest_predicates = {
        Predicate("predicates", "str"),
        Predicate("metadata", "enum", values=("true", "false")),
        Predicate("limit", "str"),
        Predicate("orderby", "str"),
        Predicate("distinct", "enum", values=("true", "false")),
        Predicate(
            "format",
            "enum",
            values=("json", "xml", "html", "csv", "tle", "3le", "kvn", "stream"),
        ),
        Predicate("emptyresult", "enum", values=("show",)),
        Predicate("favorites", "str"),
    }

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
            httpx_client = httpx.Client()
        self.client = httpx_client
        self.identity = identity
        self.password = password

        self.client.base_url = base_url

        # If set, this will be called when we sleep for the rate limit.
        self.callback = None

        self._authenticated = False
        self._predicates = dict()
        self._controller_proxies = dict()

        # From https://www.space-track.org/documentation#/api:
        #   Space-track throttles API use in order to maintain consistent
        #   performance for all users. To avoid error messages, please limit
        #   your query frequency.
        #   Limit API queries to less than 30 requests per minute / 300 requests
        #   per hour
        if rush_store is None:
            rush_store = RushDictionaryStore()
        limiter = PeriodicLimiter(rush_store)
        self._per_minute_throttle = Throttle(
            limiter=limiter,
            rate=Quota.per_minute(30),
        )
        self._per_hour_throttle = Throttle(
            limiter=limiter,
            rate=Quota.per_hour(300),
        )
        self._per_minute_key = rush_key_prefix + "st_req_min"
        self._per_hour_key = rush_key_prefix + "st_req_hr"
        self._additional_key = rush_key_prefix + "st_req_custom"
        if isinstance(additional_rate_limit, Quota):
            self._additional_throttle = Throttle(
                limiter=limiter, rate=additional_rate_limit
            )
        elif additional_rate_limit is None:
            self._additional_throttle = None
        else:
            raise TypeError("additional_rate_limit must be a rush.quota.Quota")

    @property
    def base_url(self):
        return str(self.client.base_url)

    @base_url.setter
    def base_url(self, url):
        self.client.base_url = url

    def _handle_event(self, event):
        if isinstance(event, NormalRequest):
            return self.client.send(
                event.request,
                follow_redirects=event.follow_redirects,
                stream=event.stream,
            )
        elif isinstance(event, ReadResponse):
            return event.response.read()
        elif isinstance(event, IterLines):
            return _iter_lines_generator(event.response)
        elif isinstance(event, IterContent):
            return _iter_content_generator(event.response, event.decode)
        elif isinstance(event, RateLimitWait):
            self._ratelimit_wait(event.duration)
        else:
            raise RuntimeError(f"Unknown event type: {type(event)}")

    def _run_event_generator(self, g):
        # Start generator by sending in None
        ret = None

        while True:
            try:
                event = g.send(ret)
            except StopIteration as exc:
                if isinstance(exc.value, Event):
                    return self._handle_event(exc.value)

                return exc.value

            ret = self._handle_event(event)

    def _auth_generator(self):
        if not self._authenticated:
            data = {"identity": self.identity, "password": self.password}
            resp = yield NormalRequest(
                self.client.build_request("POST", "ajaxauth/login", data=data)
            )
            _raise_for_status(resp)

            # If login failed, we get a JSON response with {'Login': 'Failed'}
            resp_data = resp.json()
            if isinstance(resp_data, Mapping):
                if resp_data.get("Login", None) == "Failed":
                    raise AuthenticationError()

            self._authenticated = True

    def authenticate(self):
        """Authenticate with Space-Track.

        Raises:
            spacetrack.base.AuthenticationError: Incorrect login details.

        .. note::

            This method is called automatically when required.
        """
        self._run_event_generator(self._auth_generator())

    def _generic_request_generator(
        self,
        class_,
        iter_lines=False,
        iter_content=False,
        controller=None,
        parse_types=False,
        **kwargs,
    ):
        if iter_lines and iter_content:
            raise ValueError("iter_lines and iter_content cannot both be True")

        if "format" in kwargs and parse_types:
            raise ValueError("parse_types can only be used if format is unset.")

        if controller is None:
            controller = self._find_controller(class_)
        else:
            classes = self.request_controllers.get(controller, None)
            if classes is None:
                raise ValueError(f"Unknown request controller {controller!r}")
            if class_ not in classes:
                raise ValueError(
                    f"Unknown request class {class_!r} for controller {controller!r}"
                )

        # Decode unicode unless class == download, including conversion of
        # CRLF newlines to LF.
        decode = class_ != "download"
        if not decode and iter_lines:
            error = (
                "iter_lines disabled for binary data, since CRLF newlines "
                "split over chunk boundaries would yield extra blank lines. "
                "Use iter_content=True instead."
            )
            raise ValueError(error)

        offline_check = (class_, controller) in self.offline_predicates
        valid_fields = {p.name for p in self.rest_predicates}
        predicates = None

        yield from self._auth_generator()

        if not offline_check:
            # Validate keyword argument names by querying valid predicates from
            # Space-Track
            predicates = yield from self._get_predicates_generator(class_, controller)
            predicate_fields = {p.name for p in predicates}
            valid_fields |= predicate_fields
        else:
            valid_fields |= self.offline_predicates[(class_, controller)]

        valid_params = self.param_fields.get((class_, controller), set())
        params = dict()

        url = f"{controller}/query/class/{class_}"

        for key, value in kwargs.items():
            if key not in valid_fields | valid_params:
                raise TypeError(f"'{class_}' got an unexpected argument '{key}'")

            if class_ == "upload" and key == "file":
                continue

            if key in valid_params:
                params[key] = value
                continue

            value = quote(_stringify_predicate_value(value), safe="")
            url += f"/{key}/{value}"

        if class_ == "upload":
            if "file" not in kwargs:
                raise TypeError("missing keyword argument: 'file'")

            request = self.client.build_request(
                "POST",
                url,
                files={"file": kwargs["file"]},
                params=params,
            )
            logger.debug(request.url)
            resp = yield from self._ratelimited_send_generator(request)
        else:
            request = self.client.build_request("GET", url, params=params)
            logger.debug(request.url)
            resp = yield from self._ratelimited_send_generator(
                request, stream=iter_lines or iter_content
            )

        if httpx.codes.is_error(resp.status_code):
            # If we're about to raise an error, fetch the full response in case
            # we're streaming
            yield ReadResponse(resp)

        _raise_for_status(resp)

        if resp.encoding is None:
            resp.encoding = "UTF-8"

        if iter_lines:
            return IterLines(resp)
        elif iter_content:
            return IterContent(resp, decode)
        else:
            # If format is specified, return that format unparsed. Otherwise,
            # parse the default JSON response.
            if "format" in kwargs:
                if decode:
                    data = resp.text
                    # Replace CRLF newlines with LF, Python will handle platform
                    # specific newlines if written to file.
                    data = data.replace("\r\n", "\n")
                else:
                    data = resp.content
                return data
            else:
                data = resp.json()

                if predicates is None or not parse_types:
                    return data
                else:
                    return self._parse_types(data, predicates)

    def generic_request(
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
        return self._run_event_generator(
            self._generic_request_generator(
                class_=class_,
                iter_lines=iter_lines,
                iter_content=iter_content,
                controller=controller,
                parse_types=parse_types,
                **kwargs,
            )
        )

    @staticmethod
    def _parse_types(data, predicates):
        predicate_map = {p.name: p for p in predicates}

        for obj in data:
            for key, value in obj.items():
                if key.lower() in predicate_map:
                    obj[key] = predicate_map[key.lower()].parse(value)

        return data

    def _ratelimited_send_generator(self, request, *, stream=False):
        """Send a request, handling rate limiting."""
        minute_limit = self._per_minute_throttle.check(self._per_minute_key, 1)
        hour_limit = self._per_hour_throttle.check(self._per_hour_key, 1)

        sleep_time = 0

        if minute_limit.limited:
            sleep_time = minute_limit.retry_after.total_seconds()

        if hour_limit.limited:
            sleep_time = max(sleep_time, hour_limit.retry_after.total_seconds())

        if self._additional_throttle is not None:
            additional_limit = self._additional_throttle.check(self._additional_key, 1)
            sleep_time = max(sleep_time, additional_limit.retry_after.total_seconds())

        if sleep_time > 0:
            yield RateLimitWait(sleep_time)

        req_event = NormalRequest(request, stream=stream, follow_redirects=True)
        resp = yield req_event

        # It's possible that Space-Track will return HTTP status 500 with a
        # query rate limit violation. This can happen if a script is cancelled
        # before it has finished sleeping to satisfy the rate limit and it is
        # started again.
        #
        # Let's catch this specific instance and retry once if it happens.
        if resp.status_code == 500:
            # Let's only retry if the error page tells us it's a rate limit
            # violation.
            yield ReadResponse(resp)
            if "violated your query rate limit" in resp.text:
                # It seems that only the per-minute rate limit causes an HTTP
                # 500 error. Breaking the per-hour limit seems to result in an
                # email from Space-Track instead.
                yield RateLimitWait(
                    self._per_minute_throttle.rate.period.total_seconds()
                )
                resp = yield req_event

        return resp

    def _ratelimit_callback(self, until):
        duration = int(round(until - time.monotonic()))
        logger.info("Rate limit reached. Sleeping for {:d} seconds.", duration)

        if self.callback is not None:
            self.callback(until)

    def _ratelimit_wait(self, duration):
        until = time.monotonic() + duration
        t = threading.Thread(target=self._ratelimit_callback, args=(until,))
        t.daemon = True
        t.start()
        time.sleep(duration)

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
                f"'{self.__class__.__name__}' object has no attribute '{attr}'"
            )

        # generic_request can resolve the controller itself, but we
        # pass it because we have to check if the class_ is owned
        # by a controller here anyway.
        function = partial(self.generic_request, class_=attr, controller=controller)
        function.get_predicates = partial(
            self.get_predicates, class_=attr, controller=controller
        )
        return function

    def __dir__(self):
        """Include request controllers and request classes."""
        attrs = list(self.__dict__)
        attrs.append("base_url")  # property
        request_classes = {
            class_
            for classes in self.request_controllers.values()
            for class_ in classes
        }

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
            raise ValueError(f"Unknown request class {class_!r}")

    def _download_predicate_data_generator(self, class_, controller):
        yield from self._auth_generator()

        url = f"{controller}/modeldef/class/{class_}"
        req = self.client.build_request("GET", url)
        logger.debug(req.url)

        resp = yield NormalRequest(req)

        _raise_for_status(resp)

        return resp.json()["data"]

    def _get_predicates_generator(self, class_, controller):
        if class_ not in self._predicates:
            if controller is None:
                controller = self._find_controller(class_)
            else:
                classes = self.request_controllers.get(controller, None)
                if classes is None:
                    raise ValueError(f"Unknown request controller {controller!r}")
                if class_ not in classes:
                    raise ValueError(f"Unknown request class {class_!r}")

            download = self._download_predicate_data_generator(class_, controller)
            predicates_data = yield from download
            predicate_objects = self._parse_predicates_data(predicates_data)
            self._predicates[class_] = predicate_objects

        return self._predicates[class_]

    def get_predicates(self, class_, controller=None):
        """Get full predicate information for given request class, and cache
        for subsequent calls.
        """
        return self._run_event_generator(
            self._get_predicates_generator(class_, controller)
        )

    def _parse_predicates_data(self, predicates_data):
        predicate_objects = []
        for field in predicates_data:
            full_type = field["Type"]
            type_match = type_re.match(full_type)
            if not type_match:
                raise ValueError(f"Couldn't parse field type '{full_type}'")

            type_name = type_match.group(1)
            field_name = field["Field"].lower()
            nullable = field["Null"] == "YES"
            default = field["Default"]

            types = {
                # Strings
                "char": "str",
                "varchar": "str",
                "longtext": "str",
                "text": "str",
                # varbinary only used for 'file' request class, for the
                # 'file_link' predicate.
                "varbinary": "str",
                # Integers
                "bigint": "int",
                "int": "int",
                "tinyint": "int",
                "smallint": "int",
                "mediumint": "int",
                # Floats
                "decimal": "float",
                "float": "float",
                "double": "float",
                # Date/Times
                "date": "date",
                "timestamp": "datetime",
                "datetime": "datetime",
                # Enum
                "enum": "enum",
                # Bytes
                "longblob": "bytes",
            }

            if type_name not in types:
                warnings.warn(
                    f"Unknown predicate type {type_name!r}",
                    UnknownPredicateTypeWarning,
                )

            predicate = Predicate(
                name=field_name,
                type_=types.get(type_name, type_name),
                nullable=nullable,
                default=default,
            )

            if type_name == "enum":
                enum_match = enum_re.match(full_type)
                if not enum_match:
                    raise ValueError(f"Couldn't parse enum type '{full_type}'")

                # match.groups() doesn't work for repeating groups, use findall
                predicate.values = tuple(re.findall(r"'(\w+)'", full_type))

            predicate_objects.append(predicate)

        return predicate_objects

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.client.close()

    def __repr__(self):
        r = ReprHelper(self)
        r.parantheses = ("<", ">")
        r.keyword_from_attr("identity")
        return str(r)


class _ControllerProxy:
    """Proxies request class methods with a preset request controller."""

    def __init__(self, client, controller):
        # The client will cache _ControllerProxy instances, so only store
        # a weak reference to it.
        self.client = weakref.proxy(client)
        self.controller = controller

    def __getattr__(self, attr):
        if attr not in self.client.request_controllers[self.controller]:
            raise AttributeError(f"'{self!r}' object has no attribute '{attr}'")

        function = partial(
            self.client.generic_request, class_=attr, controller=self.controller
        )
        function.get_predicates = partial(
            self.client.get_predicates, class_=attr, controller=self.controller
        )

        return function

    def __repr__(self):
        r = ReprHelper(self)
        r.parantheses = ("<", ">")
        r.keyword_from_attr("controller")
        return str(r)

    def get_predicates(self, class_):
        """Proxy ``get_predicates`` to client with stored request
        controller.
        """
        return self.client.get_predicates(class_=class_, controller=self.controller)


def _iter_lines_generator(response):
    for line in response.iter_lines():
        yield line.rstrip("\n")


def _iter_content_generator(response, decode_unicode):
    """Generator used to yield chunks for a streamed response."""
    if decode_unicode:
        it = response.iter_text()
    else:
        it = response.iter_bytes()
    for chunk in it:
        if decode_unicode:
            # Replace CRLF newlines with LF, Python will handle
            # platform specific newlines if written to file.
            chunk = chunk.replace("\r\n", "\n")
            # Chunk could be ['...\r', '\n...'], strip trailing \r
            chunk = chunk.rstrip("\r")
        yield chunk


def _raise_for_status(response):
    """Raise the `HTTPStatusError` if one occurred.

    This is the :meth:`httpx.Response.raise_for_status` method, modified to add
    the response from Space-Track, if given.
    """

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message = exc.args[0]
        spacetrack_error_msg = None

        try:
            json = response.json()
            if isinstance(json, Mapping):
                spacetrack_error_msg = json["error"]
        except (ValueError, KeyError, httpx.ResponseNotRead):
            pass

        if not spacetrack_error_msg:
            try:
                spacetrack_error_msg = response.text
            except httpx.ResponseNotRead:
                pass

        if spacetrack_error_msg:
            message += "\nSpace-Track response:\n" + spacetrack_error_msg

        raise httpx.HTTPStatusError(
            message, request=exc.request, response=exc.response
        ) from exc
