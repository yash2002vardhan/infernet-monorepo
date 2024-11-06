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
import os

from dotenv import load_dotenv
from ritual_arweave.repo_manager import RepoManager
from ritual_arweave.utils import PUBLIC_GATEWAYS

load_dotenv()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    section_size = int(1000 * 1024 * 5)
    wallet_path = "./keyfile-arweave.json"
    fm = RepoManager(
        wallet_path=wallet_path,
        gateways=PUBLIC_GATEWAYS[:],
        max_upload_size=section_size,
        show_progress_bar=True,
    )
    fm.download_repo(
        repo_id=f"{os.getenv('MODEL_OWNER')}/Meta-Llama-3-8B-Instruct",
        base_path="./hello",
    )


if __name__ == "__main__":
    main()
