import logging
from typing import Generator

import pytest
from common import skip_setup, skip_teardown
from utils import arweave_node_lifecycle, get_test_wallet, mint_ar

log = logging.getLogger(__name__)


@pytest.fixture()
def fund_account() -> None:
    """
    Utility fixture to fund the test wallet.
    Returns:
        None
    """
    log.info("Funding test wallet")
    mint_ar(get_test_wallet().address)


@pytest.fixture(autouse=True, scope="session")
def arweave_node() -> Generator[None, None, None]:
    """
    Utility fixture to start and stop the arweave node.
    Returns:
        None
    """
    yield from arweave_node_lifecycle(
        skip_teardown=skip_setup, skip_setup=skip_teardown
    )
