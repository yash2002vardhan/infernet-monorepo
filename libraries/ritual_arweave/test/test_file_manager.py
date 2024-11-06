import logging
import os
import tempfile
from pathlib import Path

import pytest
from ar.utils import decode_tag  # type: ignore
from common import skip_slow_tests
from ritual_arweave.file_manager import FileManager
from ritual_arweave.utils import PUBLIC_GATEWAYS
from utils import FixtureType, api_url, mine_block, wallet

log = logging.getLogger(__name__)


def test_upload_and_download_file(fund_account: FixtureType) -> None:
    fm = FileManager(gateways=[api_url], wallet_path=wallet)

    with tempfile.TemporaryDirectory() as temp_dir:
        upload_path = os.path.join(temp_dir, "upload.txt")
        content = "Hello, this is a test file!"
        tags = {"Bing": "Bong"}

        with open(upload_path, "w") as file:
            file.write(content)
        tx = fm.upload(Path(upload_path), tags)

        mine_block()

        recovered = {}
        for tag in tx.tags:
            decoded = decode_tag(tag)
            recovered[decoded["name"].decode()] = decoded["value"].decode()

        # assert that tags is a subset of recovered
        assert tags.items() <= recovered.items()

        download_path = os.path.join(temp_dir, "download.txt")
        fm.download(download_path, tx.id)
        with open(download_path, "r") as file:
            assert file.read() == content


@pytest.mark.skipif(skip_slow_tests, reason="Skipping tests that take a long time")
def test_large_file_download() -> None:
    """
    Downloads a 300mb file from arweave
    """
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    fm = FileManager(gateways=PUBLIC_GATEWAYS, wallet_path="./keyfile-arweave.json")
    fm.download("large.txt", "3KWHWeTNFaJUbyZgdnb7d-qerD_yxqJS__6R6MLx8hY")
    target_sha256 = "17a88af83717f68b8bd97873ffcf022c8aed703416fe9b08e0fa9e3287692bf0"
    assert os.path.exists("large.txt")
    assert os.system(f"sha256sum large.txt | grep {target_sha256}") == 0
