from chromadb.config import Settings
from chromadb import Client
from chromadb.api import API
import chromadb.server.fastapi
from requests.exceptions import ConnectionError
import hypothesis
import tempfile
import os
import uvicorn
import time
from multiprocessing import Process
import pytest
from typing import Generator, List, Tuple

hypothesis.settings.register_profile(
    "dev", deadline=10000, suppress_health_check=[hypothesis.HealthCheck.data_too_large]
)
hypothesis.settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))


def _run_server():
    """Run a Chroma server locally"""
    settings = Settings(
        chroma_api_impl="local",
        chroma_db_impl="duckdb",
        persist_directory=tempfile.gettempdir() + "/test_server",
    )
    server = chromadb.server.fastapi.FastAPI(settings)
    uvicorn.run(server.app(), host="0.0.0.0", port=6666, log_level="error")


def _await_server(api, attempts=0):
    try:
        api.heartbeat()
    except ConnectionError as e:
        if attempts > 10:
            raise e
        else:
            time.sleep(2)
            _await_server(api, attempts + 1)


def fastapi() -> Generator[API, None, None]:
    """Fixture generator that launches a server in a separate process, and yields a
    fastapi client connect to it"""
    proc = Process(target=_run_server, args=(), daemon=True)
    proc.start()
    api = chromadb.Client(
        Settings(
            chroma_api_impl="rest", chroma_server_host="localhost", chroma_server_http_port="6666"
        )
    )
    _await_server(api)
    yield api
    proc.kill()


def duckdb() -> Generator[API, None, None]:
    """Fixture generator for duckdb"""
    yield Client(
       Settings(
            chroma_api_impl="local",
            chroma_db_impl="duckdb",
            persist_directory=tempfile.gettempdir(),
        )
    )


def duckdb_parquet() -> Generator[API, None, None]:
    """Fixture generator for duckdb+parquet"""
    yield Client(
        Settings(
            chroma_api_impl="local",
            chroma_db_impl="duckdb+parquet",
            persist_directory=tempfile.gettempdir() + "/tests",
        )
    )


def integration_api() -> Generator[API, None, None]:
    """Fixture generator for returning a client configured via environmenet
    variables, intended for externally configured integration tests
    """
    yield chromadb.Client()


def fixtures():
    api_fixtures = [duckdb, duckdb_parquet, fastapi]
    if "CHROMA_INTEGRATION_TEST" in os.environ:
        api_fixtures.append(integration_api)
    if "CHROMA_INTEGRATION_TEST_ONLY" in os.environ:
        api_fixtures = [integration_api]
    return [duckdb]

def persist_configurations():
    return [
        Settings(
            chroma_api_impl="local",
            chroma_db_impl="duckdb+parquet",
            persist_directory=tempfile.gettempdir() + "/tests",
        )
    ]

def persist_old_version_configurations(
    versions: List[str],
) -> List[Tuple[str, Settings]]:
    """
    Only returns configurations that persist to disk at a given path for a version.
    """

    return [
        (
            version,
            Settings(
                chroma_api_impl="local",
                chroma_db_impl="duckdb+parquet",
                persist_directory=tempfile.gettempdir() + "/tests/" + version + "/",
            ),
        )
        for version in versions
    ]

@pytest.fixture(scope="module", params=fixtures())
def api(request):
    yield next(request.param())
