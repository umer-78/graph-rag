"""python -m graphrag.demo   write the live demo's data (docs/data.json): the knowledge graph's packages, their
aliases (in the order the retriever tries them), dependency and licence edges (in the order the graph
returns them) and the bench's 360 questions with results/summary.json. Maintainer names are left out."""
import json
from pathlib import Path

from . import data
from .graph import Graph

ROOT = Path(__file__).resolve().parent.parent


def build(out=ROOT / "docs"):
    summary = json.loads((ROOT / "results" / "summary.json").read_text())
    g = Graph()
    g.ingest(data.records())
    packages = [r[0] for r in g.db.execute("SELECT id FROM nodes WHERE type = 'Package' ORDER BY id")]
    aliases = sorted(g.db.execute("SELECT alias, node FROM aliases WHERE node LIKE 'package:%'").fetchall(), key=lambda r: -len(r[0]))
    nodes = {p: {"name": g.name(p), "deps": g.out(p, "DEPENDS_ON"), "dependents": g.into(p, "DEPENDS_ON"),
                 "licences": [g.name(x) for x in g.out(p, "LICENSED_AS")]} for p in packages}
    out.mkdir(exist_ok=True)
    (out / "data.json").write_text(json.dumps({"summary": {k: v for k, v in summary.items() if k != "questions"},
                                               "questions": summary["questions"], "aliases": aliases, "nodes": nodes}))
    print(f"wrote {out / 'data.json'}: {len(nodes)} packages, {len(aliases)} aliases")


if __name__ == "__main__":
    build()
