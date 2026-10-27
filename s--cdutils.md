# Context

CellDesigner SBML is a complicated xml format combining SBML model with its own proprietary code.
A set of utilities is needed to modify the format, in particular annotations of elements (called species), reactions and compartments.

Eplore exising code base and specifications to suggest a set of utilities to be used by Claude in projects requiring manipulation of CellDesigner SBML xml.

# Codebase

Explore and use information in these sources.

## Results of Claude exploration 

Claude already wrote code parsing CellDesigner and modifying it, which can be found in `harmonise-protein-annotations` and `resize`.

Results of file exploration are also available in `specifications-cdmaps.md`

## Code repository of a working parser

The MINERVA Platform already implements an extensive parser of CellDesigner SBML xml:
https://gitlab.com/uniluxembourg/lcsb/BioCore/minerva/core/-/tree/development/converter-CellDesigner?ref_type=heads

# Implementation

## Operations needed

All operations should be read/write for elements (species), reactions, or compartments. 
These are called "diagram components" or "components".

- Read and write annotations to add/remove identifiers of components
- Filter content, find components
  - by annotations
  - by component type, including specific types, like reaction types, species types or protein subtypes
  - by details of components
    - graphical properties: colour, line thickness, relative position (nesting) for `COMPLEX` species or compartments
      - do not parse reaction layout information
    - for species, consider hypothetical, modifications, homodimer, structural state, position to compartment (membrane/lumen)
- Manipulate species and reactions
  - Change graphical properties (colour, line thickness)
  - Modify species inside complexes
  - Change protein or reaction type within their respective classes
- Qualifier handling on write — when writing annotations, the library should use bqbiol:is for identities (correct semantics per Section 8.2), and warn about the qualifier change/correction. There should be a possibility of switching off this correction.
- File encoding / XML serialisation — CellDesigner SBML files have a specific XML declaration and namespace arrangement, and they are brittle. The library preserve the original formatting.
- Error handling
  - CellDesigner SBML format is very brittle. If any modification partially fails, the function should abort.

## Testing file integrity

For any modified file, use the MINERVA Plafrom API to validate it's integrity.
Check https://minerva-service.lcsb.uni.lu/minerva/docs/converter.html and `1. Conversion to systems biology formats`.
The call (in curl as an example):
curl 'https://minerva-service.lcsb.uni.lu/minerva/api/convert/CellDesigner_SBML:CellDesigner_SBML' -X POST --data-binary @file_to_test.xml -H 'Content-Type: text/plain'
Should return a 200 status and a non-zero file.
Otherwise, the file is corrupted.

## API

Create a python 3.x library with modules to be imported.
Use lxml for CellDesigner SBML xml.

## Error/edge-case handling

- Included species (RDF in <notes> instead of <annotation>) - the utilities should read/write annotations there.

- Missing/malformed elements - If a species has no <annotation> block at all, get_annotations() should return an empty dict.

- Shared protein definitions - Multiple species can share the same proteinReference. Rename via that reference, should rename all instances simultaneously. Desired behaviour: hide the mechanism but warn when a rename affects more than one species.

- Read-only vs. read-write scope - The utilities should guard against writing back a file that wasn't changed.

## Structural state

Available only on **PROTEIN** and **COMPLEX** species.
Stored in `speciesIdentity/state/listOfStructuralStates/structuralState/@structuralState`.

Although the XML wraps the value in a list element, CellDesigner only handles a **single entry**; the API reflects this.

```python
get_structural_state(species_node) -> str | None
set_structural_state(diagram, species_node, state: str | None)
get_species_state(species_node) -> dict
```

- `get_structural_state` returns the state string (e.g. `"N:3"`) or `None` if absent; returns `None` silently for non-PROTEIN/COMPLEX classes.
- `set_structural_state` replaces the single entry; pass `None` to remove `listOfStructuralStates` entirely. Raises `ValueError` if the species class is not PROTEIN or COMPLEX.
- Both `<celldesigner:state>` and `<celldesigner:listOfStructuralStates>` are created on demand by `set_structural_state` if not already present.

Species state is stored in **two independent** places — the structural state
(`listOfStructuralStates`, above) and residue-level modifications
(`listOfModifications`, read by `get_modifications`). Reading only one is a
false-negative trap: a species whose only state is `structuralState="active"`
has no modifications and looks unmodified to `get_modifications` alone.
`get_species_state` combines both in one call:

```python
get_species_state(species_node) -> {
    "structural_state": str | None,          # from get_structural_state
    "modifications": [ {"residue", "state"} ],  # from get_modifications
}
```

Prefer it when asking "does this species have *any* state?" or when comparing
two same-named species/complexes (e.g. whether a `STATE_TRANSITION` is a genuine
flip or a no-op). The two primitives remain available for single-construct reads.


## Position to compartment (membrane / lumen)

Membrane-vs-lumen placement is stored **explicitly** (not geometrically) in
`annotation/celldesigner:extension/celldesigner:positionToCompartment`, a
sibling of `speciesIdentity` on the species element.

```python
get_position_to_compartment(species_node) -> str | None
```

- Values: `"inside"` (compartment lumen/interior), `"transmembrane"`,
  `"innerSurface"`, `"outerSurface"`.
- Returns `None` when absent — e.g. included/complex-member species, which have
  no compartment placement of their own.
- One value per species: CellDesigner merges aliases so no two glyphs of a species
  share a compartment location, making the placement unambiguous.

## Compartment nesting (geometric)

`<compartmentAlias>` nodes carry `bounds` but **no parent pointer**, so
compartment-in-compartment nesting is recoverable only from box geometry. A
`speciesAlias`/`complexSpeciesAlias` *does* reference its immediate container
via `@compartmentAlias`/`@complexSpeciesAlias` (resolved by `get_parent_alias`),
but that gives only the innermost compartment, not the chain above it. The SBML
`@outside` attribute is a *referential* parent chain that can diverge from the
drawn geometry when a compartment has several aliases; where they disagree, the
geometry is what the curator drew and what MINERVA renders.

```python
bounds_contain(outer, inner, *, tol=1.0) -> bool
get_enclosing_compartment_alias(diagram, alias_node, *, tol=1.0) -> node | None
get_compartment_alias_chain(diagram, alias_node, *, tol=1.0) -> [node, ...]      # inner -> outer
locate_species(diagram, species_id, *, tol=1.0) -> [ {glyph placement}, ... ]
```

- `bounds_contain` — pure `(x, y, w, h)` geometry; `outer` encloses `inner` within `tol` px per edge.
- `get_enclosing_compartment_alias` — smallest-area `compartmentAlias` strictly containing the node.
- `get_compartment_alias_chain` — repeated enclosure, innermost → outermost; `[]` if on the canvas.
- `locate_species` — one entry per glyph (`speciesAlias`): `alias_id`, `geometry_alias_chain`,
  `geometry_chain` (drawn compartment ids), `outside_chain` (referential `@outside` ids), and
  `diverges` — `True` when `geometry_chain` is **not a prefix of** `outside_chain` (a trailing
  undrawn root such as `default` does not count). Included-species glyphs are walked up their
  complex-alias chain to the innermost `compartmentAlias`, then continued geometrically.
- `tol` (default 1.0 px) absorbs shared borders and float rounding.

## Species name (canonical) & cross-diagram equivalence

SBML IDs are **not** comparable across diagrams. A species' display name can live
in three places with two escape schemes (see *Species renaming*), so the same
entity may read as `(+)ss gRNA` (top-level) and `(+)ss_space_gRNA` (included).

```python
get_species_name(diagram, species_node) -> str
find_equivalent_species(source_diagram, source_species, target_diagram,
                        *, require_annotation=True, use_state=True) -> [ {...}, ... ]
```

- `get_species_name` — the canonical, **decoded** name. Resolution order: (1)
  PROTEIN/GENE/RNA/ANTISENSE_RNA → entity-definition `@name`; (2)
  COMPLEX/PHENOTYPE/ION/… → `speciesIdentity/celldesigner:name`; (3) fallback →
  species `@name`. Un-escapes `_space_`/`_minus_` (and `_plus_`/`_slash_` for the
  name tag), so encoded and decoded forms of one entity compare equal.
- `find_equivalent_species` — assess equivalence across submaps by the
  combination of canonical name + **shared identity annotations** (uniprot,
  obo.go, …; taxonomy/literature are only weak evidence), with **species state**
  (modifications + structural state) as a tiebreaker. Searches top-level and
  included species. Returns candidates best-first, each with `species`,
  `species_id`, `name`, `name_match`, `shared_annotations`, `shared_identity`,
  `state_match`, `score` (3·identity + 1·other + 2·name + 0.5·state).
  `require_annotation=False` also accepts an exact-name match when the source
  has no identity annotation. A heuristic aid — verify before acting.

## Species renaming

Species' names can be stored in various places:
- in species (inlcuded or top), as an attribute
- in celldesigner:name tag (complexe, phenotype, ion, simple molecule, drug, unknown, degraded) 
- in a dedicated acompanying information (celldesigner:protein, :gene, :rna, :antisenserna)

When renaming, always modify species name in these additional locations.