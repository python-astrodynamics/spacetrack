from collections import OrderedDict

from plumbum import FG, TF, local
from plumbum.cmd import doc8, flake8, sphinx_build
from shovel import task

pytest = local['py.test']


@task
def quick():
    passed = OrderedDict()

    passed['test'] = pytest['tests/'] & TF(FG=True)

    passed['docs'] = (
        sphinx_build['-W', '-b', 'spelling', 'docs', 'docs/_build/html'] &
        TF(FG=True))

    passed['spelling'] = (
        sphinx_build['-W', '-b', 'spelling', 'docs', 'docs/_build/html'] &
        TF(FG=True))

    passed['doc8'] = doc8['docs'] & TF(FG=True)

    passed['flake8'] = flake8 & TF(FG=True)

    print('\nSummary:')
    for k, v in passed.items():
        print('{:8s}: {}'.format(k, 'Pass' if v else 'Fail'))


@task
def coverage():
    pytest['--cov=spacetrack', '--cov-report=html', '--cov-config=.coveragerc'] & FG
