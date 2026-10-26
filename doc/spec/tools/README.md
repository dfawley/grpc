# Spec maintenance tools

Scripts used to maintain the documents in `doc/spec/`. Run them from any
directory; they locate `doc/spec/` relative to their own path.

| Script | Purpose |
| --- | --- |
| `check_links.py [subpath ...]` | Checks every relative markdown link (file and `#anchor`) under `doc/spec/`, or only under the given subpaths. Reports `N problems`. |
| `check_tables.py [root]` | Checks GFM tables in `doc/spec/` and `doc/spec-optionality-notes.md`: the header and delimiter rows must have the same number of columns, and no body row may have more cells than the header (usually an unescaped `\|` in a cell). |
| `insert_xds_tree.py` | Regenerates the `<!-- XDS-LB-TREE -->` blocks in `09-xds/06-lb-policies.md` and `09-xds/lb-policies/*.md`, which show each policy's position in the xDS LB policy tree. Edit the tree in the script, then rerun it; don't edit the generated blocks by hand. |

Run `check_links.py` and `check_tables.py` after every change; both should
report `0 problems`.
