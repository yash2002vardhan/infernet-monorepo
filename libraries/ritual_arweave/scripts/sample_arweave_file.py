"""
Instructions for setting up this script:
```
# generates a wallet from a seed, default seed is in the Makefile
make generate-wallet
# funds a wallet, default address is the address of the wallet generated
# in the previous step
make fund-wallet mine
# starts the arweave server on port 3069
make start-arweave
"""

import logging
import time
from typing import cast

from ritual_arweave.file_manager import FileManager
from ritual_arweave.utils import PUBLIC_GATEWAYS

section_size = int(1000 * 1024 * 1)
wallet_path = "./keyfile-arweave.json"
size = 20
fm = FileManager(
    wallet_path=wallet_path,
    gateways=PUBLIC_GATEWAYS[:4],
    max_upload_size=section_size,
    # show_progress_bar=False,
)


def upload() -> str:
    tx = fm.upload(f"./{size}MB.txt", {})

    tx_id = tx.id

    logging.info(f"tx_id: {tx_id}")

    return cast(str, tx_id)


def download(tx_id: str) -> None:
    start = time.time()
    fm.download(f"{size}MB-downloaded.txt", tx_id)
    duration = time.time() - start
    logging.info(
        f"{len(fm.gateways)} gateways - speed: {size / duration} MB/s - "
        f"section size {fm.max_upload_size/1e6}mb - download time: {duration}s - "
        f"tx: {tx_id} - {size} MB"
    )
    logging.info("✅ Success")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    # logging.getLogger("ritual_arweave.file_manager").setLevel(logging.DEBUG)
    tx_id = upload()
    logging.info(f"tx_id: {tx_id}")
    # tx_id = "m2Y0M9sNnF7vad8JUplsJLKmMzEh0Uq-_qyAPaMmD_E"
    # download(tx_id)


if __name__ == "__main__":
    main()
