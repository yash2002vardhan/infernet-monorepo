"""
File Manager: Utility functions to download and upload files to Arweave, as well
as check if a file exists on Arweave.
"""

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import requests
from ar import Peer, Transaction, Wallet  # type: ignore
from ar.manifest import Manifest  # type: ignore
from ar.utils import b64dec  # type: ignore
from ar.utils.transaction_uploader import get_uploader  # type: ignore
from reretry import retry  # type: ignore
from rich.progress import BarColumn, Progress, ProgressColumn, Task
from rich.progress import TaskID as PBarID
from rich.progress import TextColumn, TimeElapsedColumn, TimeRemainingColumn
from ritual_arweave.concurrency_utils import QueueProcessor, Worker
from ritual_arweave.types import LargeFileManifest, Tags
from ritual_arweave.utils import (
    MAX_NODE_BYTES,
    PUBLIC_GATEWAYS,
    get_sha256_digest,
    get_tags_dict,
    load_wallet,
)
from ritual_arweave.utils import log as default_logger
from ritual_arweave.version import VERSION


class FileNotReadyException(Exception):
    """Exception raised when a file is not ready for download from Arweave."""

    pass


MAXIMUM_UPLOAD_SIZE = 1000 * 1024 * 5  # 5 MB

log = logging.getLogger(__name__)

Gateway = str
TxID = str
Section = Tuple[Path, TxID]

STANDBY = "💤"


class FileManager:
    """
    A class to manage file operations with Arweave, including downloading,
    uploading, and checking file existence.
    """

    def __init__(
        self,
        gateways: List[str] | str = PUBLIC_GATEWAYS,
        wallet_path: str = "./wallet.json",
        logger: Callable[[str], None] = default_logger.info,
        max_upload_size: int = MAXIMUM_UPLOAD_SIZE,
        show_progress_bar: bool = True,
    ):
        """
        Initialize the FileManager with the given API URL, wallet path, and logger.

        Args:
            gateways (List[str] | str): A list of gateway URLs to use for file
            operations.
            wallet_path (str): The path to the wallet file.
            logger (Callable[[str], None]): A logging function.
            max_upload_size (int): The maximum size of a file to upload in bytes.
            show_progress_bar (bool): Whether to show a progress bar for file operations.
        """
        if isinstance(gateways, str):
            gateways = [gateways]
        self.gateways = gateways
        self.wallet_path = wallet_path
        self.logger = logger
        self.max_upload_size = max_upload_size
        self.default_gateway = self.gateways[0]
        self.show_progres_bar = show_progress_bar

        if show_progress_bar:
            # Disable logging when using the progress bar
            def null(a: str, *b: Any) -> None:
                pass

            log.info = null  # type: ignore
            log.error = null  # type: ignore
            log.debug = null  # type: ignore

    def gateway(self, index: Optional[int] = None) -> str:
        """Get the current gateway URL.

        Args:
            index (Optional[int]): The index of the gateway to return.

        Returns:
            str: The gateway URL.
        """
        if index is None:
            return self.default_gateway

        return self.gateways[index % len(self.gateways)]

    def get_peer(self, index: Optional[int] = None) -> Peer:
        """Get the peer at the given index.

        Args:
            index (Optional[int]): The index of the peer to return.

        Returns:
            Peer: The peer object.
        """
        return Peer(self.gateway(index))

    @property
    def peer(self) -> Peer:
        """Get the peer. If index is provided, return the peer at that index.
        Otherwise, return the next peer in the list.

        Args:
            index (Optional[int]): The index of the peer to return.

        Returns:
            Peer: The peer object.
        """
        return Peer(self.gateway())

    def get_wallet(self, index: Optional[int] = None) -> Wallet:
        """Get the wallet & configure it with the peer at the given index."""
        return load_wallet(self.wallet_path, api_url=self.gateway(index))

    @property
    def wallet(self) -> Wallet:
        """
        Load and return the wallet from the wallet path.

        Args:
            index (Optional[int]): The index of the peer to configure the wallet with.

        Returns:
            Wallet: The loaded wallet.
        """
        return load_wallet(self.wallet_path, api_url=self.gateway())

    @retry(exceptions=(Exception,), tries=5, delay=0.1)  # type: ignore
    def get_largefile_manifest(self, txid: str) -> Optional[LargeFileManifest]:
        """
        For handling of very large files, we chunk those files into different segments
        and upload those segments individually. We then aggregate the transaction IDs
        of each segment into a manifest file. This method retrieves the manifest file
        and returns a LargeFileManifest object containing the file data.

        Returns:
            LargeFileManifest: The LargeFileManifest object containing the file data.
        """
        # check if the file is ready
        self.check_ready(txid)

        # Check if the transaction is a manifest
        peer = self.get_peer()

        log.info(f"Getting Manifest file {peer.api_url} - {txid}")

        query_str = (
            """
                    query {
                        transaction(
                            id: "%s"
                        ) {
                            id
                            owner {
                              address
                            }
                            tags {
                              name
                              value
                            }
                            block {
                              timestamp
                              height
                            }
                        }
                    }
                """
            % txid
        )

        try:
            res = peer.graphql(query_str)
        except Exception as e:
            self.logger(f"Failed to download {txid}. Error: {e}")
            raise e

        tx_tags: dict[str, str] = get_tags_dict(res["data"]["transaction"]["tags"])

        if tx_tags.get("Content-Type") != "application/x.arweave-manifest+json":
            return None

        # construct the manifest dictionary from file bytes
        m_bytes = peer.tx_data(txid)
        _files_data = cast(Dict[str, Any], json.loads(m_bytes.decode()))
        _paths = _files_data.get("paths", {})

        tags = peer.tx_tags(txid)

        # get the overall file size (useful for the progress bars)
        size_tags = [tag for tag in tags if tag["name"] == b"File-Size"]
        size_tag = (
            size_tags[0]["value"]
            if size_tags
            else len(_files_data.keys()) * self.max_upload_size
        )

        log.debug("manifest_data", _files_data)

        return LargeFileManifest(
            size=int(size_tag),
            files={k: _paths[k]["id"] for k in _paths.keys()},
        )

    def concat_files(self, temp_dir: Path, target_dir: Path) -> None:
        """
        Concatenate the sections into a single file.

        Args:
            temp_dir (Path): The temporary directory containing the sections.
            target_dir (Path): The target directory to write the concatenated file.

        Returns:
            None
        """
        # Concatenate the sections into a single file
        with open(target_dir, "wb") as file_handler:
            _iterdir = sorted(temp_dir.iterdir(), key=lambda x: int(x.stem))
            for section_path in _iterdir:
                with open(section_path, "rb") as section_handler:
                    file_handler.write(section_handler.read())

    def download(self, target_path: str | Path, txid: str) -> Path:
        """
        Download an Arweave data transaction to a given path.

        Checks if the transaction is a manifest transaction with the type Sectioned.
        If so, downloads the manifest and then downloads each section. Otherwise,
        downloads the data transaction directly.

        Args:
            target_path (str|Path): The path to download the file to.
            txid (str): The transaction ID of the data transaction.

        Returns:
            Path: The absolute path of the downloaded file.
        """
        target_path = Path(target_path)

        log.info(f"Downloading {txid} to {target_path}")
        manifest_data = self.get_largefile_manifest(txid)
        progress = self.get_progress()

        if manifest_data is None:
            overall_task_id = progress.add_task(
                f"Downloading {target_path}",
                total=self.get_peer().tx_data_size(txid),
            )

            return self.download_section(
                target_path,
                txid,
                self.gateway(),
                progress,
                overall_task_id,
                overall_task_id,
            )

        overall_task_id = progress.add_task(
            f"Downloading {target_path}",
            total=manifest_data.size,
        )

        files: Dict[str, str] = manifest_data.files

        queue_processor: QueueProcessor[Gateway, Section] = QueueProcessor(logger=log)

        progress_bars: Dict[Gateway, PBarID] = {}

        for gateway in self.gateways:
            progress_bars[gateway] = progress.add_task(
                description=f"{STANDBY} - {gateway}",
                total=1,
                completed=0,
            )

        def worker_fn(gw: Gateway, task: Section) -> None:
            """
            Download a section of the file.

            Args:
                gw: The gateway to download from.
                task: The section to download.

            Returns:
                None
            """
            _section_path, _tx = task
            pbar_id = progress_bars[gw]
            progress.update(
                pbar_id,
                description=f"⬇️ - {gw}: {_section_path.name}",
                completed=0,
            )
            self.download_section(
                _section_path, _tx, gw, progress, pbar_id, overall_task_id
            )
            progress.update(
                pbar_id,
                description=f"{STANDBY} - {gateway}",
            )
            log.info(f"✅ Downloaded {_section_path} - {_tx}")

        def evict_hook(gw: Gateway) -> None:
            """
            Remove the progress bar for the given gateway. This is used after a worker
            has completed its download task.

            Args:
                gw: The gateway to remove the progress bar for.

            Returns:
                None
            """
            try:
                progress.remove_task(progress_bars[gw])
            except Exception:
                pass

        with tempfile.TemporaryDirectory() as _temp:
            temp_dir = Path(_temp)
            for _name, _tx_id in files.items():
                queue_processor.add_task((temp_dir / _name, _tx_id))

            for gateway in self.gateways:
                worker = Worker(context=gateway, work=worker_fn, evict_hook=evict_hook)
                queue_processor.add_worker(worker)

            if self.show_progres_bar:
                with progress:
                    queue_processor.process()
            else:
                queue_processor.process()

            self.concat_files(temp_dir, Path(target_path))

        return Path(target_path)

    @retry(exceptions=(Exception,), tries=3, delay=0.1)  # type: ignore
    def check_ready(self, txid: str) -> str:
        """
        Check if the file is ready for download.

        Args:
            txid (str): The transaction ID of the data transaction.

        Returns:
            str: The gateway URL to download the file from.

        Raises:
            FileNotReadyException: If the file is pending and not ready for download.
        """
        gw = self.gateway()

        log.debug(f"checking if resource is ready: {gw} {txid}")
        r = requests.get(f"{gw}/tx/{txid}")
        if r.status_code == 404:
            self.logger(f"file with txid {txid} does not exist")
            raise FileNotReadyException(
                f"File with txid {txid} does not exist on the gateway."
            )

        if r.status_code == 202:
            self.logger(f"file with txid {txid} is pending")
            raise FileNotReadyException(
                f"File with txid {txid} is pending. It has not reached finality yet."
            )
        return gw

    def download_section(
        self,
        pathname: Path | str,
        txid: str,
        gateway: str,
        progress: Progress,
        pbar_id: PBarID,
        overall_task_id: PBarID,
    ) -> Path:
        """
        Download an Arweave data transaction to a given path.

        Args:
            pathname (Path | str): The path to download to.
            txid (str): The transactionk ID of the data transaction.
            gateway (str): The gateway to download the file from.
            progress (Progress): A rich Progress object to display download progress.
            pbar_id (PBarID): The task ID of the current download progress.
            overall_task_id (PBarID): The task ID of the overall download progress.

        Returns:
            str: The absolute path of the downloaded file.

        Raises:
            FileNotReadyException: If the file is pending and not ready for download.
        """

        # Check if the file is pending
        self.check_ready(txid)

        loaded_bytes = 0
        peer = Peer(gateway, timeout=3)
        total_size = peer.tx_data_size(txid)
        progress.update(pbar_id, total=total_size)
        with open(pathname, "wb") as binary_file:
            try:
                # Try downloading the transaction data directly from the default data
                # endpoint
                data = peer.data(txid, timeout=3)

                # Write downloaded file to disk
                binary_file.write(data)

                progress.update(pbar_id, advance=len(data))
                progress.update(overall_task_id, advance=len(data))

                return Path(pathname)
            except Exception:
                log.debug(
                    f"failed to download transaction data for {txid} directly."
                    + " Will try downloading in chunks."
                )

            """
             if we are unable to download files directly, likely the file is too big.
             we can download in chunks.
             To do so, start with the end offset and fetch a chunk.
             Subtract its size from the transaction size.
             If there are more chunks to fetch, subtract the size of the chunk
             from the offset and fetch the next chunk.
             Note that chunks seem to take some time to be
             available even after a transaction may be finalized.
             For more information see:
             https://docs.arweave.org/developers/arweave-node-server/http-api
            """

            chunk_offset: dict[str, int] = peer.tx_offset(txid)
            size: int = chunk_offset["size"]
            start_offset: int = chunk_offset["offset"] - size + 1

            if size < MAX_NODE_BYTES:
                # If the size is less than the maximum node download size
                # just download the file to disk via the tx_data endpoint
                # which purportedly downloads files regardless of how it
                # was uploaded (but has this size limitation)
                data = peer.tx_data(txid)
                binary_file.write(data)
            else:
                while loaded_bytes < size:
                    # Download this chunk
                    chunk_data = peer.chunk(start_offset + loaded_bytes)["chunk"]
                    # Arweave files use b64 encoding. We decode the chunk here
                    chunk_data_dec = b64dec(chunk_data)
                    # Write the part of the file to disk
                    binary_file.write(chunk_data_dec)
                    # Update offset to subtract from file size
                    loaded_bytes += len(chunk_data_dec)
                    # Update progress bar
                    data_size = len(chunk_data_dec)
                    progress.update(pbar_id, advance=data_size)
                    progress.update(overall_task_id, advance=data_size)

            return Path(pathname)

    def get_progress(self) -> Progress:
        class SpeedColumn(ProgressColumn):
            """Custom column to display the upload speed."""

            def render(self, task: Task) -> str:
                speed = task.speed
                if speed is None:
                    return "N/A"
                speed_mbs = speed / (1024 * 1024)
                return f"{speed_mbs:.2f} MB/s"

        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            SpeedColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        return progress

    def upload(self, _file_path: Path | str, tags_dict: dict[str, str]) -> Transaction:
        """
        Upload a file to Arweave with the given tags. If the file is larger than
        the maximum node upload size, upload it in section.

        1. Split the file into multiple files each with a maximum size of
        MAXIMUM_UPLOAD_SIZE
        2. Upload each section to Arweave using the upload_section method
        3. Upload a manifest containing the transaction IDs of each section
        4. Return the transaction ID of the manifest file

        Args:
            _file_path (Path | str): The path to the file to be uploaded.
            tags_dict (dict[str, str]): A dictionary of tags to be added to the
            transaction.
        """
        file_path: Path = (
            Path(_file_path) if isinstance(_file_path, str) else _file_path
        )

        progress = self.get_progress()

        overall_pbar_id = progress.add_task(
            f"Uploading {file_path.name}", total=os.path.getsize(file_path)
        )

        if os.path.getsize(file_path) < self.max_upload_size:
            return self.upload_section(
                file_path,
                tags_dict,
                self.gateway(),
                progress,
                overall_pbar_id,
                overall_pbar_id,
            )

        # create a temporary directory to store the file sections
        log.info("Uploading large file in sections")
        with tempfile.TemporaryDirectory() as _temp:
            temp_dir = Path(_temp)
            # split the file into sections
            with open(file_path, "rb") as file_handler:
                file_number = 0
                while True:
                    chunk = file_handler.read(self.max_upload_size)
                    if not chunk:
                        break
                    section_dir = temp_dir / f"{file_number}.section"
                    with open(section_dir, "wb") as section_handler:
                        section_handler.write(chunk)
                    file_number += 1

            queue_processor: QueueProcessor[Gateway, Path] = QueueProcessor(logger=log)

            tx_ids: Dict[str, str] = {}

            log.info(f"Created {len(list(temp_dir.iterdir()))} sections")

            progress_bars: Dict[Gateway, PBarID] = {}

            for gateway in self.gateways:
                progress_bars[gateway] = progress.add_task(
                    f"{STANDBY} - {gateway}", total=1, completed=0
                )

            for section_path in temp_dir.iterdir():
                queue_processor.add_task(section_path)

            def worker_fn(gw: Gateway, _section_path: Path) -> None:
                pbar_id = progress_bars[gw]
                progress.update(
                    pbar_id,
                    description=f"⬆️ - {gw}: {_section_path.name}",
                    total=os.path.getsize(_section_path),
                    completed=0,
                )
                tx = self.upload_section(
                    _section_path, tags_dict, gw, progress, pbar_id, overall_pbar_id
                )
                tx_ids[_section_path.name] = tx.id
                log.info(f"✅ Uploaded {_section_path} - {tx.id}")
                progress.update(
                    pbar_id,
                    description=f"{STANDBY} - {gw}",
                )

            def evict_hook(gw: Gateway) -> None:
                progress.remove_task(progress_bars[gw])

            for _gateway in self.gateways:
                worker = Worker(context=_gateway, work=worker_fn, evict_hook=evict_hook)
                queue_processor.add_worker(worker)

            if self.show_progres_bar:
                with progress:
                    queue_processor.process()
            else:
                queue_processor.process()

            timestamp = time.time()

            ritual_tags: Tags = {
                "App-Name": "Ritual",
                "App-Version": VERSION,
                "File-Type": "Sectioned",
                "File-Size": str(os.path.getsize(file_path)),
                "Unix-Time": str(timestamp),
                "File-Name": str(file_path.name),
            }

            # create a manifest object containing the transaction IDs of each section
            manifest_dict = {}

            for _dir, txid in tx_ids.items():
                manifest_dict[_dir] = txid

            m = Manifest(manifest_dict)

            # upload the manifest
            @retry(tries=len(self.gateways), delay=0.2)  # type: ignore
            def _send_manifest() -> Transaction:
                t = Transaction(self.wallet, peer=self.get_peer(), data=m.tobytes())

                t.add_tags(
                    {
                        "Content-Type": "application/x.arweave-manifest+json",
                        "Type": "manifest",
                        **ritual_tags,
                    }
                )

                t.sign()
                t.send()
                return t

            return _send_manifest()

    @retry(tries=3, delay=0.2)  # type: ignore
    def upload_data(
        self, data: bytes, additional_tags: Optional[dict[str, str]] = None
    ) -> Transaction:
        """
        Upload data to Arweave with the given tags.

        Args:
            data: The data to be uploaded.
            additional_tags: Additional tags to be added to the transaction.

        Returns:
            Transaction: The created and signed transaction.
        """
        additional_tags = additional_tags or {}
        t = Transaction(self.wallet, peer=self.get_peer(), data=data)
        ritual_tags: Tags = {
            "App-Name": "Ritual",
            "App-Version": VERSION,
        }

        t.add_tags(
            {
                **ritual_tags,
                "Content-Type": "application/x.arweave-manifest+json",
                "Type": "manifest",
                **additional_tags,
            }
        )

        t.sign()
        t.send()
        return t

    def upload_dict(
        self, d: Dict[str, Any], additional_tags: Optional[dict[str, str]] = None
    ) -> Transaction:
        """
        Upload a dictionary to Arweave with the given tags

        Args:
            d: The dictionary to be uploaded.
            additional_tags: Additional tags to be added to the transaction.

        Returns:
            Transaction: The created and signed transaction.
        """
        return self.upload_data(json.dumps(d).encode(), additional_tags)

    def download_dict(self, txid: str) -> Dict[str, Any]:
        """
        Download a dictionary from Arweave.

        Args:
            txid: The transaction ID of the data transaction.

        Returns:
            Dict[str, Any]: The downloaded dictionary.
        """
        return cast(Dict[str, Any], json.loads(self.download_data(txid)))

    def upload_manifest(
        self,
        manifest_dict: dict[str, str],
        additional_tags: Optional[dict[str, str]] = None,
    ) -> Transaction:
        """
        Upload a manifest to Arweave with the given tags

        Args:
            manifest_dict: The manifest dictionary to be uploaded.
            additional_tags: Additional tags to be added to the transaction.

        Returns:
            Transaction: The created and signed transaction.
        """
        return self.upload_data(Manifest(manifest_dict).tobytes(), additional_tags)

    def download_data(self, txid: TxID) -> bytes:
        """
        Download data from Arweave.

        Args:
            txid: The transaction ID of the data transaction.

        Returns:
            bytes: The downloaded data.
        """
        return cast(bytes, self.peer.tx_data(txid))

    def upload_section(
        self,
        file_path: Path,
        tags_dict: dict[str, str],
        gateway: str,
        progress: Progress,
        task_id: PBarID,
        overall_task_id: PBarID,
    ) -> Transaction:
        """
        Upload a file to Arweave with the given tags.

        Args:
            file_path (Path): The path to the file to be uploaded.
            tags_dict (dict[str, str]): A dictionary of tags to be added to the
            transaction.
            gateway (str): The gateway to upload the file to.
            progress (Progress): A rich Progress object to display upload progress.
            task_id (TaskId): The task ID of the current upload progress.
            overall_task_id (TaskId): The task ID of the overall upload progress.

        Returns:
            Transaction: The created and signed transaction.
        """

        default_tags: Dict[str, str] = {
            "File-Size": str(os.path.getsize(file_path)),
        }

        total_tags = {**tags_dict, **default_tags}

        with open(file_path, "rb", buffering=0) as file_handler:
            tx = Transaction(
                load_wallet(self.wallet_path, api_url=gateway),
                peer=Peer(gateway),
                file_handler=file_handler,
                file_path=file_path,
            )

            for n, v in total_tags.items():
                tx.add_tag(n, v)

            tx.sign()

            uploader = get_uploader(
                tx, file_handler, task_id=task_id, progress=progress
            )

            while not uploader.is_complete:
                # Upload a chunk
                data_size = uploader.upload_chunk()
                if data_size:
                    progress.update(overall_task_id, advance=int(data_size))

        return tx

    def file_exists(self, file_path: str, txid: str) -> bool:
        """
        Given a local file path and a transaction ID, check if the file exists on
        Arweave. Checks for the following:
        - Local file exists
        - Local file's size matches transaction data size
        - Local file's sha256 digest matches transaction digest

        Args:
            file_path (str): The path to the local file.
            txid (str): The transaction ID to check against.

        Returns:
            bool: True if the file exists and matches the transaction, False otherwise.
        """
        query_str = (
            """
                query {
                    transaction(
                    id: "%s"
                    )
                    {
                        owner{
                            address
                        }
                        data{
                            size
                            type
                        }
                        tags{
                            name
                            value
                        }
                    }
                }
            """
            % txid
        )

        res = Peer(self.gateway()).graphql(query_str)

        tx_file_size: int = int(res["data"]["transaction"]["data"]["size"])
        tx_tags: dict[str, str] = get_tags_dict(res["data"]["transaction"]["tags"])

        local_file_exists, size_matches, digest_matches = (
            False,
            False,
            False,
        )

        def _log() -> None:
            """Log the current status of file existence checks."""
            self.logger(
                f"file_path={file_path} local_file_exists={local_file_exists} "
                f"size_matches={size_matches} digest_matches={digest_matches}",
            )

        local_file_exists = os.path.exists(file_path)

        if not local_file_exists:
            _log()
            return False

        size_matches = tx_file_size == os.path.getsize(file_path)

        if not size_matches:
            _log()
            return False

        digest_matches = tx_tags.get("File-SHA256") == get_sha256_digest(file_path)
        _log()
        return digest_matches
