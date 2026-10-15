"""Reproduction of CADY's "Hierarchical Reasoning & Graded Recognition"
milestone (sheet dated "Proven June 30, 2026") in plain Python, no FPGA.

Purpose: an independent check on how much capability the milestone
demonstrates. The five tests and ladder rung 3 are reproduced below by a
frame/semantic-network classifier that descends the taxonomy top-down,
attributes each trait to the level it is inherited from, and stops at the
deepest level the evidence supports: textbook symbolic AI (Quillian 1968,
Minsky 1974, Mitchell 1977). The taxonomy is our reconstruction from the
sheet's wording; their exact taxonomy sits in an appendix that was not
supplied. Rung 3's "perception tool" is unnamed, so it is stood in for by
60 synthetic labels. Rungs 1-2 are not reproduced here.

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


def children(node):
    return [n for n, v in TAXONOMY.items() if v["parent"] == node]


def traits(node):
    """All traits of a node, each tagged with the ancestor it is inherited from."""
    out = {}
    while node:
        out.update({t: node for t in TAXONOMY[node]["has"]})
        node = TAXONOMY[node]["parent"]
    return out


def explains(node, observed):
    """Can this node, or something below it, carry every observed trait?"""
    return observed <= traits(node).keys() or any(explains(c, observed) for c in children(node))


def deciders(cands):
    """Per candidate, the fewest of its own traits that rule out every other candidate."""
    out = {}
    for c in cands:
        others = [o for o in cands if o != c]
        unique = sorted(t for t in TAXONOMY[c]["has"] if not any(t in traits(o) for o in others))
        if unique:
            out[c] = " or ".join(unique)
            continue
        pick, left = [], others
        for t in sorted(TAXONOMY[c]["has"], key=lambda t: -sum(t not in traits(o) for o in left)):
            if left:
                pick.append(t)
                left = [o for o in left if t in traits(o)]
        out[c] = " + ".join(pick)
    return "; ".join(f"{c} if {d}" for c, d in out.items())


def identify(observed):
    observed, node, path = set(observed), "thing", []
    while True:  # descend while exactly one child can explain the evidence
        viable = [c for c in children(node) if explains(c, observed)]
        if len(viable) != 1:
            break
        node = viable[0]
        path.append(node)
    if not path:
        return "no known object has all of these traits - I cannot classify it."
    t = traits(node)
    why = "; ".join(f"'{x}' (from {t[x] if x in t else ' / '.join(c for c in viable if x in traits(c))})"
                    for x in sorted(observed))
    route = " -> ".join(path)
    if viable:  # stopped above the leaves: graded certainty
        return (f"it is a {node}, but I cannot say which kind ({route}). Because: {why}. "
                f"Consistent with {sorted(viable)}. To decide: {deciders(viable)}.")
    inferred = sorted(set(t) - observed)
    contrast = "; ".join(
        f"vs {s}: {sorted(TAXONOMY[node]['has'] - TAXONOMY[s]['has'])} "
        f"not {sorted(TAXONOMY[s]['has'] - TAXONOMY[node]['has'])}"
        for s in children(TAXONOMY[node]["parent"]) if s != node)
    return f"{node} ({route}). Because: {why}. Inferred, not given: {inferred}. Differs {contrast}."


MEMORY = {}  # ladder rung 3: labels kept after their source is gone


def learn(label, source):
    MEMORY[label] = source


if __name__ == "__main__":
    tests = [
        ("1 climbs the hierarchy", {"wheels", "4+ wheels", "enclosed cabin"}),
        ("2 discriminates siblings", {"wheels", "2 wheels", "pedal-powered"}),
        ("2b discriminates siblings", {"wheels", "2 wheels", "motor"}),
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
    recalled = [label for label in (f"object_{i:02d}" for i in range(60)) if label in MEMORY]
    print(f"LADDER rung 3: tool removed, recalled {len(recalled)}/60 labels")
