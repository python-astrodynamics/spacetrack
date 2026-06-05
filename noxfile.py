import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv"

PYPROJECT = nox.project.load_toml("pyproject.toml")
PYTHON_VERSIONS = nox.project.python_versions(PYPROJECT)


@nox.session(python="3.13")
def docs(session: nox.Session) -> None:
    session.run_install("uv", "sync", "--no-default-groups", "--group=docstest")

    temp_dir = session.create_tmp()
    session.run(
        "sphinx-build",
        "-W",
        "-b",
        "html",
        "-d",
        f"{temp_dir}/doctrees",
        "docs",
        "docs/_build/html",
    )
    session.run("doc8", "docs/")


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    session.run_install(
        "uv",
        "sync",
        "--no-default-groups",
        "--group=coverage",
        "--group=test",
    )

    session.run("coverage", "run", "-m", "pytest", *session.posargs)
