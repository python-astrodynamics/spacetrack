# coding: utf-8
from __future__ import absolute_import, division, print_function

import subprocess
from collections import OrderedDict

from plumbum import local, FG
from shovel import task

pytest = local['py.test']


@task
def quick():
    failed = OrderedDict.fromkeys(
        ['test', 'docs', 'spelling', 'doc8', 'flake8'], False)

    failed['tests'] = bool(subprocess.call(['py.test', 'astrodynamics/']))
    failed['docs'] = bool(subprocess.call(
        ['sphinx-build', '-W', '-b', 'html', 'docs', 'docs/_build/html']))
    failed['spelling'] = bool(subprocess.call([
        'sphinx-build', '-W', '-b', 'spelling', 'docs', 'docs/_build/html']))
    failed['doc8'] = bool(subprocess.call(['doc8', 'docs']))
    failed['flake8'] = bool(subprocess.call(['flake8']))

    print('\nSummary:')
    for k, v in failed.items():
        print('{:8s}: {}'.format(k, 'Fail' if v else 'Pass'))


@task
def coverage():
    pytest['--cov=astrodynamics', '--cov-report=html', '--cov-config=.coveragerc'] & FG
