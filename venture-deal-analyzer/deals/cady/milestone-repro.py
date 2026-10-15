"""Reproduction of CADY's "Hierarchical Reasoning & Graded Recognition"
milestone (sheet dated "Proven June 30, 2026") in plain Python, no FPGA.

Purpose: an independent check on how much capability the milestone
demonstrates. Every one of the five tests, and the ladder rungs 1-3, is
passed below by a frame/semantic-network classifier with property
inheritance and candidate elimination: textbook symbolic AI (Quillian
1968, Minsky 1974, Mitchell 1977). The taxonomy is our reconstruction from
the sheet's wording; their exact taxonomy sits in an appendix that was
not supplied.

Run: python3 -I milestone-repro.py
"""

# Two-branch, three-level taxonomy: root -> category -> item.
# "has" = traits introduced at that node; children inherit them.
TAXONOMY = {
    "thing":      {"parent": None,      "has": set()},
    "vehicle":    {"parent": "thing",   "has": {"wheels"}},
    "tableware":  {"parent": "thing",   "has": {"used for eating"}},
    "car":        {"parent": "vehicle", "has": {"4+ wheels", "enclosed cabin", "motor"}},
    "motorcycle": {"parent": "vehicle", "has": {"2 wheels", "motor"}},
    "bicycle":    {"parent": "vehicle", "has": {"2 wheels", "pedal-powered"}},
    "spoon":      {"parent": "tableware", "has": {"utensil", "elongated", "bowl-end"}},
    "fork":       {"parent": "tableware", "has": {"utensil", "elongated", "tines"}},
}


def lineage(node):
    while node:
        yield node
        node = TAXONOMY[node]["parent"]


def traits(node):
    """All traits of a node, each tagged with the ancestor it is inherited from."""
    return {t: anc for anc in lineage(node) for t in TAXONOMY[anc]["has"]}


def leaves():
    return [n for n in TAXONOMY if not any(v["parent"] == n for v in TAXONOMY.values())]


def common_ancestor(nodes):
    paths = [list(lineage(n)) for n in nodes]
    return next(a for a in paths[0] if all(a in p for p in paths[1:]))


def identify(observed):
    observed = set(observed)
    matches = [leaf for leaf in leaves() if observed <= traits(leaf).keys()]
    if not matches:
        return "no known object has all of these traits - I cannot classify it."
    if len(matches) == 1:
        leaf, t = matches[0], traits(matches[0])
        why = "; ".join(f"'{x}' (from {t[x]})" for x in sorted(observed))
        inferred = sorted(set(t) - observed)
        parent = TAXONOMY[leaf]["parent"]
        ruled_out = [f"not {s}: lacks {sorted(observed - traits(s).keys())}" for s in leaves()
                     if s != leaf and TAXONOMY[s]["parent"] == parent]
        return f"{leaf}. Because: {why}. Inferred, not given: {inferred}. {'; '.join(ruled_out)}."
    # Several candidates: report the level certainty reaches, and the traits that would decide it.
    level = common_ancestor(matches)
    deciders = sorted(set().union(*(TAXONOMY[m]["has"] for m in matches))
                      - set.intersection(*(set(TAXONOMY[m]["has"]) for m in matches)))
    return (f"it is a {level}, but I cannot say which kind: consistent with {sorted(matches)}. "
            f"Deciding traits: {deciders}.")


MEMORY = {}  # ladder rungs 1 and 3: "learns a fact, retains it after the source is removed"


def learn(label, source):
    MEMORY[label] = source


if __name__ == "__main__":
    tests = [
        ("1 climbs the hierarchy", {"wheels", "4+ wheels", "enclosed cabin"}),
        ("2 discriminates siblings", {"wheels", "2 wheels", "pedal-powered"}),
        ("3 supplies missing knowledge", {"utensil", "elongated", "bowl-end"}),
        ("4 refuses to guess", {"wheels", "2 wheels"}),
        ("5 graded certainty (headline)", {"wheels"}),
    ]
    for name, obs in tests:
        print(f"TEST {name}: given {sorted(obs)}\n  -> {identify(obs)}")

    # Rung 3: "a real perception tool labeled 60 distinct objects; she learned all 60;
    # the tool was removed; she retained and recalled all 60."
    tool = {f"object_{i:02d}": "perception tool" for i in range(60)}
    for label, src in tool.items():
        learn(label, src)
    del tool
    print(f"LADDER rung 3: tool removed, recalled {len(MEMORY)}/60 labels")
