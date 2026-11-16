"""The corpus: the most-downloaded Python packages and their PyPI records. Each record gives
text (summary and description) and relationships (dependencies, maintainer, license), so
questions can need two or three hops. Downloaded on first use into GRAPHRAG_DATA (default
~/.cache/graphrag), which then pins the corpus to the day it was fetched."""
import hashlib
import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOP = "https://raw.githubusercontent.com/hugovk/top-pypi-packages/main/top-pypi-packages.min.json"
PYPI = "https://pypi.org/pypi/{}/json"
# The sentence embedder: bge-small-en-v1.5 (BAAI, MIT) as the ONNX export fastembed uses, from
# Qdrant's Hugging Face repository at a pinned commit. Each file is checked against its SHA-256.
# (It used to come as one tarball from Qdrant's storage bucket, which no longer allows downloads.)
HF_FILE = "https://huggingface.co/{repo}/resolve/{rev}/{name}"
EMBEDDER = {"repo": "Qdrant/bge-small-en-v1.5-onnx-Q", "rev": "aa8f8b060edb00e03bfdd08813a2949946c8ba55",
            "folder": "fast-bge-small-en-v1.5",
            "files": {"tokenizer.json": "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66",
                      "model_optimized.onnx": "51f1bd0addd6e859e42c2c8021a5e5461385bb676a649f4b269aa445449f2431"}}


def cache_dir():
    path = Path(os.environ.get("GRAPHRAG_DATA", Path.home() / ".cache" / "graphrag"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch(url, path, tries=4):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(url, timeout=120) as r:
                    body = r.read()
                break
            except OSError:
                if attempt == tries - 1:
                    raise
                time.sleep(2 ** attempt)
        path.write_bytes(body)
    return path


def records(n=500):
    """[PyPI info dicts] for the n most-downloaded packages (those whose record loads)."""
    top = json.loads(fetch(TOP, cache_dir() / "top.json").read_text())["rows"][:n]
    def one(name):
        try:
            return json.loads(fetch(PYPI.format(name), cache_dir() / "pypi" / f"{name}.json").read_text())["info"]
        except (OSError, ValueError):
            return None
    with ThreadPoolExecutor(8) as pool:
        return [r for r in pool.map(one, [row["project"] for row in top]) if r]


def embedder_dir():
    return model_files(EMBEDDER)

def model_files(spec, tries=4):
    """The model's files in the cache, downloading any that are missing or do not match their SHA-256."""
    target = cache_dir() / spec["folder"]
    target.mkdir(parents=True, exist_ok=True)
    for name, sha in spec["files"].items():
        path = target / name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha:
            continue
        url = HF_FILE.format(repo=spec["repo"], rev=spec["rev"], name=name)
        for attempt in range(tries):
            try:
                with urllib.request.urlopen(url, timeout=300) as r:
                    body = r.read()
                break
            except OSError:
                if attempt == tries - 1:
                    raise
                time.sleep(2 ** attempt)
        if hashlib.sha256(body).hexdigest() != sha:
            raise RuntimeError(f"{spec['repo']}/{name}: the download does not match its pinned SHA-256")
        path.write_bytes(body)
    return target
