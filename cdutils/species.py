"""Operations on CellDesigner species (top-level and included/complex subunits).

Name sync
---------
A species' display name can live in up to three places:

1. ``sbml:species/@name`` (top-level) or ``celldesigner:species/@name``
   (included) — the SBML-level name attribute.
2. ``<celldesigner:name>`` inside ``speciesIdentity`` — used by COMPLEX,
   PHENOTYPE, ION, SIMPLE_MOLECULE, DRUG, UNKNOWN, and DEGRADED species.
3. ``celldesigner:protein/@name`` (or gene/RNA/antisenseRNA) in the
   corresponding definition list — linked via ``proteinReference``.

:func:`rename_species` updates all three locations as applicable.
Multiple species can share the same ``proteinReference``; a warning is
issued when a rename affects more than one species simultaneously.

CellDesigner name encoding
--------------------------
In ``<celldesigner:species>`` (included species), spaces are stored as
``_space_`` and hyphens as ``_minus_``.  :func:`rename_species` handles
encoding automatically.
"""

from __future__ import annotations

import logging
import warnings

from lxml import etree

from .namespaces import CD, NS, PROTEIN_TYPES, SBML, SPECIES_CLASSES
from .io import CDDiagram

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name encoding
# ---------------------------------------------------------------------------

# Species classes that carry a <celldesigner:name> child inside speciesIdentity
# (distinct from the SBML @name attribute and from protein/gene/RNA definitions).
_CD_NAME_TAG_CLASSES = frozenset({
    "COMPLEX", "PHENOTYPE", "ION", "SIMPLE_MOLECULE",
    "DRUG", "UNKNOWN", "DEGRADED",
})


# CellDesigner's ``_space_`` / ``_minus_`` / ``_plus_`` / ``_slash_`` / ``_br_`` / ``_underscore_`` escapes are a
# legacy serialisation, not a requirement. Curator ruling of 2026-09-08: names are written
# plain everywhere, so the encoders below are deliberately the identity function.
#
# The evidence, measured over four curation iterations against the last pre-harmonisation
# commit (`cc4b550`):
#
# * Plain and encoded names coexist inside single files that predate the project entirely
#   (`Iron metabolism`: 31 encoded and 53 plain ``<celldesigner:name>`` tags, unchanged at
#   `cc4b550` and today, including ``Ca2+`` and ``holo-transferrin`` stored plain).
# * CellDesigner never re-encodes a plain name: those 53 survived four rounds of editing.
# * When a curator retypes a label, CellDesigner writes it **plain**
#   (``retromer_space_VPS_space_sub_minus_complex`` -> ``retromer, cargo complex``).
# * Newly authored glyphs are born plain (19 of 25 top-level, 11 of 13 included). The
#   exceptions are copy-paste descendants that inherited an encoded string verbatim, which is
#   why they are half-encoded (``Ca2_plus__space_channel:RIM-BP`` keeps a literal hyphen).
#
# So the escapes propagate from legacy fields rather than regenerating, and emitting them
# would keep a defect class alive that has no source left once the legacy fields are cleared.
# The decoders stay, because files written before 2026-09-08 still hold the escapes.
_CD_ESCAPES = (("_br_", " "), ("_slash_", "/"), ("_plus_", "+"),
               ("_space_", " "), ("_minus_", "-"))
# ``_underscore_`` is decoded around the others, not among them: its own underscores would
# otherwise complete a neighbouring escape (``x_underscore_minus_underscore_y`` is ``x_minus_y``,
# not ``x-y``). It is shielded behind a character XML cannot contain, then restored last.
_CD_UNDERSCORE = "_underscore_"
_SHIELD = "\x00"


def encode_cd_name(name: str) -> str:
    """Return a display name for use in a CellDesigner included-species ``@name``.

    Identity by the 2026-09-08 ruling above: names are stored plain.
    """
    return name


def decode_cd_name(encoded: str) -> str:
    """Decode a CellDesigner-encoded name back to a display name.

    Handles every escape in the scheme. It previously covered only ``_space_`` and
    ``_minus_``, which made :func:`get_species_name` non-canonical and silently broke
    name-based cross-diagram matching for glyphs such as ``Fe3_plus_`` and ``Ca2_plus_``.

    ``_br_`` is CellDesigner's line break inside a glyph label. It has no display-name
    equivalent and cannot be restored, so by curator ruling of 2026-09-02 it decodes to a
    space — a rename through this function deliberately turns the line break into a space.

    ``_underscore_`` (a literal ``_``, e.g. ``Gamma_underscore_secretase``) is decoded without
    letting its underscores join a neighbouring escape, so names without it decode exactly as
    before.
    """
    encoded = encoded.replace(_CD_UNDERSCORE, _SHIELD)
    for enc, dec in _CD_ESCAPES:
        encoded = encoded.replace(enc, dec)
    return encoded.replace(_SHIELD, "_")


def _encode_cd_tag_name(name: str) -> str:
    """Return a display name for use in a ``<celldesigner:name>`` element.

    Identity by the 2026-09-08 ruling above: names are stored plain.
    """
    return name


def _decode_cd_tag_name(encoded: str) -> str:
    """Decode a ``<celldesigner:name>`` element value back to a display name.

    The tag and the ``@name`` attribute share one escape scheme, so this is
    :func:`decode_cd_name`; both names are kept because callers use both.
    """
    return decode_cd_name(encoded)


# ---------------------------------------------------------------------------
# Accessors — species lists
# ---------------------------------------------------------------------------

def get_all_species(diagram: CDDiagram) -> list[etree._Element]:
    """Return all top-level ``<species>`` elements from ``listOfSpecies``."""
    model = diagram.model
    species_list = model.find(f"{{{SBML}}}listOfSpecies")
    if species_list is None:
        return []
    return list(species_list)


def get_included_species(diagram: CDDiagram) -> list[etree._Element]:
    """Return all ``<celldesigner:species>`` elements from ``listOfIncludedSpecies``."""
    model = diagram.model
    ann = model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return []
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return []
    lis = ext.find(f"{{{CD}}}listOfIncludedSpecies")
    if lis is None:
        return []
    return list(lis)


def get_species_by_id(diagram: CDDiagram, species_id: str) -> etree._Element | None:
    """Find a species by ID in both top-level and included species lists."""
    for sp in get_all_species(diagram):
        if sp.get("id") == species_id:
            return sp
    for sp in get_included_species(diagram):
        if sp.get("id") == species_id:
            return sp
    return None


# ---------------------------------------------------------------------------
# Accessors — species properties
# ---------------------------------------------------------------------------

def _get_species_identity(species_node: etree._Element) -> etree._Element | None:
    """Return the ``celldesigner:speciesIdentity`` element."""
    # Top-level: inside sbml:annotation/cd:extension
    ann = species_node.find(f"{{{SBML}}}annotation")
    if ann is not None:
        ext = ann.find(f"{{{CD}}}extension")
        if ext is not None:
            return ext.find(f"{{{CD}}}speciesIdentity")
    # Included: inside cd:annotation
    cd_ann = species_node.find(f"{{{CD}}}annotation")
    if cd_ann is not None:
        return cd_ann.find(f"{{{CD}}}speciesIdentity")
    return None


def get_species_class(species_node: etree._Element) -> str | None:
    """Return the species class string (e.g. ``"PROTEIN"``, ``"COMPLEX"``)."""
    identity = _get_species_identity(species_node)
    if identity is None:
        return None
    cls = identity.find(f"{{{CD}}}class")
    return cls.text if cls is not None else None


def get_position_to_compartment(species_node: etree._Element) -> str | None:
    """Return the species' placement relative to its compartment, or ``None``.

    CellDesigner records membrane-vs-lumen placement **explicitly** in
    ``annotation/celldesigner:extension/celldesigner:positionToCompartment`` (a
    sibling of ``speciesIdentity``) — it is *not* encoded in the glyph geometry.
    Values seen in this map: ``"inside"`` (compartment lumen/interior),
    ``"transmembrane"``, ``"innerSurface"``, ``"outerSurface"``.

    Returns ``None`` when the element is absent — e.g. included/complex-member
    species, which have no compartment placement of their own. A single value
    applies per species: CellDesigner merges aliases so no two glyphs of one
    species share a compartment location, so the placement is unambiguous.
    """
    # Top-level species: sbml:annotation/cd:extension/cd:positionToCompartment
    ann = species_node.find(f"{{{SBML}}}annotation")
    if ann is not None:
        ext = ann.find(f"{{{CD}}}extension")
        if ext is not None:
            el = ext.find(f"{{{CD}}}positionToCompartment")
            if el is not None:
                return (el.text or "").strip() or None
    # Included species: directly under cd:annotation (no extension wrapper)
    cd_ann = species_node.find(f"{{{CD}}}annotation")
    if cd_ann is not None:
        el = cd_ann.find(f"{{{CD}}}positionToCompartment")
        if el is not None:
            return (el.text or "").strip() or None
    return None


def get_species_name(diagram: CDDiagram, species_node: etree._Element) -> str:
    """Return the canonical, **decoded** display name of a species.

    A species' name can live in three places (see the module docstring), with
    two different encodings, so the same entity can appear as e.g.
    ``"(+)ss gRNA"`` (top-level) and ``"(+)ss_space_gRNA"`` (included). This
    resolves the authoritative location for the species class and decodes the
    CellDesigner escapes, yielding an identical string for the same entity
    regardless of glyph type — the basis for comparing names across submaps
    (SBML IDs are **not** comparable across diagrams).

    Resolution order:

    1. PROTEIN/GENE/RNA/ANTISENSE_RNA → the entity definition ``@name``
       (shared definitions give free-glyph and in-complex member the same name).
    2. COMPLEX/PHENOTYPE/ION/SIMPLE_MOLECULE/DRUG/UNKNOWN/DEGRADED →
       ``speciesIdentity/celldesigner:name``.
    3. Fallback → the species ``@name`` attribute.

    Returns ``""`` if no name is found.
    """
    cls = get_species_class(species_node)

    # 1. typed entity definition (stored as plain text)
    ref_id = _get_definition_reference_id(species_node, cls)
    if ref_id is not None:
        defn = _find_typed_definition(diagram, cls, ref_id)
        if defn is not None and defn.get("name"):
            return decode_cd_name(defn.get("name"))

    # 2. <celldesigner:name> element (its own escape scheme)
    if cls in _CD_NAME_TAG_CLASSES:
        identity = _get_species_identity(species_node)
        if identity is not None:
            nm_el = identity.find(f"{{{CD}}}name")
            if nm_el is not None and nm_el.text:
                return _decode_cd_tag_name(nm_el.text)

    # 3. @name attribute (decode included-species escapes; harmless on plain names)
    return decode_cd_name(species_node.get("name", ""))


_CLASS_REFERENCE_TAG = {
    "PROTEIN":       "proteinReference",
    "GENE":          "geneReference",
    "RNA":           "rnaReference",
    "ANTISENSE_RNA": "antisenseRNAReference",
}


def _get_definition_reference_id(species_node: etree._Element, species_class: str | None) -> str | None:
    """Return the definition-list reference ID for PROTEIN/GENE/RNA/ANTISENSE_RNA species."""
    ref_tag = _CLASS_REFERENCE_TAG.get(species_class or "")
    if ref_tag is None:
        return None
    identity = _get_species_identity(species_node)
    if identity is None:
        return None
    ref = identity.find(f"{{{CD}}}{ref_tag}")
    return ref.text if ref is not None else None


_CLASS_DEFINITION_LIST = {
    "PROTEIN":       f"{{{CD}}}listOfProteins",
    "GENE":          f"{{{CD}}}listOfGenes",
    "RNA":           f"{{{CD}}}listOfRNAs",
    "ANTISENSE_RNA": f"{{{CD}}}listOfAntisenseRNAs",
}


def _find_typed_definition(
    diagram: CDDiagram, species_class: str | None, ref_id: str | None
) -> etree._Element | None:
    """Locate the protein/gene/RNA/antisenseRNA definition element by ``@id``."""
    list_tag = _CLASS_DEFINITION_LIST.get(species_class or "")
    if list_tag is None or ref_id is None:
        return None
    model = diagram.model
    ann = model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return None
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return None
    entity_list = ext.find(list_tag)
    if entity_list is None:
        return None
    for item in entity_list:
        if item.get("id") == ref_id:
            return item
    return None


def _find_protein_definition(diagram: CDDiagram, protein_ref_id: str) -> etree._Element | None:
    """Locate ``<celldesigner:protein id="{protein_ref_id}">`` in listOfProteins."""
    model = diagram.model
    ann = model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return None
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return None
    protein_list = ext.find(f"{{{CD}}}listOfProteins")
    if protein_list is None:
        return None
    for p in protein_list:
        if p.get("id") == protein_ref_id:
            return p
    return None


def get_protein_type(diagram: CDDiagram, species_node: etree._Element) -> str | None:
    """Return the protein type (``"GENERIC"``, ``"RECEPTOR"``, etc.) by following
    the ``proteinReference`` chain. Returns ``None`` if not a PROTEIN species."""
    ref_id = _get_definition_reference_id(species_node, get_species_class(species_node))
    if ref_id is None:
        return None
    protein_def = _find_protein_definition(diagram, ref_id)
    if protein_def is None:
        return None
    return protein_def.get("type")


def get_multimer_cardinality(species_node: etree._Element) -> int:
    """Return how many copies of the entity this glyph stands for.

    CellDesigner records this as ``<celldesigner:homodimer>N</celldesigner:homodimer>`` inside
    the species' ``<celldesigner:state>``. **The tag is absent for a monomer**, so a missing
    tag means 1, not "unknown" — which is why this returns an ``int`` and never ``None``.

    Cardinality is a third, independent piece of species state alongside ``structuralState``
    and ``listOfModifications``, and it is the one most easily missed because nothing is
    written in the XML for the common case. Two glyphs of the same protein in the same
    compartment, with identical modifications, are still **different species** when one is a
    monomer and the other a dimer: `BAK1` n=1 → `BAK1` n=2 is oligomerisation, not a no-op.

    Returns 1 for a malformed or non-numeric value, since CellDesigner will not author one and
    a parse failure must not silently promote a monomer to a multimer.
    """
    identity = _get_species_identity(species_node)
    if identity is None:
        return 1
    state = identity.find(f"{{{CD}}}state")
    if state is None:
        return 1
    homodimer = state.find(f"{{{CD}}}homodimer")
    if homodimer is None or not (homodimer.text or "").strip():
        return 1
    try:
        return max(1, int(homodimer.text.strip()))
    except ValueError:
        return 1


def is_homodimer(species_node: etree._Element) -> bool:
    """Return ``True`` if the species stands for more than one copy of the entity.

    A convenience wrapper over :func:`get_multimer_cardinality`; use that when the *number*
    matters, which is whenever two same-named glyphs are being compared.
    """
    return get_multimer_cardinality(species_node) > 1


def is_hypothetical(species_node: etree._Element) -> bool:
    """Return ``True`` if the species carries ``<celldesigner:hypothetical>true</celldesigner:hypothetical>``."""
    identity = _get_species_identity(species_node)
    if identity is None:
        return False
    hyp = identity.find(f"{{{CD}}}hypothetical")
    return hyp is not None and (hyp.text or "").strip().lower() == "true"


def get_modifications(species_node: etree._Element) -> list[dict[str, str]]:
    """Return modification states as ``[{"residue": ..., "state": ...}, ...]``."""
    identity = _get_species_identity(species_node)
    if identity is None:
        return []
    state = identity.find(f"{{{CD}}}state")
    if state is None:
        return []
    mods_list = state.find(f"{{{CD}}}listOfModifications")
    if mods_list is None:
        return []
    result = []
    for mod in mods_list:
        result.append({
            "residue": mod.get("residue", ""),
            "state": mod.get("state", ""),
        })
    return result


def get_structural_state(species_node: etree._Element) -> str | None:
    """Return the structural state string, or ``None`` if absent.

    Structural states are defined only for PROTEIN and COMPLEX species.
    Returns ``None`` for all other classes or when no state is set.
    """
    cls = get_species_class(species_node)
    if cls not in ("PROTEIN", "COMPLEX"):
        return None
    identity = _get_species_identity(species_node)
    if identity is None:
        return None
    state_el = identity.find(f"{{{CD}}}state")
    if state_el is None:
        return None
    ss_list = state_el.find(f"{{{CD}}}listOfStructuralStates")
    if ss_list is None:
        return None
    first = next(iter(ss_list), None)
    if first is None:
        return None
    return first.get("structuralState") or None


def get_species_state(species_node: etree._Element) -> dict:
    """Return the complete state of a species in one call.

    CellDesigner stores species state in **three** independent places, and reading only one is
    a false-negative trap: a species whose only state is ``structuralState="active"`` has no
    ``listOfModifications`` and looks unmodified to :func:`get_modifications` alone, and a
    species that differs only in multimer cardinality has neither. This getter combines all
    three so a caller cannot miss one.

    Parameters
    ----------
    species_node:
        A ``<species>`` or ``<celldesigner:species>`` element.

    Returns
    -------
    dict
        ``{"structural_state": str | None, "modifications": list[dict[str, str]],
        "multimer_cardinality": int}``

        - ``structural_state`` — the ``<celldesigner:structuralState>`` string
          (PROTEIN/COMPLEX only), or ``None`` if absent (see
          :func:`get_structural_state`).
        - ``modifications`` — residue-level marks from
          ``<celldesigner:listOfModifications>`` (see :func:`get_modifications`).
        - ``multimer_cardinality`` — copies of the entity, 1 when CellDesigner wrote no
          ``<celldesigner:homodimer>`` tag (see :func:`get_multimer_cardinality`).

    Notes
    -----
    Prefer this over :func:`get_modifications` when asking "does this species
    have *any* state?" or when comparing two same-named species/complexes (e.g.
    deciding whether a ``STATE_TRANSITION`` is a genuine flip or a no-op).
    """
    return {
        "structural_state": get_structural_state(species_node),
        "modifications": get_modifications(species_node),
        "multimer_cardinality": get_multimer_cardinality(species_node),
    }


def set_structural_state(
    diagram: CDDiagram,
    species_node: etree._Element,
    state: str | None,
) -> None:
    """Set the structural state on a PROTEIN or COMPLEX species.

    Parameters
    ----------
    diagram:
        The owning diagram (marked dirty on success).
    species_node:
        A ``<species>`` or ``<celldesigner:species>`` element.
    state:
        Structural state string (e.g. ``"N:3"``).
        Pass ``None`` to remove the structural state entirely.

    Raises
    ------
    ValueError
        If the species class is not PROTEIN or COMPLEX.
    RuntimeError
        If the species node has no ``speciesIdentity`` element.
    """
    cls = get_species_class(species_node)
    if cls not in ("PROTEIN", "COMPLEX"):
        raise ValueError(
            f"Structural states are only available for PROTEIN and COMPLEX species; got {cls!r}"
        )

    identity = _get_species_identity(species_node)
    if identity is None:
        raise RuntimeError("Species node has no speciesIdentity element")

    state_el = identity.find(f"{{{CD}}}state")

    if state is None:
        if state_el is not None:
            ss_list = state_el.find(f"{{{CD}}}listOfStructuralStates")
            if ss_list is not None:
                state_el.remove(ss_list)
        diagram.mark_dirty()
        return

    if state_el is None:
        state_el = etree.SubElement(identity, f"{{{CD}}}state")

    ss_list = state_el.find(f"{{{CD}}}listOfStructuralStates")
    if ss_list is None:
        ss_list = etree.SubElement(state_el, f"{{{CD}}}listOfStructuralStates")
    else:
        for child in list(ss_list):
            ss_list.remove(child)

    el = etree.SubElement(ss_list, f"{{{CD}}}structuralState")
    el.set("structuralState", state)

    diagram.mark_dirty()


# ---------------------------------------------------------------------------
# Finding species that share a protein definition
# ---------------------------------------------------------------------------

def _species_sharing_definition_ref(diagram: CDDiagram, ref_id: str) -> list[etree._Element]:
    """Return all species (top-level + included) whose definition reference matches *ref_id*."""
    sharing = []
    for sp in get_all_species(diagram) + get_included_species(diagram):
        if _get_definition_reference_id(sp, get_species_class(sp)) == ref_id:
            sharing.append(sp)
    return sharing


# ---------------------------------------------------------------------------
# Mutation — rename
# ---------------------------------------------------------------------------

def rename_species(
    diagram: CDDiagram,
    species_node: etree._Element,
    new_name: str,
) -> None:
    """Rename a species, updating both the SBML attribute and the CellDesigner
    protein/gene/RNA definition.

    If the protein definition is shared by multiple species, all instances are
    renamed simultaneously and a warning is issued.

    Parameters
    ----------
    diagram:
        The owning diagram (marked dirty on success).
    species_node:
        The ``<species>`` or ``<celldesigner:species>`` element to rename.
    new_name:
        The new display name.

    Raises
    ------
    RuntimeError
        If the rename cannot be applied cleanly.
    """
    cls = get_species_class(species_node)

    # Update SBML @name (or cd @name for included species)
    is_included = etree.QName(species_node).namespace == CD
    if is_included:
        species_node.set("name", encode_cd_name(new_name))
    else:
        species_node.set("name", new_name)

    # Update the CellDesigner definition (protein/gene/RNA/antisenseRNA)
    ref_id = _get_definition_reference_id(species_node, cls)
    if ref_id is not None:
        _rename_typed_definition(diagram, cls, ref_id, new_name)

    # Update <celldesigner:name> tag for species classes that carry one
    if cls in _CD_NAME_TAG_CLASSES:
        identity = _get_species_identity(species_node)
        if identity is not None:
            cd_name_el = identity.find(f"{{{CD}}}name")
            if cd_name_el is not None:
                cd_name_el.text = _encode_cd_tag_name(new_name)

    diagram.mark_dirty()


def _rename_typed_definition(
    diagram: CDDiagram,
    species_class: str | None,
    ref_id: str,
    new_name: str,
) -> None:
    """Update the name attribute on the CellDesigner entity definition."""
    class_to_list = {
        "PROTEIN": (f"{{{CD}}}listOfProteins", f"{{{CD}}}protein"),
        "GENE": (f"{{{CD}}}listOfGenes", f"{{{CD}}}gene"),
        "RNA": (f"{{{CD}}}listOfRNAs", f"{{{CD}}}RNA"),
        "ANTISENSE_RNA": (f"{{{CD}}}listOfAntisenseRNAs", f"{{{CD}}}antisenseRNA"),
    }
    if species_class not in class_to_list:
        return

    list_tag, item_tag = class_to_list[species_class]
    model = diagram.model
    ann = model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return
    entity_list = ext.find(list_tag)
    if entity_list is None:
        return

    for item in entity_list:
        if item.get("id") == ref_id:
            # Check how many species share this definition — warn if > 1
            sharing = _species_sharing_definition_ref(diagram, ref_id)
            if len(sharing) > 1:
                names = [s.get("name", "?") for s in sharing]
                warnings.warn(
                    f"Definition {ref_id!r} is shared by {len(sharing)} species "
                    f"({', '.join(names)}); all will be renamed to {new_name!r}.",
                    stacklevel=4,
                )
            item.set("name", new_name)
            return

    logger.warning("Definition %r not found for ref_id %r", species_class, ref_id)


# ---------------------------------------------------------------------------
# Mutation — change protein type
# ---------------------------------------------------------------------------

def change_protein_type(
    diagram: CDDiagram,
    species_node: etree._Element,
    new_type: str,
) -> None:
    """Change the protein subtype (``GENERIC``, ``RECEPTOR``, etc.).

    Parameters
    ----------
    diagram:
        The owning diagram.
    species_node:
        A PROTEIN-class species element.
    new_type:
        One of ``GENERIC``, ``ION_CHANNEL``, ``RECEPTOR``, ``TRUNCATED``.

    Raises
    ------
    ValueError
        If *new_type* is not a valid protein type, or if *species_node* is
        not a PROTEIN-class species.
    """
    if new_type not in PROTEIN_TYPES:
        raise ValueError(
            f"Invalid protein type {new_type!r}. Valid: {sorted(PROTEIN_TYPES)}"
        )
    cls = get_species_class(species_node)
    if cls != "PROTEIN":
        raise ValueError(
            f"change_protein_type requires a PROTEIN-class species; got {cls!r}"
        )
    ref_id = _get_definition_reference_id(species_node, cls)
    if ref_id is None:
        raise RuntimeError("PROTEIN species has no proteinReference")
    protein_def = _find_protein_definition(diagram, ref_id)
    if protein_def is None:
        raise RuntimeError(f"Protein definition {ref_id!r} not found in listOfProteins")
    protein_def.set("type", new_type)
    diagram.mark_dirty()


# ---------------------------------------------------------------------------
# Protein residue definitions
# ---------------------------------------------------------------------------

def get_protein_residues(
    diagram: CDDiagram,
    species_node: etree._Element,
) -> list[dict[str, str]]:
    """Return residue definitions for a PROTEIN species.

    Follows ``proteinReference`` to the protein definition in ``listOfProteins``
    and returns each ``<celldesigner:modificationResidue>`` as
    ``{"id": str, "name": str, "angle": str, "side": str}``.

    This lets callers resolve a residue ID from :func:`get_modifications` to
    its label (``name``, e.g. ``"S62"``) and its visual position (``angle`` in
    radians, ``side``).

    **The ``id`` is local to the definition; only ``name`` identifies the residue.**
    Two definitions of the same protein can label the same ``id`` differently, so
    comparing or copying modifications across definitions must go through ``name``
    (see :func:`merge_entity_definitions`).

    Returns an empty list for non-PROTEIN species or proteins with no residues.
    """
    cls = get_species_class(species_node)
    if cls != "PROTEIN":
        return []
    ref_id = _get_definition_reference_id(species_node, cls)
    if ref_id is None:
        return []
    protein_def = _find_protein_definition(diagram, ref_id)
    if protein_def is None:
        return []
    residues_list = protein_def.find(f"{{{CD}}}listOfModificationResidues")
    if residues_list is None:
        return []
    return [
        {
            "id": r.get("id", ""),
            "name": r.get("name", ""),
            "angle": r.get("angle", ""),
            "side": r.get("side", ""),
        }
        for r in residues_list
    ]


# ---------------------------------------------------------------------------
# Catalyzed reactions
# ---------------------------------------------------------------------------

def get_catalyzed_reactions(species_node: etree._Element) -> list[str]:
    """Return reaction IDs listed in ``listOfCatalyzedReactions`` for a species.

    CellDesigner maintains a back-reference on top-level species to the
    reactions they catalyse.  This reads that list.

    Returns an empty list for included species (which cannot carry this
    element) or if the list is absent.
    """
    ann = species_node.find(f"{{{SBML}}}annotation")
    if ann is None:
        return []
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return []
    cat_list = ext.find(f"{{{CD}}}listOfCatalyzedReactions")
    if cat_list is None:
        return []
    return [cat.get("reaction", "") for cat in cat_list if cat.get("reaction")]


# ---------------------------------------------------------------------------
# Complex children
# ---------------------------------------------------------------------------

def get_complex_children(
    diagram: CDDiagram,
    complex_species_node: etree._Element,
) -> list[etree._Element]:
    """Return the included species that belong to *complex_species_node*.

    Parameters
    ----------
    diagram:
        The owning diagram.
    complex_species_node:
        A top-level ``<species>`` element with class ``COMPLEX``.
    """
    complex_id = complex_species_node.get("id")
    if complex_id is None:
        return []
    result = []
    for sp in get_included_species(diagram):
        cd_ann = sp.find(f"{{{CD}}}annotation")
        if cd_ann is None:
            continue
        parent_ref = cd_ann.find(f"{{{CD}}}complexSpecies")
        if parent_ref is not None and parent_ref.text == complex_id:
            result.append(sp)
    return result


# ---------------------------------------------------------------------------
# Entity definitions (listOfProteins / listOfGenes / listOfRNAs /
# listOfAntisenseRNAs) — enumeration, orphan removal, and merging
# ---------------------------------------------------------------------------
#
# A CellDesigner diagram declares each protein/gene/RNA once in a definition
# list, and every glyph of it carries a ``*Reference`` to that declaration.
# Diagrams assembled over time accumulate *several* declarations of the same
# entity — copy-paste between files and repeated imports both cause it — so the
# same protein ends up declared many times over. The duplicates are inert but
# they make the definition list unusable as an inventory, and they hide that a
# rename through a shared definition touches every glyph using it.
#
# Merging them is only safe through the residue *label*. ``modificationResidue``
# ids (``rs2``, ``mr1``) are local to one definition: two declarations of the
# same protein routinely map the same id to different residues, so repointing a
# glyph without remapping its ``modification/@residue`` silently rewrites which
# residue is modified. These functions refuse rather than guess.

_DEFINITION_LISTS = (
    ("PROTEIN",       f"{{{CD}}}listOfProteins",       f"{{{CD}}}protein"),
    ("GENE",          f"{{{CD}}}listOfGenes",          f"{{{CD}}}gene"),
    ("RNA",           f"{{{CD}}}listOfRNAs",           f"{{{CD}}}RNA"),
    ("ANTISENSE_RNA", f"{{{CD}}}listOfAntisenseRNAs",  f"{{{CD}}}antisenseRNA"),
)


def _definition_residues(definition: etree._Element) -> dict[str, str]:
    """``{residue id: residue label}`` for one entity definition. Label may be ``""``."""
    residues = definition.find(f"{{{CD}}}listOfModificationResidues")
    if residues is None:
        return {}
    return {r.get("id", ""): r.get("name", "") for r in residues}


def _iter_definitions(diagram: CDDiagram):
    """Yield ``(species_class, list_element, definition_element)`` for every declaration."""
    ann = diagram.model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return
    for cls, list_tag, item_tag in _DEFINITION_LISTS:
        entity_list = ext.find(list_tag)
        if entity_list is None:
            continue
        for item in entity_list:
            if item.tag == item_tag:
                yield cls, entity_list, item


def _reference_element(species_node: etree._Element) -> etree._Element | None:
    """The ``<celldesigner:*Reference>`` element of a PROTEIN/GENE/RNA species."""
    ref_tag = _CLASS_REFERENCE_TAG.get(get_species_class(species_node) or "")
    if ref_tag is None:
        return None
    identity = _get_species_identity(species_node)
    if identity is None:
        return None
    return identity.find(f"{{{CD}}}{ref_tag}")


def _modification_elements(species_node: etree._Element) -> list[etree._Element]:
    """The ``<celldesigner:modification>`` elements carrying ``@residue`` for a species."""
    identity = _get_species_identity(species_node)
    if identity is None:
        return []
    state = identity.find(f"{{{CD}}}state")
    if state is None:
        return []
    mods = state.find(f"{{{CD}}}listOfModifications")
    return [] if mods is None else list(mods)


def get_entity_definitions(
    diagram: CDDiagram,
    classes: set[str] | None = None,
) -> list[dict]:
    """Inventory the CellDesigner entity definition lists (read-only).

    Returns one entry per declaration::

        {"ref_id": str, "species_class": str, "name": str, "type": str | None,
         "residues": {residue_id: residue_label},
         "species_ids": [ids of species referencing it]}

    ``name`` is decoded (CellDesigner escapes resolved). A declaration with an
    empty ``species_ids`` is an orphan — nothing in the diagram refers to it; see
    :func:`remove_unused_entity_definitions`.

    Pass *classes* to restrict to e.g. ``{"PROTEIN"}``.
    """
    referencing: dict[str, list[str]] = {}
    for sp in get_all_species(diagram) + get_included_species(diagram):
        ref = _get_definition_reference_id(sp, get_species_class(sp))
        if ref:
            referencing.setdefault(ref, []).append(sp.get("id"))

    out = []
    for cls, _list_el, definition in _iter_definitions(diagram):
        if classes is not None and cls not in classes:
            continue
        out.append({
            "ref_id": definition.get("id"),
            "species_class": cls,
            "name": decode_cd_name(definition.get("name") or ""),
            "type": definition.get("type"),
            "residues": _definition_residues(definition),
            "species_ids": referencing.get(definition.get("id"), []),
        })
    return out


def remove_unused_entity_definitions(
    diagram: CDDiagram,
    classes: set[str] | None = None,
) -> list[dict]:
    """Delete entity definitions that no species references.

    An orphaned declaration is inert — no glyph, reaction or annotation points at
    it — so removing it cannot change what the diagram states. Returns the entries
    removed, in the shape :func:`get_entity_definitions` uses. The diagram is
    marked dirty only if something was removed.
    """
    referenced = {
        _get_definition_reference_id(sp, get_species_class(sp))
        for sp in get_all_species(diagram) + get_included_species(diagram)
    }
    removed = []
    for cls, list_el, definition in list(_iter_definitions(diagram)):
        if classes is not None and cls not in classes:
            continue
        if definition.get("id") in referenced:
            continue
        removed.append({
            "ref_id": definition.get("id"),
            "species_class": cls,
            "name": decode_cd_name(definition.get("name") or ""),
            "type": definition.get("type"),
            "residues": _definition_residues(definition),
            "species_ids": [],
        })
        list_el.remove(definition)
    if removed:
        diagram.mark_dirty()
    return removed


def merge_entity_definitions(
    diagram: CDDiagram,
    keep_ref: str,
    drop_refs: list[str],
) -> dict:
    """Repoint every species from *drop_refs* onto *keep_ref*, then delete them.

    Modification residues are remapped by **label**, never by id: a residue id is
    local to its declaration, so carrying ``residue="rs2"`` across a merge can
    change which residue a glyph claims is modified. Where the two declarations
    agree id-for-id no remapping is needed; otherwise every residue a glyph
    actually uses is looked up by label in the kept declaration.

    Refuses (``ValueError``, nothing written) when:

    * the declarations differ in class, name or type — they are not the same entity;
    * a label occurs more than once in either declaration, so a lookup is ambiguous;
    * a glyph uses a residue whose label has no counterpart in the kept declaration.

    Returns ``{"kept", "dropped", "repointed", "residues_remapped"}`` where
    *repointed* lists ``(species_id, old_ref)`` and *residues_remapped* lists
    ``(species_id, old_residue_id, new_residue_id, label)``.
    """
    definitions = {d.get("id"): (cls, list_el, d)
                   for cls, list_el, d in _iter_definitions(diagram)}

    missing = [r for r in [keep_ref, *drop_refs] if r not in definitions]
    if missing:
        raise ValueError(f"no such entity definition: {missing}")

    keep_cls, _keep_list, keep_def = definitions[keep_ref]
    keep_residues = _definition_residues(keep_def)
    keep_by_label: dict[str, list[str]] = {}
    for rid, label in keep_residues.items():
        keep_by_label.setdefault(label, []).append(rid)
    ambiguous = sorted(lbl for lbl, ids in keep_by_label.items() if len(ids) > 1)
    if ambiguous:
        raise ValueError(
            f"{keep_ref} declares residue label(s) {ambiguous} more than once — "
            f"a merge cannot resolve which residue a glyph means"
        )

    # Validate every drop against the kept declaration before touching anything.
    plans: list[tuple[str, etree._Element, etree._Element, dict[str, str]]] = []
    for drop_ref in drop_refs:
        if drop_ref == keep_ref:
            raise ValueError(f"{drop_ref} is both kept and dropped")
        drop_cls, drop_list, drop_def = definitions[drop_ref]
        if (drop_cls, decode_cd_name(drop_def.get("name") or ""), drop_def.get("type")) != (
                keep_cls, decode_cd_name(keep_def.get("name") or ""), keep_def.get("type")):
            raise ValueError(
                f"{drop_ref} is not the same entity as {keep_ref}: "
                f"{drop_cls}/{drop_def.get('name')!r}/{drop_def.get('type')!r} vs "
                f"{keep_cls}/{keep_def.get('name')!r}/{keep_def.get('type')!r}"
            )
        drop_residues = _definition_residues(drop_def)
        if len(set(drop_residues.values())) != len(drop_residues):
            raise ValueError(
                f"{drop_ref} declares a residue label more than once — cannot remap"
            )
        # identical id->label maps: ids already mean the same thing, no remap needed
        remap = {} if drop_residues == keep_residues else {
            rid: keep_by_label[label][0]
            for rid, label in drop_residues.items()
            if label in keep_by_label
        }
        plans.append((drop_ref, drop_list, drop_def, remap))

        if drop_residues != keep_residues:
            for sp in _species_sharing_definition_ref(diagram, drop_ref):
                for mod in _modification_elements(sp):
                    rid = mod.get("residue", "")
                    if rid in remap:
                        continue
                    label = drop_residues.get(rid, "")
                    raise ValueError(
                        f"species {sp.get('id')!r} is modified at residue {rid!r} "
                        f"(label {label!r}) of {drop_ref}, which has no counterpart in "
                        f"{keep_ref} (labels {sorted(keep_by_label)}) — merge refused"
                    )

    repointed: list[tuple[str, str]] = []
    remapped: list[tuple[str, str, str, str]] = []
    for drop_ref, drop_list, drop_def, remap in plans:
        drop_residues = _definition_residues(drop_def)
        for sp in _species_sharing_definition_ref(diagram, drop_ref):
            for mod in _modification_elements(sp):
                rid = mod.get("residue", "")
                new_rid = remap.get(rid, rid)
                if new_rid != rid:
                    mod.set("residue", new_rid)
                    remapped.append((sp.get("id"), rid, new_rid, drop_residues.get(rid, "")))
            ref_el = _reference_element(sp)
            if ref_el is None:
                raise RuntimeError(
                    f"species {sp.get('id')!r} references {drop_ref} but has no "
                    f"reference element to repoint"
                )
            ref_el.text = keep_ref
            repointed.append((sp.get("id"), drop_ref))
        drop_list.remove(drop_def)

    diagram.mark_dirty()
    return {
        "kept": keep_ref,
        "dropped": [p[0] for p in plans],
        "repointed": repointed,
        "residues_remapped": remapped,
    }


# ---------------------------------------------------------------------------
# Removing species
# ---------------------------------------------------------------------------
#
# A top-level species is more than its <species> element: it has one or more aliases
# (glyphs), a complex owns included species and their aliases (possibly nested
# complexes), and alias groups list member aliases by id. Removing only the <species>
# leaves aliases pointing at nothing, which CellDesigner and MINERVA reject. Entity
# definitions are left to remove_unused_entity_definitions.

def _complex_members(diagram: CDDiagram) -> dict[str, list[str]]:
    """``{complex species id: [ids of included species directly inside it]}``."""
    members: dict[str, list[str]] = {}
    for sp in get_included_species(diagram):
        ann = sp.find(f"{{{CD}}}annotation")
        ref = ann.find(f"{{{CD}}}complexSpecies") if ann is not None else None
        if ref is not None and ref.text:
            members.setdefault(ref.text, []).append(sp.get("id"))
    return members


def _with_members(species_id: str, members: dict[str, list[str]]) -> set[str]:
    """*species_id* plus every included species nested inside it, at any depth."""
    out, stack = set(), [species_id]
    while stack:
        sid = stack.pop()
        if sid not in out:
            out.add(sid)
            stack.extend(members.get(sid, []))
    return out


def _delete_species(diagram: CDDiagram, top_ids: set[str]) -> dict[str, list[str]]:
    """Remove the given top-level species with their members, aliases and group entries.
    Callers have already checked that nothing references them."""
    from .layout import _get_extension

    members = _complex_members(diagram)
    included_ids = set().union(*(_with_members(s, members) for s in top_ids)) - top_ids
    all_ids = top_ids | included_ids
    removed = {"species": [], "included_species": [], "aliases": []}

    ext = _get_extension(diagram)
    if ext is not None:
        for list_tag in ("listOfSpeciesAliases", "listOfComplexSpeciesAliases"):
            alias_list = ext.find(f"{{{CD}}}{list_tag}")
            if alias_list is None:
                continue
            for alias in list(alias_list):
                if alias.get("species") in all_ids:
                    removed["aliases"].append(alias.get("id"))
                    alias_list.remove(alias)
        gone = set(removed["aliases"])
        groups = ext.find(f"{{{CD}}}listOfGroups")
        if groups is not None and gone:
            for group in list(groups):
                kept = [m for m in (group.get("members") or "").split(",") if m and m not in gone]
                if kept:
                    group.set("members", ",".join(kept))
                else:
                    groups.remove(group)
        included_list = ext.find(f"{{{CD}}}listOfIncludedSpecies")
        if included_list is not None:
            for sp in list(included_list):
                if sp.get("id") in included_ids:
                    removed["included_species"].append(sp.get("id"))
                    included_list.remove(sp)

    species_list = diagram.model.find(f"{{{SBML}}}listOfSpecies")
    for sp in list(species_list) if species_list is not None else []:
        if sp.get("id") in top_ids:
            removed["species"].append(sp.get("id"))
            species_list.remove(sp)

    if any(removed.values()):
        diagram.mark_dirty()
    return removed


def remove_species(diagram: CDDiagram, species_node: etree._Element) -> dict[str, list[str]]:
    """Delete a top-level species together with its aliases and, for a complex, every
    included species (at any depth) and their aliases. Alias-group memberships are
    pruned; a group left empty is removed.

    Run :func:`remove_unused_entity_definitions` afterwards to drop the protein/gene/RNA
    declarations nothing refers to any more.

    Returns ``{"species": [...], "included_species": [...], "aliases": [...]}`` (ids).

    Raises
    ------
    ValueError
        If *species_node* is not a top-level species of *diagram* (a complex member is
        removed by editing or removing its complex), or if any reaction still refers to
        it or to one of its members — remove those reactions first. Nothing is written.
    """
    from .reactions import get_all_reactions, get_reaction_species_ids

    species_list = diagram.model.find(f"{{{SBML}}}listOfSpecies")
    if species_list is None or species_node.getparent() is not species_list:
        raise ValueError(
            f"{species_node.get('id')!r} is not a top-level species of this diagram")
    sid = species_node.get("id")
    family = _with_members(sid, _complex_members(diagram))
    in_use = [r.get("id") for r in get_all_reactions(diagram)
              if get_reaction_species_ids(r) & family]
    if in_use:
        raise ValueError(f"{sid!r} still takes part in reaction(s) {in_use}")
    return _delete_species(diagram, {sid})


def remove_orphaned_species(
    diagram: CDDiagram,
    keep: set[str] | None = None,
) -> dict[str, list[str]]:
    """Remove every top-level species that takes part in no reaction, as
    :func:`remove_species` would. A complex counts as used when any of its members
    is in a reaction. Species ids in *keep* are left alone.

    Returns the removed ids in the shape :func:`remove_species` uses.
    """
    from .reactions import get_all_reactions, get_reaction_species_ids

    keep = keep or set()
    used: set[str] = set()
    for r in get_all_reactions(diagram):
        used |= get_reaction_species_ids(r)
    members = _complex_members(diagram)
    orphans = {sp.get("id") for sp in get_all_species(diagram)
               if sp.get("id") not in keep and not (_with_members(sp.get("id"), members) & used)}
    return _delete_species(diagram, orphans)
