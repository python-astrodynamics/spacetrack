# coding: utf-8
from __future__ import absolute_import, division, print_function

import sys

from .base import AuthenticationError, SpaceTrackClient  # noqa
from .operators import (  # noqa
    greater_than, inclusive_range, less_than, like, not_equal, startswith)

__all__ = [
    'AuthenticationError',
    'greater_than',
    'inclusive_range',
    'less_than',
    'like',
    'not_equal',
    'SpaceTrackClient',
    'startswith',
]

if sys.version_info >= (3, 5):
    from .aio import AsyncSpaceTrackClient  # noqa
    __all__.append('AsyncSpaceTrackClient')

__all__ = tuple(__all__)

__version__ = '0.9.0'
__description__ = 'Python client for space-track.org'

__license__ = 'MIT'

__author__ = 'Frazer McLean'
__email__ = 'frazer@frazermclean.co.uk'
