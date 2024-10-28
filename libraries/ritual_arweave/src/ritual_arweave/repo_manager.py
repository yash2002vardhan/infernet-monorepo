"""
Utility functions for uploading/downloading repositories to/from Arweave. Each repository
contains multiple artifact files.


Repository files (artifacts) are logically grouped together via a Manifest file, which
maps individual transaction data to named files.

When uploading a repo directory, a version mapping dictionary file is expected to be
provided. The mapping should contain a map of filename to version tag. The version tag
is useful if a specific version of a file is meant to be downloaded. If no mapping is
specified, version will be an empty string.
"""

import json
import logging
import mimetypes
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

import requests
from ar import Transaction  # type: ignore
from ar.manifest import Manifest  # type: ignore
from pydantic import BaseModel
from requests.exceptions import HTTPError
from ritual_arweave.file_manager import FileManager
from ritual_arweave.types import ArRepoId, Tags
from ritual_arweave.utils import edge_unix_ts, get_sha256_digest
from ritual_arweave.version import VERSION

log = logging.getLogger(__name__)


class NotFinalizedException(Exception):
    """Exception raised when a transaction is not yet finalized."""

    pass


class UploadArweaveRepoResult(BaseModel):
    """Model to represent the result of a repository upload."""

    repo_id: ArRepoId
    transaction_id: str
    manifest_url: str


class RepoManager(FileManager):
    def download_artifact_file(
        self,
        repo_id: Union[ArRepoId, str],
        file_name: str,
        version: Optional[str] = None,
        force_download: bool = False,
        base_path: str | Path = ".",
    ) -> Path:
        """Downloads a specific artifact from Arweave.

        Args:
            repo_id (Union[ArRepoId, str]): id of the repo, if provided as a string, the
                format must be of the form `owner`/`name`. Where `owner` is the wallet
                address of the uploader and `name` is the repository's name.
            file_name (str): name of artifact
            version (Optional[str], optional): Version of file. Defaults to None.
                If none specified, will fetch the latest version.
            force_download (bool, optional): If True, will download file even if it
                already exists at that path. Defaults to False.
            base_path (str, optional): path to download file to. Defaults to "".

        Raises:
            ValueError: if wallet file path is not specified or wallet file is not found.

        Returns:
            Path: path to downloaded file
        """
        if isinstance(repo_id, str):
            repo_id = ArRepoId.from_str(repo_id)

        base = Path(base_path)
        os.makedirs(base, exist_ok=True)
        owners = [repo_id.owner]

        file_version_str = (
            ""
            if not version
            else """
            {
                name: "File-Version",
                values: ["%s"]
            },
        """
            % version
        )
        query_str = """
        query {
            transactions(
                sort:HEIGHT_DESC,
                owners: %s,
                tags: [
                    {
                        name: "App-Name",
                        values: ["Ritual"]
                    },
                    %s
                    {
                        name: "File-Name",
                        values: ["%s"]
                    },
                    {
                        name: "Repo-Name",
                        values: ["%s"]
                    }
                ])
            {
                edges {
                    node {
                        block {
                            id
                            timestamp
                        }
                        id
                        owner {
                            address
                        }
                        tags {
                            name
                            value
                        }
                    }
                }
            }
        }
        """ % (
            json.dumps(owners),
            file_version_str,
            file_name,
            repo_id.name,
        )
        log.debug(query_str)

        file_path: Path = base.joinpath(file_name)

        res = self.peer.graphql(query_str)
        transactions = res["data"]["transactions"]["edges"]
        transactions.sort(reverse=True, key=edge_unix_ts)

        if len(transactions) == 0:
            raise ValueError(
                f"Could not find any matching artifacts for: "
                f"({repo_id}, {file_name}, {version or 'latest'})"
            )

        transaction = transactions[0]

        tx_metadata: dict[str, Any] = transaction["node"]

        tx_id = tx_metadata["id"]

        if force_download or not self.file_exists(str(file_path), tx_id):
            log.info(f"downloading {tx_metadata}")
            return self.download(str(file_path), tx_id)
        else:
            log.info(f"not downloading {tx_metadata} because it already exists")
            return Path(file_path)

    def upload_repo(
        self,
        name: str,
        path: Path | str,
        version_mapping_file: Optional[str] = None,
        version_mapping: Optional[Dict[str, str]] = None,
        extra_file_tags: Optional[Dict[str, Tags]] = None,
    ) -> UploadArweaveRepoResult:
        """
        Uploads a repo directory to Arweave. For every repository upload, a manifest
        mapping is created.

        Args:
            name (str): Name of the repository. Once uploaded, the repo will be
                accessible via the repo Id: `owner/name`. Where `owner` is the wallet
                address of the uploader and `name` is the repository's name.
            path (Path | str): Path to the directory containing the repository files.
            version_mapping_file (str): Path to a json dict file mapping file names to
                specific versions. If a specific mapping is found, the File-Version
                attribute is tagged with the value. This is to facilitate uploading and
                downloading version specific files.
            version_mapping (dict[str, str]): Dictionary mapping file names to specific
                versions. If a specific mapping is found, the File-Version attribute is
                tagged with the value. This is to facilitate uploading and downloading
                version specific files. If provided, this will override the version_file.
            extra_file_tags (dict[str, Tags]): Dictionary mapping file names to
                additional tags to be added to the file. This is useful for adding
                additional metadata to each file.

        Raises:
            ValueError: if wallet file path is not specified or wallet file is not found.

        Returns:
            UploadArweaveRepoResult: Result of the upload containing repo_id,
            transaction_id, and manifest_url.
        """

        # path to load files from
        _path: Path = Path(path)

        # load all sub-paths in this path
        p = _path.glob("**/*")

        # get timestamp to tag files with
        timestamp = time.time()

        # filter out simlinks and non-files
        files = [x for x in p if x.is_file()]

        _version_mapping = {}
        if version_mapping:
            _version_mapping = version_mapping
        elif version_mapping_file:
            with open(version_mapping_file, "r") as vf:
                _version_mapping = json.load(vf)
        self.logger(f"using mapping {_version_mapping}")

        # keep track of entries via a manifest
        manifest_dict: dict[str, str] = {}

        ritual_tags: Tags = {
            "App-Name": "Ritual",
            "App-Version": VERSION,
            "Unix-Time": str(timestamp),
            "Repo-Name": str(name),
        }

        for f in files:
            rel_path = os.path.relpath(f, _path)

            self.logger(f"looking at {f} ({rel_path}) Size: {os.path.getsize(f)}")

            content_type = (
                guess
                if (guess := mimetypes.guess_type(f)[0])
                else "application/octet-stream"
            )
            file_extra_tags = (
                extra_file_tags.get(rel_path, {}) if extra_file_tags else {}
            )

            tags_dict: Tags = {
                **file_extra_tags,
                "Content-Type": content_type,
                "File-Version": _version_mapping.get(str(rel_path), "0.0.0"),
                "File-Name": rel_path,
                "File-SHA256": get_sha256_digest(str(f)),
                **ritual_tags,
            }

            self.logger(f"uploading: {f} with tags: {tags_dict}")

            tx = self.upload(f, tags_dict)

            # we are done uploading the whole file, keep track if filename -> tx.id
            manifest_dict[str(os.path.relpath(f, _path))] = tx.id
            self.logger(f"uploaded file {f} with id {tx.id} and tags {tags_dict}")

        # we create a manifest of all the files to their transactions
        m = Manifest(manifest_dict)

        # upload the manifest
        t = Transaction(self.wallet, peer=self.peer, data=m.tobytes())

        t.add_tags(
            {
                "Content-Type": "application/x.arweave-manifest+json",
                "Type": "manifest",
                **ritual_tags,
            }
        )

        t.sign()
        t.send()

        self.logger(f"uploaded manifest with tx id {t.id}")

        return UploadArweaveRepoResult(
            repo_id=ArRepoId(owner=self.wallet.address, name=name),
            transaction_id=t.id,
            manifest_url=f"{t.api_url}/{t.id}",
        )

    def download_file_in_repo(
        self,
        repo_id: Union[ArRepoId, str],
        file_name: str,
        base_path: str | Path = Path("."),
    ) -> Path:
        """
        Downloads a file from a repo on Arweave.

        Args:
            repo_id: Arweave repo id, in the format of `owner`/`name` where `owner` is
                the wallet address of the uploader and `name` is the repository's name.
            file_name: name of the file to download.
            base_path: path to download the file to.

        Returns:
            path to the downloaded file.

        """

        base_path = Path(base_path)
        manifest = self.get_repo_manifest(repo_id)
        file_tid = manifest["paths"][file_name]["id"]
        return self.download(base_path / file_name, file_tid)

    def get_repo_manifest(self, repo_id: Union[ArRepoId, str]) -> dict[str, Any]:
        """
        Get the manifest of a repo from Arweave.
        Args:
            repo_id: Arweave repo id, in the format of `owner`/`name` where `owner` is
                the wallet address of the uploader and `name` is the repository's name.

        Returns:
            dict: manifest of the repo.

        """

        if isinstance(repo_id, str):
            repo_id = ArRepoId.from_str(repo_id)
        owners = [repo_id.owner]
        query_str = """
        query {
            transactions(
                sort:HEIGHT_DESC,
                owners: %s,
                tags: [
                    {
                        name: "App-Name",
                        values: ["Ritual"]
                    },
                    {
                        name: "Repo-Name",
                        values: ["%s"]
                    },
                    {
                        name: "Type",
                        values: ["manifest"]
                    }
                ]
            )
            {
                edges {
                    node {
                        block {
                            id
                            timestamp
                        }
                        id
                        owner {
                            address
                        }
                        tags {
                            name
                            value
                        }
                    }
                }
            }
        }
        """ % (
            json.dumps(owners),
            repo_id.name,
        )

        # self.logger(query_str)
        log.info("getting first query")
        try:
            res = self.peer.graphql(query_str)
        except HTTPError as e:
            raise ValueError(f"Error querying repo manifests: {e}")
        log.info("done getting first query")

        # get latest Manifest

        manifests = res["data"]["transactions"]["edges"]
        manifests.sort(reverse=True, key=edge_unix_ts)
        self.logger(f"found {len(manifests)} manifests for {repo_id}")

        if len(manifests) == 0:
            raise ValueError("Could not find any matching repo manifests from query.")

        manifest = manifests[0]

        tx_id = manifest["node"]["id"]

        # download manifest data
        self.logger(f"found manifest {manifest}")

        log.info("getting manifest")
        try:
            m = json.loads(self.peer.tx_data(tx_id))
        except Exception as e:
            log.info("Exception while getting manifest")
            r = requests.get(f"{self.peer.api_url}/tx/{tx_id}")
            if r.status_code == 202:
                raise NotFinalizedException(
                    f"Manifest {tx_id} is still being mined. Please try again later."
                )
            raise ValueError(f"Error fetching manifest data: {e}")
        log.info("done getting manifest")

        self.logger(f"loaded manifest {m}")
        return cast(dict[str, Any], m)

    def download_repo(
        self,
        repo_id: Union[ArRepoId, str],
        base_path: str | Path = Path("."),
        force_download: bool = False,
    ) -> List[Path]:
        """Downloads a repo from Arweave to a given directory.

        Args:
            repo_id (Union[ArRepoId, str]): id of the repo, if provided as a string, the
                format must be of the form `owner`/`name`. Where `owner` is the wallet
                address of the uploader and `name` is the respository's name.
            base_path (str | Path, optional): path to download files to. Defaults to ".".
            force_download (bool, optional): If True, will download files even if they
                already exist. Defaults to False.

        Raises:
            ValueError: if wallet file path is not specified or wallet file is not found.
            ValueError: if matching repo manifest not found
            NotFinalizedException: if the manifest is still being mined

        Returns:
            list[str]: downloaded file paths
        """

        manifest = self.get_repo_manifest(repo_id)

        base = Path(base_path)
        base.mkdir(parents=True, exist_ok=True)

        paths = []

        with ThreadPoolExecutor() as executor:
            for pathname, tid in manifest["paths"].items():
                file_tid: str = tid["id"]
                joined_path: Path = base.joinpath(pathname)

                # check if file exists
                if force_download or not self.file_exists(str(joined_path), file_tid):
                    st = time.time()
                    self.logger(f"downloading file {pathname} for {file_tid}")
                    paths.append(
                        executor.submit(self.download, str(joined_path), file_tid)
                    )
                    self.logger(f"downloaded in {time.time() - st} sec: {joined_path}")
                else:
                    self.logger(
                        f"Path {joined_path} already exists and will not be downloaded. "
                        + "Please remove it or use --force_download flag."
                    )

        return [p.result() for p in paths]
