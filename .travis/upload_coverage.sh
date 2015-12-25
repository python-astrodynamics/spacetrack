#!/bin/bash

set -e
set -x

NO_COVERAGE_TOXENVS=(py2flake8 py3flake8 docs)
if ! [[ "${NO_COVERAGE_TOXENVS[*]}" =~ "${TOXENV}" ]]; then
    source ~/.venv/bin/activate
    codecov --env TRAVIS_OS_NAME TOXENV
fi
