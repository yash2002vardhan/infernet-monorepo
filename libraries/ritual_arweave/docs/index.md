# Ritual Arweave Documentation

## Overview

Ritual Arweave is a Python library and CLI tool designed to facilitate the uploading and downloading of data to and from the Arweave network. This library supports both individual file operations and repository-level operations, making it versatile for various use cases, including model storage and retrieval in machine learning projects.

## Key Features

- Upload and Download Individual Files: Easily manage single files on the Arweave network.
- Upload and Download Repositories: Handle entire directories containing multiple files, ideal for managing grouped artifacts.
- Version mapping: Enables versioning for files when uploading/downloading repositories via tags.
- CLI Support: Use command-line interface for streamlined operations without writing additional code.

## Main Components

- [FileManager](../reference/ritual_arweave/file_manager/?h=filemanage#ritual_arweave.file_manager.FileManager): Handles the uploading and downloading of individual files.
- [RepoManager](../reference/ritual_arweave/repo_manager/?h=repomana#ritual_arweave.repo_manager.RepoManager): Manages the uploading and downloading of repositories, including handling manifest files and version mappings.

## 🎉 What's new in `ritual-arweave 0.2.0`?

The following new features have been added in `ritual-arweave 0.2.0`:

1. Progress bar support for file uploads and downloads.
2. Parallel upload/download support for [very large (> 1GB) files](./quickstart/#large-file-uploadsdownloads).
3. Support for [generic blobs](./quickstart/#generic-blob-uploaddownload), as well as [dictionaries](./quickstart/#dictionary-uploaddownload).
