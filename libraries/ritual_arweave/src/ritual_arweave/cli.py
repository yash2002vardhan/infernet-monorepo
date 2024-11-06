"""
Script containing a command line interface to upload and download repositories from/to
arweave. This file is a thin wrapper around RepoManager & FileManager classes to
facilitate usage of the repo upload and download functions from the command line.

This CLI is commonly used to upload and download model files from/to arweave, similar
to how models are handled in huggingface hub.
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

import click
from ritual_arweave.file_manager import FileManager
from ritual_arweave.repo_manager import NotFinalizedException, RepoManager
from ritual_arweave.utils import PUBLIC_GATEWAYS

DEFAULT_GATEWAYS = ",".join(PUBLIC_GATEWAYS)


# suppress ritual-pyarweave error logs
logging.getLogger("ar.peer").setLevel(logging.ERROR)


@click.group()
def cli() -> None:
    pass


GenericCallable = Callable[..., Any]


# Define reusable options as functions
def repo_name_option(f: GenericCallable) -> GenericCallable:
    return click.option(
        "--repo-name",
        type=str,
        required=True,
        help="Repo name to upload. Once you upload this repo, it can be downloaded "
        "using the repo id: `owner/repo_name` where `owner` is the wallet address"
        "that uploaded the repo.",
    )(f)


def repo_id_option(f: GenericCallable) -> GenericCallable:
    return click.option(
        "--repo-id",
        type=str,
        required=True,
        help="Repo ID to upload or download. This is a unique identifier for the repo,"
        " and is in the format: `owner/repo_name` where `owner` is the wallet "
        "address that uploaded the repo, and `repo_name` is the name of the "
        "repo.",
    )(f)


def wallet_option(f: GenericCallable) -> GenericCallable:
    return click.option(
        "--wallet",
        type=str,
        required=False,
        default="wallet.json",
        help="Path to wallet file, default is `wallet.json`",
    )(f)


def gateways_option(f: GenericCallable) -> GenericCallable:
    return click.option(
        "--gateways",
        type=str,
        required=False,
        default=DEFAULT_GATEWAYS,  # Assuming a default value is set
        help=f"Comma separated list of Arweave gateways, default is "
        f"{DEFAULT_GATEWAYS}",
    )(f)


def max_upload_size_option(f: GenericCallable) -> GenericCallable:
    return click.option(
        "--max-upload-size",
        type=int,
        required=False,
        default=None,  # Assuming a default value is set
        help="If a file is too large to be uploaded in a single transaction, it will be "
        "split into chunks of this size. Default is 5MB",
    )(f)


def show_progress_option(f: GenericCallable) -> GenericCallable:
    return click.option(
        "--show-progress",
        type=bool,
        required=False,
        default=True,
        help="If set, it will show progress bar while uploading files",
    )(f)


@click.option(
    "--repo-dir",
    required=True,
    type=click.Path(exists=True, readable=True),
    help="Enter repo directory",
)
@click.option(
    "--version-file",
    required=False,
    default=None,
    type=str,
    help="enter version mapping json of repo files to upload",
)
@repo_name_option
@wallet_option
@show_progress_option
@gateways_option
@cli.command(
    name="upload-repo",
)
def upload_repo(
    repo_name: str,
    repo_dir: str,
    version_file: Optional[str],
    wallet: str,
    show_progress: bool,
    gateways: str,
) -> None:
    """
    Uploads a repo to Arweave using the specified repo name & repo directory.

    Parameters:
        repo_name: Name of the repo to upload.
        repo_dir: Path to the repo directory.
        version_file (optional): Path to the version mapping file. This is a json file
            that maps repo filenames to their corresponding versions.
        wallet (optional): Path to the wallet file. Default is `wallet.json`.
        show_progress: If set, it will show progress bar while uploading files.
        gateways (optional): Commas separated list of Arweave gateways.


    Examples:

    To upload a repo with ID <repo-id> from the directory <repo-dir>:

    ritual-arweave upload-repo --repo-name <repo-name> --repo-dir <repo-dir>

    To upload a repo with ID <repo-id> from the directory <repo-dir> and version
    mapping file <version-file>:

    ritual-arweave upload-repo --repo-name <repo-name> --repo-dir <repo-dir> \
        --version-file <version-file>

    To upload a repo with ID <repo-id> from the directory <repo-dir> and
    wallet <wallet>:

    ritual-arweave upload-repo --repo-name <repo-name> --repo-dir <repo-dir> \
        --wallet <wallet>

    """
    r = RepoManager(
        gateways=gateways.split(","),
        wallet_path=wallet,
        show_progress_bar=show_progress,
    ).upload_repo(name=repo_name, path=repo_dir, version_mapping_file=version_file)
    click.echo(
        f"uploaded repo: {r}"
        f"\n\tyou can download it using the repo id: "
        f"`{r.repo_id.owner}/{r.repo_id.name}`"
    )


@click.option(
    "--base-path",
    type=str,
    default=".",
    required=False,
    help="enter base path to save repo files, defaults to the current directory.",
)
@click.option(
    "--force-download",
    is_flag=True,
    default=False,
    required=False,
    help="If set, it will override the existing repo files if they exist",
)
@repo_id_option
@show_progress_option
@gateways_option
@cli.command(
    name="download-repo",
)
def download_repo(
    repo_id: str,
    base_path: str = ".",
    force_download: bool = False,
    show_progress: bool = True,
    gateways: str = DEFAULT_GATEWAYS,
) -> None:
    """
    Downloads a repo from Arweave using the specified repo ID, and
    API URL. Optionally, you can specify multiple owners and a
    base path where the repo files will be saved.
    Use the --force-download flag to override existing files.

    Parameters:
        repo_id: The ID of the repository to download.
        base_path: The base path to save the repo files. Defaults to the current
            directory.
        force_download: If set, it will override the existing repo files if they exist.
        show_progress: If set, it will show progress bar while downloading files.
        gateways: Commas separated list of Arweave gateways.

    Examples:

    To download a repo with ID <repo-id> and owner <owner-address>:

    ritual-arweave download-repo --repo-id <repo-id> --owner <owner-address>

    To download a repo with ID <repo-id> and owner <owner-address> and save the repo
    files to <path-to-save-repo>:

    ritual-arweave download-repo --repo-id <repo-id> --base-path <path-to-save-repo>
    """

    try:
        files = RepoManager(
            gateways=gateways.split(","), show_progress_bar=show_progress
        ).download_repo(
            repo_id,
            base_path,
            force_download,
        )
    except NotFinalizedException:
        click.echo(
            f"Repo with ID {repo_id} is not finalized yet. Please retry "
            f"in a few minutes."
        )
        return

    click.echo(f"downloaded files: {files}")


@click.option(
    "--file-path",
    type=str,
    help="Path to the file to download",
)
@click.option(
    "--tx-id",
    type=str,
    help="Transaction id of the file to download",
)
@show_progress_option
@gateways_option
@cli.command(
    name="download-file",
)
def download_file(
    file_path: str,
    tx_id: str,
    gateways: str = DEFAULT_GATEWAYS,
    show_progress: bool = True,
) -> None:
    """
    Downloads a file from Arweave using the transaction ID.

    Parameters:
        file_path: Path to the file to download.
        tx_id: Transaction ID of the file to download.
        gateways: Comma separated list of Arweave gateways.
        show_progress: If set to false, it will not show the progress bar while

    Examples:

    To download a file with transaction id <tx-id> to the path <file-path>:

    ritual-arweave download-file --file-path <file-path> --tx-id <tx-id>
    """
    fm = FileManager(gateways=gateways.split(","), show_progress_bar=show_progress)
    fm.download(file_path, tx_id)


@click.option(
    "--file-path",
    type=str,
    help="Path to the file to upload",
    required=True,
)
@click.option(
    "--tags",
    type=str,
    required=False,
    default="{}",
    help="Dictionary of tags to attach to the file. Must be a JSON string.",
)
@max_upload_size_option
@show_progress_option
@gateways_option
@wallet_option
@cli.command(
    name="upload-file",
)
def upload_file(
    file_path: str,
    max_upload_size: int,
    show_progress: bool = True,
    gateways: str = ",".join(DEFAULT_GATEWAYS),
    wallet: str = "wallet.json",
    tags: str = "{}",
) -> None:
    """
    Uploads a file to Arweave.

    Parameters:
        file_path: Path to the file to upload.
        max_upload_size: For large files, the file will be split into chunks of this
        size.
        gateways: Comma separated list of Arweave gateways.
        wallet: Path to the wallet file. Default is `wallet.json`.
        tags: Dictionary of tags to attach to the file. Must be a JSON string.

    Examples:

    To upload a file with path <file-path>:

    ritual-arweave upload-file --file-path <file-path>
    """
    fm = FileManager(
        gateways=gateways.split(","),
        wallet_path=wallet,
        max_upload_size=max_upload_size,
        show_progress_bar=show_progress,
    )
    tx = fm.upload(Path(file_path), tags_dict=json.loads(tags))
    click.echo(f"uploaded file: {tx.id}")
