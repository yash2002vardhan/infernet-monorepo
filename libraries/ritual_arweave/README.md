# Ritual Arweave

This is a library as well as a CLI tool that allows uploading and downloading data to
and from the Arweave network. Users can:

1. Upload/Download individual files from & to the Arweave network.
2. Upload/Download repositories to & from the Arweave network. Each repository is a
   directory containing multiple files (artifacts). These are commonly used in
   `infernet-ml` to store and retrieve models.

For more information, refer to the [Ritual Arweave documentation]
(https://ritual-arweave.docs.ritual.net/).

## Installation

**Via pip:**

```
pip install ritual-arweave
```

**Via UV:**

```
uv pip install ritual-arweave
```

## Usage

**CLI:**

```
ritual-arweave --help
```

## Developing

You might find yourself iterating on both `ritual_arweave` & `ritual_pyarweave` when
doing development. To make sure that the correct modules are imported, set the
`PYTHONPATH` environment variable like so:

```
export PYTHONPATH="libraries/ritual_arweave/src:libraries/ritual_pyarweave/src"
```
