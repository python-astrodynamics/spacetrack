# coding: utf-8
from __future__ import absolute_import, division, print_function

import os
from shutil import rmtree

from plumbum import FG
from plumbum.cmd import pandoc, sphinx_build
from shovel import task
from watchdog.observers import Observer
from watchdog.tricks import ShellCommandTrick
from watchdog.watchmedo import observe_with

from _helpers import check_git_unchanged


@task
def watch():
    """Renerate documentation when it changes."""

    # Start with a clean build
    sphinx_build['-b', 'html', '-E', 'docs', 'docs/_build/html'] & FG

    handler = ShellCommandTrick(
        shell_command='sphinx-build -b html docs docs/_build/html',
        patterns=['*.rst', '*.py'],
        ignore_patterns=['_build/*'],
        ignore_directories=['.tox'],
        drop_during_process=True)
    observer = Observer()
    observe_with(observer, handler, pathnames=['.'], recursive=True)


@task
def gen(skipdirhtml=False):
    """Generate html and dirhtml output."""
    docs_changelog = 'docs/changelog.rst'
    check_git_unchanged(docs_changelog)
    pandoc('--from=markdown', '--to=rst', '--output=' + docs_changelog, 'CHANGELOG.md')
    if not skipdirhtml:
        sphinx_build['-b', 'dirhtml', '-W', '-E', 'docs', 'docs/_build/dirhtml'] & FG
    sphinx_build['-b', 'html', '-W', '-E', 'docs', 'docs/_build/html'] & FG


@task
def clean():
    """Clean build directory."""
    rmtree('docs/_build')
    os.mkdir('docs/_build')
