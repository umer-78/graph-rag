"""The corpus: the most-downloaded Python packages and their PyPI records. Each record gives
text (summary and description) and relationships (dependencies, maintainer, license), so
questions can need two or three hops. Downloaded on first use into GRAPHRAG_DATA (default
~/.cache/graphrag), which then pins the corpus to the day it was fetched."""
import hashlib
import json
import os
import tarfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TOP = "https://raw.githubusercontent.com/hugovk/top-pypi-packages/main/top-pypi-packages.min.json"
PYPI = "https://pypi.org/pypi/{}/json"
EMBEDDER = ("https://storage.googleapis.com/qdrant-fastembed/fast-bge-small-en-v1.5.tar.gz",
            "3858004b3822f64f940280874b8f2d2dc25b34a4f3eb3cdf617bdceeb21ed9ed")


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
    url, sha = EMBEDDER
    target = cache_dir() / "fast-bge-small-en-v1.5"
    if not (target / "tokenizer.json").exists():
        archive = fetch(url, cache_dir() / "fast-bge-small-en-v1.5.tar.gz")
        if hashlib.sha256(archive.read_bytes()).hexdigest() != sha:
            raise RuntimeError("the embedder download does not match its pinned SHA-256")
        with tarfile.open(archive) as tar:
            tar.extractall(cache_dir(), members=[m for m in tar.getmembers() if not Path(m.name).name.startswith("._")],
                           filter="data")
    return target
