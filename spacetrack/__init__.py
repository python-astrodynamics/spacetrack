# coding: utf-8
from __future__ import absolute_import, division, print_function

from .base import SpaceTrackClient
from .operators import (
    greater_than, inclusive_range, less_than, like, not_equal, startswith)

__all__ = (
    'greater_than',
    'inclusive_range',
    'less_than',
    'like',
    'not_equal',
    'SpaceTrackClient',
    'startswith',
)

__version__ = '0.1.0'
__description__ = 'Python client for space-track.org'

__license__ = 'MIT'

__author__ = 'Frazer McLean'
__email__ = 'frazer@frazermclean.co.uk'
