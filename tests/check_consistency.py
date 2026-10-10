"""Builder consistency: run the normalize stage twice on the same briefs and compare the structured fields (two model calls).

    .venv/bin/python tests/check_consistency.py briefs/brief-a.md tools/openapi.json
"""
import json, pathlib, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from builder import llm, normalize
from check_variant import flat


def main(argv):
    briefs, spec = [(pathlib.Path(b).name, pathlib.Path(b).read_text()) for b in argv[:-1]], pathlib.Path(argv[-1]).read_text()
    work = pathlib.Path(tempfile.mkdtemp(prefix="consistency-"))
    lines, policies = [], []
    for i in (1, 2):
        policies.append(normalize.normalize(briefs, spec, work, lines.append, llm.ask, llm.parse_json))
    a, b = flat(policies[0]), flat(policies[1])
    diff = [k for k in a if a[k] != b[k]]
    for k in diff:
        print("DIFF", k, "\n   run 1:", json.dumps(a[k])[:300], "\n   run 2:", json.dumps(b[k])[:300])
    print("\n".join(lines))
    print(str(len(a) - len(diff)) + " / " + str(len(a)) + " structured fields identical between two builds; rules extracted:", len(policies[0].get("rules", [])), "and", len(policies[1].get("rules", [])))
    return 0 if not diff else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
