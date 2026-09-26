"""python -m graphrag bench    graph and vector retrieval on questions that need hops, written to results/"""
import sys

from .bench import bench

if __name__ == "__main__":
    if sys.argv[1:] != ["bench"]:
        sys.exit(__doc__)
    print(bench())
