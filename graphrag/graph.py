"""The graph: a constrained ontology, entity resolution, and an idempotent store.

Entities: Package, Maintainer, License. Relationships: DEPENDS_ON (package to package),
MAINTAINED_BY, LICENSED_AS. Nothing else is extracted, so every query has a known shape.

Entity resolution is where raw metadata fails: `requires_dist` says `charset_normalizer`,
the project is `charset-normalizer`; licenses come as "MIT", "MIT License" or a classifier.
Names are normalised (PEP 503 for packages; a table for licenses) and every spelling seen is
kept as an alias. Writes are upserts, so ingesting twice changes nothing, and every edge
carries the chunk that justifies it.
"""
import re
import sqlite3

LICENSES = {"mit": "MIT", "mit license": "MIT", "apache 2.0": "Apache-2.0", "apache-2.0": "Apache-2.0",
            "apache software license": "Apache-2.0", "apache license 2.0": "Apache-2.0", "apache license, version 2.0": "Apache-2.0",
            "bsd": "BSD", "bsd license": "BSD", "bsd-3-clause": "BSD-3-Clause", "bsd 3-clause": "BSD-3-Clause",
            "bsd-2-clause": "BSD-2-Clause", "psf-2.0": "PSF-2.0", "python software foundation license": "PSF-2.0",
            "mpl-2.0": "MPL-2.0", "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0", "isc": "ISC", "isc license (iscl)": "ISC",
            "lgpl-3.0-or-later": "LGPL-3.0", "gnu lesser general public license v3 (lgplv3)": "LGPL-3.0",
            "unlicense": "Unlicense", "the unlicense (unlicense)": "Unlicense"}


def package_id(name):
    return "package:" + re.sub(r"[-_.]+", "-", name).lower()


def dependency_names(requires_dist):
    """Runtime dependencies only: entries behind an `extra ==` marker are optional."""
    out = []
    for req in requires_dist or []:
        if "extra ==" in req.replace(" ", "").replace("extra==", "extra =="):
            continue
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
        if m:
            out.append(m.group(1))
    return out


def license_of(info):
    raw = info.get("license_expression") or ""
    if not raw and info.get("license") and len(info["license"]) < 60:
        raw = info["license"]
    if not raw:
        raw = next((c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")), "")
    raw = raw.strip()
    return LICENSES.get(raw.lower(), raw) if raw else ""


def maintainer_of(info):
    name = info.get("author") or info.get("maintainer") or ""
    if not name:
        m = re.match(r'\s*"?([^"<,]+?)"?\s*<', info.get("author_email") or info.get("maintainer_email") or "")
        name = m.group(1) if m else ""
    return re.sub(r"\s+", " ", name).strip()


def chunks(info, size=800, most=3):
    """[(chunk id, text)]: a metadata chunk, then up to `most` description chunks."""
    pid = package_id(info["name"])
    out = [(f"{pid}#0", f"{info['name']}: {info.get('summary') or ''}")]
    buf = ""
    for para in re.split(r"\n\s*\n", info.get("description") or ""):
        if len(buf) + len(para) > size and buf:
            out.append((f"{pid}#{len(out)}", buf.strip()))
            buf = ""
        buf += para + "\n\n"
        if len(out) > most:
            break
    if buf.strip() and len(out) <= most:
        out.append((f"{pid}#{len(out)}", buf.strip()))
    return out


class Graph:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, type TEXT, name TEXT);
            CREATE TABLE IF NOT EXISTS aliases (alias TEXT PRIMARY KEY, node TEXT);
            CREATE TABLE IF NOT EXISTS edges (src TEXT, rel TEXT, dst TEXT, chunk TEXT, PRIMARY KEY (src, rel, dst));
            CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, node TEXT, text TEXT);""")

    def node(self, nid, type_, name, *aliases):
        self.db.execute("INSERT OR IGNORE INTO nodes VALUES (?, ?, ?)", (nid, type_, name))
        for a in (name, *aliases):
            self.db.execute("INSERT OR IGNORE INTO aliases VALUES (?, ?)", (a.lower(), nid))

    def edge(self, src, rel, dst, chunk):
        self.db.execute("INSERT OR IGNORE INTO edges VALUES (?, ?, ?, ?)", (src, rel, dst, chunk))

    def ingest(self, infos, normalise=True):
        """Upsert every record; returns how many dependency mentions resolved to a package in the corpus."""
        key = package_id if normalise else (lambda n: "package:" + n)
        for info in infos:
            self.node(key(info["name"]), "Package", info["name"], re.sub(r"[-_.]+", "-", info["name"]))
            for cid, text in chunks(info):
                self.db.execute("INSERT OR IGNORE INTO chunks VALUES (?, ?, ?)", (cid, key(info["name"]), text))
        known = {r[0] for r in self.db.execute("SELECT id FROM nodes WHERE type = 'Package'")}
        mentions = resolved = 0
        for info in infos:
            pid, meta = key(info["name"]), f"{package_id(info['name'])}#0"
            for dep in dependency_names(info.get("requires_dist")):
                mentions += 1
                if key(dep) in known:
                    resolved += 1
                    self.edge(pid, "DEPENDS_ON", key(dep), meta)
            lic, who = license_of(info), maintainer_of(info)
            if lic:
                self.node(f"license:{lic.lower()}", "License", lic)
                self.edge(pid, "LICENSED_AS", f"license:{lic.lower()}", meta)
            if who:
                self.node(f"maintainer:{who.lower()}", "Maintainer", who)
                self.edge(pid, "MAINTAINED_BY", f"maintainer:{who.lower()}", meta)
        self.db.commit()
        return {"mentions": mentions, "resolved": resolved}

    def out(self, src, rel):
        return [r[0] for r in self.db.execute("SELECT dst FROM edges WHERE src = ? AND rel = ?", (src, rel))]

    def into(self, dst, rel):
        return [r[0] for r in self.db.execute("SELECT src FROM edges WHERE dst = ? AND rel = ?", (dst, rel))]

    def name(self, nid):
        row = self.db.execute("SELECT name FROM nodes WHERE id = ?", (nid,)).fetchone()
        return row[0] if row else nid

    def counts(self):
        return dict(self.db.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall()) | \
            {r: n for r, n in self.db.execute("SELECT rel, COUNT(*) FROM edges GROUP BY rel")}
