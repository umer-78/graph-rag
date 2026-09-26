"""Questions generated from the graph, with the packages each needs retrieved as the gold set.

Six kinds, several phrasings each: a single fact about a named package (the vector path's
home ground), its dependencies, what depends on it, its dependencies' licences, their
maintainers, and what two packages share. The last five need hops the question never names:
the text of `requests` does not say who maintains `urllib3`. Recall@10 is the share of the
gold packages retrieved (out of at most 10).
"""
import json
import random
from pathlib import Path

import numpy as np

from . import data
from .embed import Embedder
from .graph import Graph
from .retrieve import Retriever

RESULTS = Path(__file__).resolve().parent.parent / "results"
TEMPLATES = {
    "fact": ["What is {a} used for?", "What does the {a} package do?"],
    "deps": ["What does {a} depend on?", "Which packages does {a} need at runtime?", "What are the dependencies of {a}?"],
    "dependents": ["Which packages depend on {a}?", "What in this set requires {a}?", "Which libraries are built on {a}?"],
    "dep_licenses": ["Under which licenses are the dependencies of {a} released?", "What licences do the packages {a} needs use?"],
    "dep_maintainers": ["Who maintains the packages that {a} depends on?", "Who are the authors of {a}'s dependencies?"],
    "shared": ["Which dependencies do {a} and {b} have in common?", "What do {a} and {b} both depend on?"],
}


def questions(g, per_kind=60, seed=0):
    rng = random.Random(seed)
    pkgs = [r[0] for r in g.db.execute("SELECT id FROM nodes WHERE type = 'Package' ORDER BY id")]
    deps = {p: sorted(set(g.out(p, "DEPENDS_ON"))) for p in pkgs}
    users = {p: sorted(set(g.into(p, "DEPENDS_ON"))) for p in pkgs}
    out = []
    pools = {"fact": [(p,) for p in pkgs], "deps": [(p,) for p in pkgs if len(deps[p]) >= 2],
             "dependents": [(p,) for p in pkgs if len(users[p]) >= 2],
             "shared": [(a, b) for a in pkgs for b in pkgs if a < b and len(set(deps[a]) & set(deps[b])) >= 1]}
    pools["dep_licenses"] = pools["dep_maintainers"] = pools["deps"]
    for kind, templates in TEMPLATES.items():
        for args in rng.sample(pools[kind], min(per_kind, len(pools[kind]))):
            text = rng.choice(templates).format(a=g.name(args[0]), b=g.name(args[-1]))
            gold = {"fact": {args[0]}, "dependents": set(users[args[0]]), "shared": set(args) | (set(deps[args[0]]) & set(deps[args[-1]]))
                    }.get(kind, set(deps[args[0]]))
            out.append({"kind": kind, "question": text, "gold": sorted(gold)})
    return out


def recall(got, gold, k=10):
    return len(set(got[:k]) & set(gold)) / min(len(gold), k)


def bench():
    infos = data.records()
    g = Graph()
    resolved = g.ingest(infos)
    before = g.counts()
    g.ingest(infos)                                          # idempotence: a second ingest adds nothing
    idempotent = g.counts() == before
    raw = Graph().ingest(infos, normalise=False)
    r = Retriever(g, Embedder())
    qs = questions(g)
    rows = []
    for q in qs:
        path, intent = r.route(q["question"])
        rows.append({**q, "routed_intent": intent,
                     "vector": recall(r.retrieve(q["question"], path="vector"), q["gold"]),
                     "routed": recall(r.retrieve(q["question"]), q["gold"]),
                     "both": recall(r.retrieve(q["question"], path="both"), q["gold"])})
    kinds = list(TEMPLATES)
    lines = [f"{len(infos)} packages; graph: {g.counts()}.", "",
             f"Entity resolution: {resolved['resolved']} of {resolved['mentions']} runtime-dependency mentions resolve to a "
             f"package in the corpus with PEP 503 names; {raw['resolved']} with names taken as written. "
             f"Ingesting twice leaves the graph unchanged: {idempotent}.", "",
             "| Question kind | Questions | Router correct | Recall@10: vector | Recall@10: routed | Recall@10: both merged |",
             "|---|---|---|---|---|---|"]
    for kind in kinds + ["all"]:
        rs = [x for x in rows if kind in ("all", x["kind"])]
        lines.append(f"| {kind} | {len(rs)} | {100 * np.mean([x['routed_intent'] == x['kind'] for x in rs]):.0f}% | "
                     + " | ".join(f"{100 * np.mean([x[p] for x in rs]):.1f}%" for p in ("vector", "routed", "both")) + " |")
    example = next(q for q in qs if q["kind"] == "dep_licenses")
    lines += ["", f"Answer from the graph for \"{example['question']}\" (package, licence, source chunk):", ""]
    lines += [f"- {a} — {b} (`{c}`)" for a, b, c in r.answer(example["question"])]
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "bench.md").write_text("\n".join(lines) + "\n")
    (RESULTS / "summary.json").write_text(json.dumps({"counts": g.counts(), "resolution": resolved, "raw_resolution": raw,
                                                      "questions": rows}, indent=1))
    return "\n".join(lines)
