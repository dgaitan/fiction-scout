"""Session-scoped real-server fixture for the Meilisearch live test tier.

Connect to `MEILISEARCH_TEST_URL` if set, otherwise launch the `meilisearch` binary
from `PATH` as a subprocess on a random port. If neither is available,
`live_client` skips the requesting test rather than failing it — the point
is that `nox -s test_meilisearch` degrades gracefully on a machine without
the binary/Docker, not that live tests are optional to write.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import meilisearch

_MASTER_KEY = "fiction-scout-test-master-key"

# `meilisearch` is imported lazily inside each fixture body below, not at
# module level. This whole file is only ever *collected* when the
# `meilisearch` extra is installed (see `tests/conftest.py`'s
# `collect_ignore`), but pytest imports every conftest.py it finds while
# walking `testpaths` regardless of `collect_ignore` — that filter only
# governs which paths become collected *test items*, not which conftest.py
# files get imported. A module-level `import meilisearch` here would break
# every other test suite's collection on a machine without the extra
# installed (confirmed: it did, before this was made lazy).


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_until_healthy(client: meilisearch.Client, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.is_healthy():
            return True
        time.sleep(0.1)
    return False


@pytest.fixture(scope="session")
def meilisearch_url() -> Iterator[str | None]:
    env_url = os.environ.get("MEILISEARCH_TEST_URL")
    if env_url:
        yield env_url
        return

    binary = shutil.which("meilisearch")
    if binary is None:
        yield None
        return

    import meilisearch as meilisearch_module

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory(prefix="fiction-scout-meilisearch-") as db_path:
        process = subprocess.Popen(
            [
                binary,
                "--http-addr",
                f"127.0.0.1:{port}",
                "--master-key",
                _MASTER_KEY,
                "--db-path",
                db_path,
                "--no-analytics",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            client = meilisearch_module.Client(url, _MASTER_KEY)
            if not _wait_until_healthy(client, timeout=10.0):
                yield None
                return
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture
def live_client(meilisearch_url: str | None) -> meilisearch.Client:
    if meilisearch_url is None:
        pytest.skip(
            "No local `meilisearch` binary on PATH and MEILISEARCH_TEST_URL not set"
        )
    import meilisearch as meilisearch_module

    api_key = os.environ.get("MEILISEARCH_TEST_KEY", _MASTER_KEY)
    return meilisearch_module.Client(meilisearch_url, api_key)
