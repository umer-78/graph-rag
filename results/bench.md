500 packages; graph: {'License': 46, 'Maintainer': 311, 'Package': 500, 'DEPENDS_ON': 1051, 'LICENSED_AS': 495, 'MAINTAINED_BY': 479}.

Entity resolution: 1112 of 1231 runtime-dependency mentions resolve to a package in the corpus with PEP 503 names; 1042 with names taken as written. Ingesting twice leaves the graph unchanged: True.

| Question kind | Questions | Router correct | Recall@10: vector | Recall@10: routed | Recall@10: both merged |
|---|---|---|---|---|---|
| fact | 60 | 100% | 98.3% | 98.3% | 100.0% |
| deps | 60 | 100% | 22.3% | 100.0% | 100.0% |
| dependents | 60 | 100% | 15.3% | 100.0% | 100.0% |
| dep_licenses | 60 | 100% | 13.7% | 100.0% | 100.0% |
| dep_maintainers | 60 | 100% | 18.0% | 100.0% | 100.0% |
| shared | 60 | 100% | 62.0% | 100.0% | 100.0% |
| all | 360 | 100% | 38.3% | 99.7% | 100.0% |

Answer from the graph for "What licences do the packages cyclopts needs use?" (package, licence, source chunk):

- attrs — MIT (`package:attrs#0`)
- docstring-parser — MIT (`package:docstring-parser#0`)
- rich — MIT (`package:rich#0`)
- rich-rst — MIT (`package:rich-rst#0`)
