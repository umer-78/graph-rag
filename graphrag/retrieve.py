"""Two retrieval paths over the same chunk ids, and a router between them.

Vector: the question's embedding against every chunk's. Graph: find the packages the
question names (by alias), then walk the relationship the question asks about. The router
is a small rule set; when it is unsure it runs both and merges.
"""
import re

import numpy as np

VERB = re.compile(r"\b(depend(?:s|ed)? on|rel(?:y|ies) on|requires?|needs?|pulls? in|built on|dependenc(?:y|ies))\b")


class Retriever:
    def __init__(self, graph, embedder):
        self.g, self.embedder = graph, embedder
        rows = self.g.db.execute("SELECT id, node, text FROM chunks ORDER BY id").fetchall()
        self.chunk_ids, self.chunk_node = [r[0] for r in rows], [r[1] for r in rows]
        self.vectors = embedder.cached([r[2] for r in rows])
        self.aliases = sorted(self.g.db.execute("SELECT alias, node FROM aliases WHERE node LIKE 'package:%'").fetchall(),
                              key=lambda r: -len(r[0]))

    def entities(self, question, positions=False):
        """Packages the question names, longest alias first so `google-auth` wins over `google`."""
        found, text = [], question.lower()
        for alias, node in self.aliases:
            m = re.search(rf"(?<![\w-]){re.escape(alias)}(?![\w-])", text) if len(alias) > 2 else None
            if m and node not in [n for n, _ in found]:
                found.append((node, m.start()))
                text = text[:m.start()] + " " * len(alias) + text[m.end():]
        found.sort(key=lambda x: x[1])
        return found if positions else [n for n, _ in found]

    def route(self, question):
        """(path, intent). Graph when the question asks for a relationship of packages it names:
        what they share, their dependencies' licences or maintainers, what they depend on, or,
        when the named package comes after the verb, what depends on it. Vector otherwise."""
        named, q = self.entities(question, positions=True), question.lower()
        verb = VERB.search(q)
        if not named:
            return "vector", "fact"
        if len(named) >= 2 and re.search(r"\b(in common|share[sd]?|both)\b", q):
            return "graph", "shared"
        if verb and re.search(r"licen[cs]e", q):
            return "graph", "dep_licenses"
        if verb and re.search(r"\b(maintain\w*|authors?|wrote)\b", q):
            return "graph", "dep_maintainers"
        if verb:
            after = named[0][1] > verb.start() and not verb.group(1).startswith("dependenc")
            return "graph", "dependents" if after else "deps"
        return "vector", "fact"

    def vector(self, question, k=10):
        q = self.embedder.encode([question])[0]
        order = np.argsort(-(self.vectors @ q))
        out = []
        for i in order:
            if self.chunk_node[i] not in out:
                out.append(self.chunk_node[i])
            if len(out) == k:
                break
        return out

    def graph(self, question, intent, k=10):
        names = self.entities(question)
        if intent == "shared" and len(names) >= 2:
            common = set(self.g.out(names[0], "DEPENDS_ON")) & set(self.g.out(names[1], "DEPENDS_ON"))
            return (names[:2] + sorted(common))[:k]
        if intent == "dependents":
            return [n for p in names for n in self.g.into(p, "DEPENDS_ON")][:k]
        deps = [d for p in names for d in self.g.out(p, "DEPENDS_ON")]
        return (deps if intent in ("deps", "dep_licenses", "dep_maintainers") else names)[:k]

    def retrieve(self, question, k=10, path=None):
        route, intent = self.route(question)
        path = path or route
        if path == "vector":
            return self.vector(question, k)
        if path == "graph":
            return self.graph(question, intent, k)
        merged = []
        for n in self.graph(question, intent, k) + self.vector(question, k):
            if n not in merged:
                merged.append(n)
        return merged[:k]

    def answer(self, question):
        """For relationship questions the graph gives the answer itself, with the chunk that justifies each edge."""
        _, intent = self.route(question)
        nodes = self.graph(question, intent)
        rel = {"dep_licenses": "LICENSED_AS", "dep_maintainers": "MAINTAINED_BY"}.get(intent)
        if not rel:
            return [(self.g.name(n), f"{n}#0") for n in nodes]
        return [(self.g.name(n), self.g.name(v), f"{n}#0") for n in nodes for v in self.g.out(n, rel)]
