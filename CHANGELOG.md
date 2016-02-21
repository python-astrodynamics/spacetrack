# Change Log

## [Unreleased][unreleased]
N/A

## [0.11.0]
### Added
- Some unit tests added for `AsyncSpaceTrackClient`.

### Fixed
- `\r\n` to `\n` newline conversion for async chunk iterator.

### Changed
- `AsyncSpaceTrackClient` can no longer be imported from the top level
  `spacetrack` module, since this would cause an error if optional
  dependency `aiohttp` was not installed. It must be imported from
  `spacetrack.aio`.

## [0.10.0] - 2016-02-04
### Fixed
- Compatibility with `file` and `download` request classes for `fileshare`
  request controller. `upload` request class removed, unable to test.
- Rate limit violation HTTP status code 500 handled during predicate
  information request.

### Changed
- `iter_lines=True` now raises `ValueError` if receiving binary data (currently
  only possible with `download` request class).
- Removed internal method `_get_predicate_fields`, set comprehension used
  inline instead.
- `Predicate` class now has a `default` attribute.

## [0.9.0] - 2016-01-28

First release.

[unreleased]: https://github.com/python-astrodynamics/spacetrack/compare/0.11.0...HEAD
[0.11.0]: https://github.com/python-astrodynamics/spacetrack/compare/0.10.0...0.11.0
[0.10.0]: https://github.com/python-astrodynamics/spacetrack/compare/0.9.0...0.10.0
[0.9.0]: https://github.com/python-astrodynamics/spacetrack/compare/e5fc088a96ec1557d44931e00500cdcef8349fad...0.9.0
