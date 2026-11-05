#!/usr/bin/env python3
"""Insert the canonical xDS LB policy tree into each xDS LB policy document and
into 09-xds/06-lb-policies.md.

The tree is a box-drawing tree inside an HTML <pre> block, with each policy an
<a href> link (GitHub keeps <a> and <b> inside <pre>). The current policy is
bold and marked "◀ this policy".

Each document must contain the placeholder `<!-- XDS-LB-TREE -->`, or a
previously generated block between `<!-- XDS-LB-TREE...-->` and
`<!-- /XDS-LB-TREE -->`, which is replaced.
"""
import re, os

SPEC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # doc/spec


def tree_lines(cur, xprefix, gprefix, regprefix):
    def x(name):  # xDS-dir policy
        a = f'<a href="{xprefix}{name}.md">{name}</a>'
        return f"<b>{a}  ◀ this policy</b>" if name == cur else a

    def g(name):  # general-purpose policy
        return f'<a href="{gprefix}{name}.md">{name}</a>'

    reg = f'<a href="{regprefix}#2-xds-lb-policy-registry">xDS LB Policy Registry</a>'

    # (label, [children])
    leaf_subtree = (
        f"{g('priority')}  (one child per EDS priority)",
        [
            (f"{x('xds_wrr_locality')}  (default; see {reg})", [
                (f"{g('weighted_target')}  (one child per locality)", [
                    (f"endpoint-picking policy (e.g. {g('round_robin')})", [
                        (f"{g('pick_first')}  (one per endpoint)", []),
                    ]),
                ]),
            ]),
            (f"or another converted policy: {g('ring_hash')} | {g('random_subsetting')} | ...", []),
        ],
    )
    root = (
        f"{x('xds_cluster_manager')}  (one child per cluster and per cluster specifier plugin)",
        [
            (f"{x('cds')}  (one per cluster)", [
                ("non-aggregate cluster (EDS or LOGICAL_DNS):", [
                    (g("outlier_detection"), [
                        (x("xds_cluster_impl"), [
                            (x("xds_override_host"), [leaf_subtree]),
                        ]),
                    ]),
                ]),
                ("aggregate cluster:", [
                    (f"{g('priority')}  (one child per leaf cluster)", [
                        (f"{x('cds')}  (one per leaf cluster; non-aggregate subtree above)", []),
                    ]),
                ]),
            ]),
            (f"{g('rls')}  (one per RLS cluster specifier plugin)", [
                (f"{x('cds')}  (one per target cluster returned by the lookup server)", []),
            ]),
        ],
    )

    out = []

    def walk(node, prefix, is_last, is_root):
        label, children = node
        if is_root:
            out.append(label)
            child_prefix = ""
        else:
            out.append(prefix + ("└── " if is_last else "├── ") + label)
            child_prefix = prefix + ("    " if is_last else "│   ")
        for i, c in enumerate(children):
            walk(c, child_prefix, i == len(children) - 1, False)

    walk(root, "", True, True)
    return out


targets = [(n, os.path.join(SPEC, "09-xds/lb-policies", n + ".md"),
            dict(xprefix="", gprefix="../../04-client-channel/lb-policies/", regprefix="../06-lb-policies.md"))
           for n in ["xds_cluster_manager", "cds", "xds_cluster_impl", "xds_override_host", "xds_wrr_locality"]]
targets.append((None, os.path.join(SPEC, "09-xds/06-lb-policies.md"),
                dict(xprefix="lb-policies/", gprefix="../04-client-channel/lb-policies/", regprefix="")))

pat = re.compile(r"<!-- XDS-LB-TREE(?:[^>]*)-->(?:.*?<!-- /XDS-LB-TREE -->)?", re.S)
for name, p, kw in targets:
    s = open(p, newline="").read()
    nl = "\r\n" if "\r\n" in s else "\n"
    lines = tree_lines(name, **kw)
    block = nl.join(
        ["<!-- XDS-LB-TREE: generated; identical in every xDS LB policy document except for the highlighted policy -->",
         "<pre>"] + lines + ["</pre>", "<!-- /XDS-LB-TREE -->"])
    n = len(pat.findall(s))
    assert n == 1, (p, n)
    s = pat.sub(lambda m: block, s)
    open(p, "w", newline="").write(s)
    print("updated", p)
