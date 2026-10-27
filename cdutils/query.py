"""Filtering and search functions across diagram components."""

from __future__ import annotations

from lxml import etree

from .annotations import get_annotations, parse_miriam_uri
from .compartments import get_all_compartments
from .io import CDDiagram
from .namespaces import IDENTITY_NAMESPACES, SBML
from .reactions import get_all_reactions, get_reaction_type
from .species import (
    get_all_species,
    get_included_species,
    get_protein_type,
    get_species_class,
    get_species_name,
    get_species_state,
)


def find_by_name(
    diagram: CDDiagram,
    name: str,
    exact: bool = True,
) -> list[etree._Element]:
    """Find species by name in both top-level and included species.

    Parameters
    ----------
    diagram:
        The diagram to search.
    name:
        Name to match against the ``@name`` attribute.
    exact:
        If ``True`` (default), require an exact match.  If ``False``,
        match any species whose name contains *name* as a substring
        (case-sensitive).

    Returns
    -------
    List of matching species elements.
    """
    result = []
    for sp in get_all_species(diagram) + get_included_species(diagram):
        sp_name = sp.get("name", "")
        if exact:
            if sp_name == name:
                result.append(sp)
        else:
            if name in sp_name:
                result.append(sp)
    return result


def find_by_class(diagram: CDDiagram, class_name: str) -> list[etree._Element]:
    """Return top-level species whose CellDesigner class matches *class_name*.

    Parameters
    ----------
    diagram:
        The diagram to search.
    class_name:
        Species class string, e.g. ``"PROTEIN"``, ``"COMPLEX"``.

    Notes
    -----
    Only top-level species are searched.  Included species are always of a
    typed class (PROTEIN, GENE, …) but are not returned here — use
    :func:`get_included_species` and filter manually if needed.
    """
    return [
        sp for sp in get_all_species(diagram)
        if get_species_class(sp) == class_name
    ]


def find_by_annotation(
    diagram: CDDiagram,
    namespace: str,
    identifier: str | None = None,
) -> list[etree._Element]:
    """Return all components (species, reactions, compartments) that carry an
    annotation matching *namespace* (and optionally *identifier*).

    Checks both ``<annotation>`` and ``<celldesigner:notes>`` RDF blocks, so
    included species are covered transparently.

    Parameters
    ----------
    diagram:
        The diagram to search.
    namespace:
        MIRIAM namespace prefix, e.g. ``"uniprot"``.
    identifier:
        Optional identifier value.  If ``None``, any identifier in
        *namespace* matches.

    Returns
    -------
    List of matching lxml elements (may be species, reactions, or compartments).
    """
    result = []
    candidates = (
        get_all_species(diagram)
        + get_included_species(diagram)
        + get_all_reactions(diagram)
        + get_all_compartments(diagram)
    )
    for element in candidates:
        anns = get_annotations(element)
        for uris in anns.values():
            for uri in uris:
                try:
                    ns, ident = parse_miriam_uri(uri)
                except ValueError:
                    continue
                if ns == namespace and (identifier is None or ident == identifier):
                    result.append(element)
                    break
            else:
                continue
            break
    return result


def find_by_protein_type(diagram: CDDiagram, protein_type: str) -> list[etree._Element]:
    """Return top-level PROTEIN-class species with the given protein subtype.

    Parameters
    ----------
    diagram:
        The diagram to search.
    protein_type:
        One of ``"GENERIC"``, ``"RECEPTOR"``, ``"ION_CHANNEL"``, ``"TRUNCATED"``.
    """
    return [
        sp for sp in get_all_species(diagram)
        if get_species_class(sp) == "PROTEIN"
        and get_protein_type(diagram, sp) == protein_type
    ]


def find_by_reaction_type(diagram: CDDiagram, reaction_type: str) -> list[etree._Element]:
    """Return all reactions with the given CellDesigner reaction type.

    Parameters
    ----------
    diagram:
        The diagram to search.
    reaction_type:
        E.g. ``"STATE_TRANSITION"``, ``"HETERODIMER_ASSOCIATION"``.
    """
    return [
        r for r in get_all_reactions(diagram)
        if get_reaction_type(r) == reaction_type
    ]


# ---------------------------------------------------------------------------
# Cross-diagram equivalence
# ---------------------------------------------------------------------------

def _uri_sets(annotations: dict) -> tuple[set[str], set[str]]:
    """Return ``(all_uris, identity_uris)`` from a ``get_annotations`` dict.

    ``identity_uris`` are those whose MIRIAM namespace is in
    ``IDENTITY_NAMESPACES`` (uniprot, obo.go, …) — the strong equivalence
    evidence; taxonomy/literature URIs are shared by many species and only
    weakly informative.
    """
    all_uris: set[str] = set()
    identity: set[str] = set()
    for uris in annotations.values():
        for uri in uris:
            all_uris.add(uri)
            try:
                ns, _ = parse_miriam_uri(uri)
            except ValueError:
                continue
            if ns in IDENTITY_NAMESPACES:
                identity.add(uri)
    return all_uris, identity


def _state_key(state: dict) -> tuple:
    """Order-independent comparable key for a ``get_species_state`` dict.

    Includes multimer cardinality: a monomer and a trimer of the same protein are different
    species, and leaving it out would let :func:`find_equivalent_species` match them.
    """
    mods = frozenset((m.get("residue", ""), m.get("state", "")) for m in state["modifications"])
    return (state["structural_state"], mods, state.get("multimer_cardinality", 1))


def find_equivalent_species(
    source_diagram: CDDiagram,
    source_species: etree._Element,
    target_diagram: CDDiagram,
    *,
    require_annotation: bool = True,
    use_state: bool = True,
) -> list[dict]:
    """Find species in *target_diagram* equivalent to *source_species*.

    SBML IDs are **not** comparable across diagrams, so equivalence is assessed
    on the combination of **canonical decoded name** (:func:`get_species_name`)
    and **shared identity annotations** (uniprot, obo.go, …), with **species
    state** (modifications + structural state, :func:`get_species_state`) as
    supporting evidence.  Both top-level and included species in the target are
    considered.

    Parameters
    ----------
    source_diagram, source_species:
        The species to match, and its owning diagram (needed to resolve the
        name via shared definitions).
    target_diagram:
        The diagram to search.
    require_annotation:
        If ``True`` (default), only return candidates that share at least one
        **identity** annotation with the source.  If ``False``, a candidate also
        qualifies on an exact canonical-name match alone (use when the source
        carries no identity annotation).
    use_state:
        If ``True`` (default), compare species state; a match adds to the score
        and is reported as ``state_match``.

    Returns
    -------
    list[dict], best match first, each:
        ``species`` (node), ``species_id``, ``name`` (candidate canonical name),
        ``name_match`` (bool), ``shared_annotations`` (sorted shared MIRIAM
        URIs), ``shared_identity`` (the identity subset), ``state_match`` (bool),
        ``score`` (float — 3·identity + 1·other + 2·name + 0.5·state).

    Notes
    -----
    A heuristic aid, not an oracle: verify a proposed equivalence before acting,
    especially where name and annotations disagree.
    """
    src_name = get_species_name(source_diagram, source_species)
    src_all, src_identity = _uri_sets(get_annotations(source_species))
    src_state_key = _state_key(get_species_state(source_species)) if use_state else None

    results: list[dict] = []
    for cand in get_all_species(target_diagram) + get_included_species(target_diagram):
        if cand is source_species:
            continue

        cand_name = get_species_name(target_diagram, cand)
        name_match = bool(src_name) and src_name == cand_name

        cand_all, cand_identity = _uri_sets(get_annotations(cand))
        shared = src_all & cand_all
        shared_identity = src_identity & cand_identity
        shared_other = shared - shared_identity

        qualifies = bool(shared_identity) or (name_match and not require_annotation)
        if not qualifies:
            continue

        state_match = bool(
            use_state and src_state_key is not None
            and src_state_key == _state_key(get_species_state(cand))
        )

        score = (
            3 * len(shared_identity)
            + len(shared_other)
            + (2 if name_match else 0)
            + (0.5 if state_match else 0)
        )
        results.append({
            "species": cand,
            "species_id": cand.get("id", ""),
            "name": cand_name,
            "name_match": name_match,
            "shared_annotations": sorted(shared),
            "shared_identity": sorted(shared_identity),
            "state_match": state_match,
            "score": score,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results
