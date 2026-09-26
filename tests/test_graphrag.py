import numpy as np

from graphrag.graph import Graph, dependency_names, license_of, package_id
from graphrag.retrieve import Retriever

INFOS = [
    {"name": "Requests", "summary": "HTTP for humans", "description": "Send HTTP requests easily.", "license": "Apache 2.0",
     "author": "Kenneth Reitz", "requires_dist": ["charset_normalizer<4", "urllib3>=1.21", "PySocks; extra == 'socks'"]},
    {"name": "urllib3", "summary": "HTTP client", "description": "Connection pooling.", "license_expression": "MIT",
     "author": "Andrey Petrov", "requires_dist": []},
    {"name": "charset-normalizer", "summary": "Charset detection", "description": "Detects encodings.", "license": "",
     "classifiers": ["License :: OSI Approved :: MIT License"], "author": "Ahmed Tahri", "requires_dist": []},
    {"name": "httpx", "summary": "Async HTTP", "description": "Next generation HTTP client.", "license": "BSD",
     "author": "Tom Christie", "requires_dist": ["urllib3"]},
]


class FakeEmbedder:
    """Bag-of-letters vectors: enough to test the plumbing without a model."""
    def encode(self, texts):
        v = np.array([[t.lower().count(c) for c in "abcdefghijklmnopqrstuvwxyz"] for t in texts], float) + 1e-9
        return v / np.linalg.norm(v, axis=1, keepdims=True)

    def cached(self, texts):
        return self.encode(texts)


def test_resolution_licences_and_idempotent_ingest():
    assert package_id("Charset_Normalizer") == package_id("charset-normalizer")
    assert dependency_names(INFOS[0]["requires_dist"]) == ["charset_normalizer", "urllib3"]
    assert [license_of(i) for i in INFOS] == ["Apache-2.0", "MIT", "MIT", "BSD"]
    g = Graph()
    stats = g.ingest(INFOS)
    assert stats == {"mentions": 3, "resolved": 3}
    before = g.counts()
    g.ingest(INFOS)
    assert g.counts() == before and Graph().ingest(INFOS, normalise=False)["resolved"] == 2


def test_router_direction_and_graph_answers():
    g = Graph()
    g.ingest(INFOS)
    r = Retriever(g, FakeEmbedder())
    assert r.route("What does requests depend on?") == ("graph", "deps")
    assert r.route("Which packages depend on urllib3?") == ("graph", "dependents")
    assert r.route("What do requests and httpx both depend on?") == ("graph", "shared")
    assert r.route("What is urllib3 used for?") == ("vector", "fact")
    assert set(r.retrieve("Which packages depend on urllib3?")) == {package_id("requests"), package_id("httpx")}
    licences = r.answer("Under which licenses are the dependencies of requests released?")
    assert {(a, b) for a, b, _ in licences} == {("charset-normalizer", "MIT"), ("urllib3", "MIT")}
