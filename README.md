# cdutils

Python utilities for reading and editing [CellDesigner](https://www.celldesigner.org/) SBML XML files.

CellDesigner files combine SBML Level 2 Version 4 with CellDesigner's own extensions. They break easily: a species name can be stored in three places, annotations of complex subunits are kept in `<notes>` instead of `<annotation>`, and layout is stored in alias nodes separate from the model. `cdutils` handles these details so you can annotate, search and edit a map without leaving dangling references or making changes that MINERVA rejects.

## Installation

Requires Python ≥ 3.10 and `lxml`.

```bash
pip install git+https://github.com/mjostaszewski/cdutils.git
# or, from a local clone
pip install -e .
```

## Quick start

```python
from cdutils import (load_diagram, save_diagram, find_by_name, find_by_annotation,
                     get_annotations, add_annotation, get_aliases_for_species, set_colour)

d = load_diagram("Autophagy.xml")

pink1 = find_by_name(d, "PINK1")[0]
get_annotations(pink1)              # {'is': ['urn:miriam:uniprot:Q9BXM7']}

add_annotation(pink1, "is", "hgnc.symbol", "PINK1", diagram=d)
for alias in get_aliases_for_species(d, pink1.get("id")):
    set_colour(alias, "ffccffcc", diagram=d)   # ARGB

save_diagram(d, "Autophagy.edited.xml", validate=True)
```

Functions return and accept plain `lxml` elements, so you can still use `etree` for anything the library does not cover.

## What's in the package

| Module | Covers |
|---|---|
| `io` | `load_diagram`, `save_diagram`, `CDDiagram`, `get_canvas_size` |
| `annotations` | Get/set/add/remove MIRIAM annotations, with qualifier correction; get/set plain-text notes; `parse_miriam_uri`, `make_miriam_uri` |
| `species` | Listing top-level and included species; canonical names; class, protein type, homodimer, hypothetical; modifications and structural state; renaming; complex membership; entity-definition clean-up and merging; removing species |
| `reactions` | Listing reactions and participants; changing reaction type; adding, removing and rewiring reactions; connected components |
| `compartments` | Listing and renaming compartments; the `@outside` hierarchy |
| `query` | `find_by_name`, `find_by_class`, `find_by_annotation`, `find_by_protein_type`, `find_by_reaction_type`, `find_equivalent_species` (across diagrams) |
| `layout` | Aliases; colour, line width, bounds, activity; compartment nesting from geometry; `locate_species` |
| `validate` | Integrity check through the MINERVA converter API |
| `namespaces` | XML namespace constants and the annotation/qualifier model |

Every public function is exported from the top-level `cdutils` package. Signatures and edge cases are documented in the docstrings.

## Behaviour to know about

**Saving only happens after a change.** `save_diagram` writes the file only when the diagram has been marked dirty, and returns `False` when it skips the write. Functions that change the map take a `diagram=` argument (positional for the ones that need the whole diagram anyway). **If you change an element without passing `diagram`, the change is not recorded and `save_diagram` silently does nothing.** Load and save keep the original whitespace.

**Errors are raised before anything changes.** If an annotation or notes write fails partway, the element is restored to its earlier state. Reaction and species edits check their inputs first (unknown ids, aliases that belong to another species, duplicate reaction ids) and raise `ValueError` before they change the tree.

**Included species are handled automatically.** CellDesigner does not allow `<annotation>` on complex subunits, so their RDF goes inside `<celldesigner:notes>`. `get_annotations` / `set_annotations` and `find_by_annotation` read and write both locations, and `get_annotation_location` tells you which one an element uses.

**Qualifiers are corrected on write.** By default `set_annotations` moves each identifier to the qualifier that fits the element's class. For example, `uniprot` on a protein goes under `bqbiol:is`, and `taxonomy` on a reaction stays under `occursIn`. It logs a warning for every change. It leaves annotations alone when they are already valid, when the namespace is not covered by the model, or when the right qualifier is ambiguous. Pass `correct_qualifiers=False` to turn this off. `add_annotation` and `remove_annotation` never correct qualifiers; they keep exactly the qualifiers you give them. The rules are defined in `cdutils.namespaces.ANNOTATION_MODEL`.

**Names are synchronised and decoded.** `rename_species` updates every place a name is stored (the SBML `@name`, `celldesigner:name`, and the protein/gene/RNA definition). It emits a `UserWarning` when a shared definition means more than one species gets renamed. `get_species_name` decodes CellDesigner escapes such as `_space_` and `_minus_`, so names written in different forms compare equal.

**Species state is stored in two places.** Use `get_species_state` to read both. `get_modifications` alone misses a species whose only state is a structural state such as `"active"`.

**Compartment nesting.** `compartmentAlias` nodes do not record their parent, so nesting is computed from the box geometry (`get_compartment_alias_chain`, `locate_species`). `locate_species` also reports where the drawn geometry disagrees with the SBML `@outside` chain.

**Reaction layout is not parsed.** Layout functions work on species, complex and compartment aliases only.

## Validating with MINERVA

`validate_file`, `validate_diagram` and `save_diagram(..., validate=True)` send the XML to the MINERVA converter endpoint. They raise `ValidationError` unless MINERVA returns HTTP 200 with a non-empty body. With `validate=True`, the file is not written when the check fails.

These calls need network access. By default they use the public LCSB service. You can override this with environment variables:

| Variable | Default |
|---|---|
| `MINERVA_CONVERT_URL` | `https://minerva-service.lcsb.uni.lu/minerva/api/convert/CellDesigner_SBML:CellDesigner_SBML` |
| `MINERVA_CONVERT_TIMEOUT` | `60` (seconds) |

## Tests

The tests in `tests/` are standalone scripts, not pytest modules. Run each one directly:

```bash
for t in tests/test_*.py; do python "$t"; done
```

Most of them need real maps that are not part of this repo: PD map submaps under `/workspace/pdmap/` and the AD knowledge-graph map. Several also call the MINERVA API.

## Specifications

- [`s--cdmaps.md`](s--cdmaps.md): the CellDesigner SBML XML format as these utilities understand it (namespaces, document structure, species, aliases, annotations).
- [`s--cdutils.md`](s--cdutils.md): the requirements and design notes the library was built from.
