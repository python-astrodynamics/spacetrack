import nox

nox.options.reuse_existing_virtualenvs = True
nox.options.default_venv_backend = "uv"


@nox.session(python="3.13")
def docs(session: nox.Session) -> None:
    session.run_install(
        "uv",
        "sync",
        "--no-dev",
        "--group=docstest",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

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


@nox.session(python=["3.9", "3.10", "3.11", "3.12", "3.13"])
def tests(session: nox.Session) -> None:
    session.run_install(
        "uv",
        "sync",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    if session.posargs:
        tests = session.posargs
    else:
        tests = ["tests/"]

    session.run(
        "coverage",
        "run",
        "-m",
        "pytest",
        *tests,
    )
