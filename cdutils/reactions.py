"""Operations on CellDesigner reactions."""

from __future__ import annotations

from lxml import etree

from .namespaces import CD, REACTION_TYPES, SBML
from .io import CDDiagram


def get_all_reactions(diagram: CDDiagram) -> list[etree._Element]:
    """Return all ``<reaction>`` elements from ``listOfReactions``."""
    model = diagram.model
    reaction_list = model.find(f"{{{SBML}}}listOfReactions")
    if reaction_list is None:
        return []
    return list(reaction_list)


def get_reaction_type(reaction_node: etree._Element) -> str | None:
    """Return the CellDesigner reaction type string, e.g. ``"STATE_TRANSITION"``."""
    ann = reaction_node.find(f"{{{SBML}}}annotation")
    if ann is None:
        return None
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return None
    rtype = ext.find(f"{{{CD}}}reactionType")
    return rtype.text if rtype is not None else None


def get_participants(reaction_node: etree._Element) -> dict[str, list[dict[str, str]]]:
    """Return the reactants, products, and modifiers of a reaction.

    Returns
    -------
    dict with keys ``"reactants"``, ``"products"``, ``"modifiers"``.
    Reactant and product entries: ``{"species_id": str, "alias_id": str}``.
    Modifier entries add ``"modifier_type"`` (e.g. ``"CATALYSIS"``,
    ``"INHIBITION"``; empty string if not found in the CD extension).
    """
    result: dict[str, list[dict[str, str]]] = {
        "reactants": [],
        "products": [],
        "modifiers": [],
    }

    def _alias_id_from_ref(ref: etree._Element) -> str:
        ann = ref.find(f"{{{SBML}}}annotation")
        if ann is None:
            return ""
        ext = ann.find(f"{{{CD}}}extension")
        if ext is None:
            return ""
        alias_el = ext.find(f"{{{CD}}}alias")
        return alias_el.text if alias_el is not None else ""

    def _parse_refs(parent_tag: str, key: str) -> None:
        lst = reaction_node.find(f"{{{SBML}}}{parent_tag}")
        if lst is None:
            return
        for ref in lst:
            result[key].append({
                "species_id": ref.get("species", ""),
                "alias_id": _alias_id_from_ref(ref),
            })

    _parse_refs("listOfReactants", "reactants")
    _parse_refs("listOfProducts", "products")

    # Build modifier-type lookup from celldesigner:listOfModification.
    # @modifiers and @aliases may be comma-separated (boolean gate inputs).
    cd_modifier_types: dict[tuple[str, str], str] = {}
    reaction_ann = reaction_node.find(f"{{{SBML}}}annotation")
    if reaction_ann is not None:
        reaction_ext = reaction_ann.find(f"{{{CD}}}extension")
        if reaction_ext is not None:
            cd_mod_list = reaction_ext.find(f"{{{CD}}}listOfModification")
            if cd_mod_list is not None:
                for mod in cd_mod_list:
                    mtype = mod.get("type", "")
                    sids = [s.strip() for s in mod.get("modifiers", "").split(",") if s.strip()]
                    aids = [a.strip() for a in mod.get("aliases", "").split(",") if a.strip()]
                    for sid, aid in zip(sids, aids):
                        cd_modifier_types[(sid, aid)] = mtype

    sbml_modifiers = reaction_node.find(f"{{{SBML}}}listOfModifiers")
    if sbml_modifiers is not None:
        for ref in sbml_modifiers:
            species_id = ref.get("species", "")
            alias_id = _alias_id_from_ref(ref)
            modifier_type = cd_modifier_types.get((species_id, alias_id), "")
            result["modifiers"].append({
                "species_id": species_id,
                "alias_id": alias_id,
                "modifier_type": modifier_type,
            })

    return result


def change_reaction_type(
    diagram: CDDiagram,
    reaction_node: etree._Element,
    new_type: str,
) -> None:
    """Change the reaction type within the set of valid CellDesigner reaction types.

    Parameters
    ----------
    diagram:
        The owning diagram (marked dirty on success).
    reaction_node:
        The ``<reaction>`` element to modify.
    new_type:
        A valid CellDesigner reaction type string.

    Raises
    ------
    ValueError
        If *new_type* is not recognised.
    RuntimeError
        If the ``<celldesigner:reactionType>`` element cannot be located.
    """
    if new_type not in REACTION_TYPES:
        raise ValueError(
            f"Invalid reaction type {new_type!r}. Valid types: {sorted(REACTION_TYPES)}"
        )
    ann = reaction_node.find(f"{{{SBML}}}annotation")
    if ann is None:
        raise RuntimeError("Reaction has no <annotation> element")
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        raise RuntimeError("Reaction annotation has no <celldesigner:extension>")
    rtype = ext.find(f"{{{CD}}}reactionType")
    if rtype is None:
        raise RuntimeError("Reaction has no <celldesigner:reactionType> element")
    rtype.text = new_type
    diagram.mark_dirty()


# ---------------------------------------------------------------------------
# Participants as a network
# ---------------------------------------------------------------------------

def get_reaction_species_ids(reaction_node: etree._Element) -> set[str]:
    """Every species id *reaction_node* refers to — reactants, products, modifiers,
    Boolean-gate inputs and reactant/product links, top-level or included.

    Read from both the SBML lists and the CellDesigner extension, since a reaction can
    point at a complex member (an included species) that SBML never lists.
    """
    ids: set[str] = set()
    for el in reaction_node.iter():
        if not isinstance(el.tag, str):
            continue
        # reactant/product: the species of a reactantLink/productLink (an extra reactant or
        # product); SBML lists them too, but a hand-edited file need not
        for attr in ("species", "reactant", "product", "modifiers"):
            value = el.get(attr)
            if value:
                ids.update(v.strip() for v in value.split(",") if v.strip())
    return ids


def get_species_reactions(diagram: CDDiagram, species_id: str) -> list[etree._Element]:
    """Return the reactions in which *species_id* takes part in any role."""
    return [r for r in get_all_reactions(diagram) if species_id in get_reaction_species_ids(r)]


def get_connected_components(
    diagram: CDDiagram,
    exclude_reactions: set[str] | None = None,
) -> list[set[str]]:
    """Connected components of the species–reaction network, largest first.

    Each component is a set of top-level species ids; two species are connected when a
    reaction links them in any role (direction ignored). A reaction touching a complex
    member counts for its top-level complex. Species in no reaction are singletons.

    Pass *exclude_reactions* (reaction ids) to see the network as it would be after
    removing them — check what a removal disconnects before making it.
    """
    from .species import get_all_species, get_included_species

    exclude_reactions = exclude_reactions or set()
    parent: dict[str, str] = {}
    for sp in get_included_species(diagram):
        ann = sp.find(f"{{{CD}}}annotation")
        ref = ann.find(f"{{{CD}}}complexSpecies") if ann is not None else None
        if ref is not None and ref.text:
            parent[sp.get("id")] = ref.text

    def top(species_id: str) -> str:
        seen = set()
        while species_id in parent and species_id not in seen:
            seen.add(species_id)
            species_id = parent[species_id]
        return species_id

    adjacency: dict[str, set[str]] = {sp.get("id"): set() for sp in get_all_species(diagram)}
    for r in get_all_reactions(diagram):
        if r.get("id") in exclude_reactions:
            continue
        members = {top(s) for s in get_reaction_species_ids(r)} & adjacency.keys()
        for s in members:
            adjacency[s] |= members - {s}

    components, seen = [], set()
    for start in adjacency:
        if start in seen:
            continue
        stack, component = [start], set()
        seen.add(start)
        while stack:
            node = stack.pop()
            component.add(node)
            for nxt in adjacency[node] - seen:
                seen.add(nxt)
                stack.append(nxt)
        components.append(component)
    components.sort(key=len, reverse=True)
    return components


# ---------------------------------------------------------------------------
# Removing and adding reactions
# ---------------------------------------------------------------------------

def remove_reaction(diagram: CDDiagram, reaction_node: etree._Element) -> None:
    """Delete *reaction_node* and the back-references CellDesigner keeps to it.

    Top-level species list the reactions they catalyse in
    ``listOfCatalyzedReactions``; entries naming this reaction are dropped, and a list
    left empty is removed. The species themselves stay, even if now unconnected —
    see :func:`cdutils.species.remove_orphaned_species`.

    Raises
    ------
    ValueError
        If *reaction_node* is not a reaction of *diagram*.
    """
    reaction_list = diagram.model.find(f"{{{SBML}}}listOfReactions")
    if reaction_list is None or reaction_node.getparent() is not reaction_list:
        raise ValueError(f"Reaction {reaction_node.get('id')!r} is not part of this diagram")
    rid = reaction_node.get("id")

    from .species import get_all_species
    for sp in get_all_species(diagram):
        cat_list = sp.find(f"{{{SBML}}}annotation/{{{CD}}}extension/{{{CD}}}listOfCatalyzedReactions")
        if cat_list is None:
            continue
        for cat in list(cat_list):
            if cat.get("reaction") == rid:
                cat_list.remove(cat)
        if len(cat_list) == 0:
            cat_list.getparent().remove(cat_list)

    reaction_list.remove(reaction_node)
    diagram.mark_dirty()


def _all_ids(diagram: CDDiagram) -> set[str]:
    return {v for el in diagram.root.iter() if isinstance(el.tag, str)
            for k, v in el.attrib.items() if k in ("id", "metaid")}


def _closest_aliases(diagram: CDDiagram, reactant_id: str, product_id: str) -> tuple[str, str]:
    """The (reactant alias, product alias) pair whose centres are nearest — where a
    curator would draw the arc when either species is shown more than once."""
    from .layout import get_aliases_for_species, get_bounds

    def centres(species_id):
        out = []
        for a in get_aliases_for_species(diagram, species_id):
            b = get_bounds(a)
            out.append((a.get("id"), (b[0] + b[2] / 2, b[1] + b[3] / 2) if b else (0.0, 0.0)))
        return out

    ra, pa = centres(reactant_id), centres(product_id)
    if not ra or not pa:
        missing = reactant_id if not ra else product_id
        raise ValueError(f"Species {missing!r} has no alias to draw a reaction from")
    best = min(((r, p) for r in ra for p in pa),
               key=lambda rp: (rp[0][1][0] - rp[1][1][0]) ** 2 + (rp[0][1][1] - rp[1][1][1]) ** 2)
    return best[0][0], best[1][0]


def add_reaction(
    diagram: CDDiagram,
    reactant_id: str,
    product_id: str,
    reaction_type: str,
    reactant_alias: str | None = None,
    product_alias: str | None = None,
    reaction_id: str | None = None,
) -> etree._Element:
    """Add a one-reactant, one-product reaction between two existing top-level species.

    Written in the layout CellDesigner itself uses for a straight, unmodified arc. Without
    explicit aliases, the nearest pair of the two species' aliases is used. The reaction
    is appended to ``listOfReactions`` with a fresh id, and returned so it can be annotated
    (:func:`~cdutils.annotations.add_annotation`, :func:`~cdutils.annotations.set_notes_text`).

    Raises
    ------
    ValueError
        If the type is unknown or a Boolean gate (gates need inputs this cannot express),
        a species is missing or included in a complex, an alias does not belong to its
        species, reactant and product are the same species, or *reaction_id* is taken.
        Nothing is written in that case.
    """
    from .layout import get_alias_by_id
    from .species import get_all_species

    if reaction_type not in REACTION_TYPES or reaction_type.startswith("BOOLEAN_LOGIC_GATE"):
        raise ValueError(f"Cannot add a reaction of type {reaction_type!r}")
    if reactant_id == product_id:
        raise ValueError("Reactant and product are the same species")
    top_level = {sp.get("id") for sp in get_all_species(diagram)}
    for sid in (reactant_id, product_id):
        if sid not in top_level:
            raise ValueError(f"{sid!r} is not a top-level species of this diagram")

    if reactant_alias is None or product_alias is None:
        near_r, near_p = _closest_aliases(diagram, reactant_id, product_id)
        reactant_alias = reactant_alias or near_r
        product_alias = product_alias or near_p
    for sid, aid in ((reactant_id, reactant_alias), (product_id, product_alias)):
        alias = get_alias_by_id(diagram, aid)
        if alias is None or alias.get("species") != sid:
            raise ValueError(f"Alias {aid!r} does not belong to species {sid!r}")

    taken = _all_ids(diagram)
    if reaction_id is None:
        n = 1
        while f"cdu_re{n}" in taken:
            n += 1
        reaction_id = f"cdu_re{n}"
    elif reaction_id in taken:
        raise ValueError(f"Id {reaction_id!r} is already used in this diagram")

    E = lambda tag, parent=None, **attrs: (
        etree.SubElement(parent, tag, attrs) if parent is not None else etree.Element(tag, attrs))
    r = E(f"{{{SBML}}}reaction", metaid=reaction_id, id=reaction_id, reversible="false")
    ext = E(f"{{{CD}}}extension", E(f"{{{SBML}}}annotation", r))
    E(f"{{{CD}}}reactionType", ext).text = reaction_type
    E(f"{{{CD}}}baseReactant", E(f"{{{CD}}}baseReactants", ext),
      species=reactant_id, alias=reactant_alias)
    E(f"{{{CD}}}baseProduct", E(f"{{{CD}}}baseProducts", ext),
      species=product_id, alias=product_alias)
    scheme = E(f"{{{CD}}}connectScheme", ext, connectPolicy="direct")
    E(f"{{{CD}}}lineDirection", E(f"{{{CD}}}listOfLineDirection", scheme),
      index="0", value="unknown")
    E(f"{{{CD}}}line", ext, width="1.0", color="ff000000")
    for list_tag, sid, aid in (("listOfReactants", reactant_id, reactant_alias),
                               ("listOfProducts", product_id, product_alias)):
        ref = E(f"{{{SBML}}}speciesReference", E(f"{{{SBML}}}{list_tag}", r), species=sid)
        E(f"{{{CD}}}alias", E(f"{{{CD}}}extension", E(f"{{{SBML}}}annotation", ref))).text = aid

    reaction_list = diagram.model.find(f"{{{SBML}}}listOfReactions")
    if reaction_list is None:
        # SBML order: listOfSpecies … listOfReactions … listOfEvents
        reaction_list = etree.Element(f"{{{SBML}}}listOfReactions")
        species_list = diagram.model.find(f"{{{SBML}}}listOfSpecies")
        if species_list is not None:
            species_list.addnext(reaction_list)
        else:
            diagram.model.append(reaction_list)
    reaction_list.append(r)
    diagram.mark_dirty()
    return r


# ---------------------------------------------------------------------------
# Repointing a participant
# ---------------------------------------------------------------------------

# Attributes holding exactly one species id, each paired with an ``alias`` attribute on the
# same element: base reactants/products, link targets, reactant/product links.
_SINGLE_SPECIES_ATTRS = ("species", "reactant", "product")


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",")]


def replace_reaction_species(
    diagram: CDDiagram,
    reaction_node: etree._Element,
    old_species_id: str,
    new_species_id: str,
    new_alias: str | None = None,
) -> int:
    """Make *reaction_node* refer to *new_species_id* wherever it refers to *old_species_id*.

    Every role is covered — reactant, product, modifier, Boolean-gate input, reactant/product
    link — in both the SBML lists and the CellDesigner extension, and the arc is redrawn to a
    glyph of the new species: *new_alias*, or by default the new species' glyph nearest to
    the old one. A catalysis back-reference (``listOfCatalyzedReactions``) moves to the new
    species. The old species is left in place, possibly unconnected — see
    :func:`cdutils.species.remove_orphaned_species`. Typical use: point a reaction at the
    human species instead of its mouse orthologue.

    Returns the number of references rewritten.

    Raises
    ------
    ValueError
        If the reaction is not part of *diagram*, does not involve *old_species_id*, the new
        species is not a top-level species of *diagram* (or is the old one), it already takes
        part in the reaction (the result would link a species to itself), or *new_alias* is
        not one of its glyphs. Nothing is written.
    """
    from .layout import get_alias_by_id, get_aliases_for_species, get_bounds
    from .species import get_all_species

    reaction_list = diagram.model.find(f"{{{SBML}}}listOfReactions")
    if reaction_list is None or reaction_node.getparent() is not reaction_list:
        raise ValueError(f"Reaction {reaction_node.get('id')!r} is not part of this diagram")
    rid = reaction_node.get("id")
    participants = get_reaction_species_ids(reaction_node)
    if old_species_id not in participants:
        raise ValueError(f"Reaction {rid!r} does not involve {old_species_id!r}")
    if new_species_id == old_species_id:
        raise ValueError("Old and new species are the same")
    top_level = {sp.get("id"): sp for sp in get_all_species(diagram)}
    if new_species_id not in top_level:
        raise ValueError(f"{new_species_id!r} is not a top-level species of this diagram")
    if new_species_id in participants:
        raise ValueError(f"{new_species_id!r} already takes part in reaction {rid!r}")

    # glyphs of the old species this reaction is drawn to
    old_aliases: set[str] = set()
    for el in reaction_node.iter():
        if not isinstance(el.tag, str):
            continue
        if old_species_id in (el.get(a) for a in _SINGLE_SPECIES_ATTRS) and el.get("alias"):
            old_aliases.add(el.get("alias"))
        if el.get("modifiers"):
            old_aliases.update(a for m, a in zip(_split(el.get("modifiers")), _split(el.get("aliases")))
                               if m == old_species_id and a)

    if new_alias is None:
        def centre(alias):
            b = get_bounds(alias) if alias is not None else None
            return (b[0] + b[2] / 2, b[1] + b[3] / 2) if b else (0.0, 0.0)
        anchors = [centre(get_alias_by_id(diagram, a)) for a in old_aliases] or [(0.0, 0.0)]
        candidates = get_aliases_for_species(diagram, new_species_id)
        if not candidates:
            raise ValueError(f"Species {new_species_id!r} has no glyph to draw the reaction to")
        ax, ay = anchors[0]
        new_alias = min(candidates, key=lambda a: (centre(a)[0] - ax) ** 2 + (centre(a)[1] - ay) ** 2
                        ).get("id")
    alias_el = get_alias_by_id(diagram, new_alias)
    if alias_el is None or alias_el.get("species") != new_species_id:
        raise ValueError(f"Alias {new_alias!r} does not belong to species {new_species_id!r}")

    changed = 0
    for el in reaction_node.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in _SINGLE_SPECIES_ATTRS:
            if el.get(attr) == old_species_id:
                el.set(attr, new_species_id)
                changed += 1
                if el.get("alias") in old_aliases:
                    el.set("alias", new_alias)
        if el.get("modifiers"):
            mods, aliases = _split(el.get("modifiers")), _split(el.get("aliases"))
            if old_species_id in mods:
                for i, m in enumerate(mods):
                    if m == old_species_id:
                        mods[i] = new_species_id
                        if i < len(aliases):
                            aliases[i] = new_alias
                        changed += 1
                el.set("modifiers", ",".join(mods))
                if el.get("aliases") is not None:
                    el.set("aliases", ",".join(aliases))
        elif el.get("aliases") and etree.QName(el).localname == "GateMember":
            gate = _split(el.get("aliases"))
            if old_aliases & set(gate):
                el.set("aliases", ",".join(new_alias if a in old_aliases else a for a in gate))
                changed += 1
        if etree.QName(el).localname == "alias" and etree.QName(el).namespace == CD \
                and (el.text or "").strip() in old_aliases:
            el.text = new_alias

    # catalysis back-reference follows the catalyst
    def catalysed_list(sp, create=False):
        ext = sp.find(f"{{{SBML}}}annotation/{{{CD}}}extension")
        lst = ext.find(f"{{{CD}}}listOfCatalyzedReactions") if ext is not None else None
        if lst is None and create and ext is not None:
            lst = etree.Element(f"{{{CD}}}listOfCatalyzedReactions")
            identity = ext.find(f"{{{CD}}}speciesIdentity")
            if identity is not None:
                identity.addnext(lst)
            else:
                ext.append(lst)
        return lst

    old_sp = top_level.get(old_species_id)
    old_list = catalysed_list(old_sp) if old_sp is not None else None
    if old_list is not None and any(c.get("reaction") == rid for c in old_list):
        for c in list(old_list):
            if c.get("reaction") == rid:
                old_list.remove(c)
        if len(old_list) == 0:
            old_list.getparent().remove(old_list)
        new_list = catalysed_list(top_level[new_species_id], create=True)
        if new_list is not None and not any(c.get("reaction") == rid for c in new_list):
            etree.SubElement(new_list, f"{{{CD}}}catalyzed", reaction=rid)

    diagram.mark_dirty()
    return changed
