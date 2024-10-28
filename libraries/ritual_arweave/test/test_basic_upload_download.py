import logging

from ritual_arweave.file_manager import FileManager
from utils import FixtureType, api_url, mine_block, wallet

log = logging.getLogger(__name__)


def test_upload_and_download_blob(fund_account: FixtureType) -> None:
    fm = FileManager(gateways=[api_url], wallet_path=wallet)
    data = "yooooo".encode()
    tx = fm.upload_data(data)
    log.info("tx: %s", tx.id)
    mine_block()
    downloaded = fm.download_data(tx.id)
    assert data == downloaded


def test_upload_download_dict(fund_account: FixtureType) -> None:
    fm = FileManager(gateways=[api_url], wallet_path=wallet)
    data = {"key": "value"}
    tx = fm.upload_dict(data)
    log.info("tx: %s", tx.id)
    mine_block()
    downloaded = fm.download_dict(tx.id)
    assert data == downloaded
