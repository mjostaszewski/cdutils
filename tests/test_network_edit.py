#!/usr/bin/env python3
"""Network editing — removing and adding reactions, removing species, connectivity.

These are the operations the AD knowledge-graph review needs: drop reactions without
admissible evidence, clear the species they leave unconnected, add replacement reactions,
and check beforehand what a removal disconnects. The common failure is a *dangling
reference* — an alias, group, catalysis back-reference or reaction pointing at something
removed — which CellDesigner and MINERVA reject, so every editing test ends with a
whole-diagram reference check rather than only looking at the element it touched.
"""
import os
import socket
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree

from cdutils import (load_diagram, save_diagram, get_all_reactions, get_all_species,
                     get_included_species, get_participants, get_reaction_type,
                     change_reaction_type, get_reaction_species_ids, get_species_reactions,
                     get_connected_components, remove_reaction, add_reaction,
                     remove_species, remove_orphaned_species, remove_unused_entity_definitions,
                     get_species_name, get_aliases_for_species, get_catalyzed_reactions,
                     add_annotation, get_annotations, set_notes_text, get_notes_text,
                     validate_xml_bytes)
from cdutils.namespaces import CD

PD = "/workspace/pdmap/submaps"
AUTOPHAGY = f"{PD}/Autophagy.xml"          # has listOfCatalyzedReactions back-references
IRON = f"{PD}/Iron metabolism.xml"         # reactions that point at complex members
AD_KG = "/workspace/sandbox/pdmap-expansion/ad-interaction/ad_kg.xml"
passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def dangling(d):
    """Every id reference in the diagram that no longer resolves."""
    species = {s.get("id") for s in get_all_species(d)} | \
              {s.get("id") for s in get_included_species(d)}
    reactions = {r.get("id") for r in get_all_reactions(d)}
    ext = d.model.find(f"{{http://www.sbml.org/sbml/level2/version4}}annotation/{{{CD}}}extension")
    aliases = {a.get("id") for tag in ("listOfSpeciesAliases", "listOfComplexSpeciesAliases")
               for a in ext.find(f"{{{CD}}}{tag}")}
    bad = []
    for tag in ("listOfSpeciesAliases", "listOfComplexSpeciesAliases"):
        for a in ext.find(f"{{{CD}}}{tag}"):
            if a.get("species") not in species:
                bad.append(("alias->species", a.get("id")))
            if a.get("complexSpeciesAlias") and a.get("complexSpeciesAlias") not in aliases:
                bad.append(("alias->complex alias", a.get("id")))
    for s in get_included_species(d):
        ref = s.find(f"{{{CD}}}annotation/{{{CD}}}complexSpecies")
        if ref is not None and ref.text not in species:
            bad.append(("included->complex", s.get("id")))
    for r in get_all_reactions(d):
        missing = get_reaction_species_ids(r) - species
        if missing:
            bad.append(("reaction->species", r.get("id"), sorted(missing)))
        for el in r.iter(f"{{{CD}}}*"):
            if el.get("alias") and el.get("alias") not in aliases:
                bad.append(("reaction->alias", r.get("id")))
    for s in get_all_species(d):
        for rid in get_catalyzed_reactions(s):
            if rid not in reactions:
                bad.append(("catalysed->reaction", s.get("id"), rid))
    groups = ext.find(f"{{{CD}}}listOfGroups")
    for g in (groups if groups is not None else []):
        for m in (g.get("members") or "").split(","):
            if m and m not in aliases:
                bad.append(("group->alias", g.get("id"), m))
    return bad


def test_dangling_detects_raw_deletion():
    """The reference check is not vacuous: deleting a bare <species> element is caught."""
    d = load_diagram(AUTOPHAGY)
    check("pristine map has no dangling references", dangling(d) == [])
    sp = get_all_species(d)[0]
    sp.getparent().remove(sp)
    check("raw deletion leaves dangling references", len(dangling(d)) > 0)


def test_reaction_types():
    """Types the maps already use are accepted; nonsense is still refused."""
    d = load_diagram(AUTOPHAGY)
    r = get_all_reactions(d)[0]
    ok = True
    for t in ("REDUCED_MODULATION", "TRIGGER", "UNKNOWN_POSITIVE_INFLUENCE", "MODULATION"):
        change_reaction_type(d, r, t)
        ok &= get_reaction_type(r) == t
    check("REDUCED_MODULATION / TRIGGER / UNKNOWN_POSITIVE_INFLUENCE accepted", ok)
    try:
        change_reaction_type(d, r, "SIDEWAYS_INFLUENCE")
        check("unknown type refused", False)
    except ValueError:
        check("unknown type refused", True)


def test_participants_include_complex_members():
    """A reaction pointing at a complex member reports that member, not just SBML refs."""
    d = load_diagram(IRON)
    included = {s.get("id") for s in get_included_species(d)}
    hits = [r for r in get_all_reactions(d) if get_reaction_species_ids(r) & included]
    check("reactions referring to complex members are seen", len(hits) > 0)
    member = next(iter(get_reaction_species_ids(hits[0]) & included))
    check("get_species_reactions finds a member's reaction",
          hits[0] in get_species_reactions(d, member))


def test_components_and_simulated_removal():
    """Components cover every species; excluding a reaction shows what it disconnects."""
    d = load_diagram(AUTOPHAGY)
    comps = get_connected_components(d)
    check("components partition all top-level species",
          sum(map(len, comps)) == len(get_all_species(d))
          and set().union(*comps) == {s.get("id") for s in get_all_species(d)})
    # a species in exactly one reaction is cut off when that reaction goes
    leaf = next(s for s in get_all_species(d) if len(get_species_reactions(d, s.get("id"))) == 1)
    rid = get_species_reactions(d, leaf.get("id"))[0].get("id")
    after = get_connected_components(d, exclude_reactions={rid})
    check("simulated removal isolates the leaf species", {leaf.get("id")} in after)
    check("simulation leaves the diagram untouched", not d.is_dirty)


def test_remove_reaction_cleans_backrefs():
    """Removing a catalysed reaction drops the species' back-reference to it."""
    d = load_diagram(AUTOPHAGY)
    cat = next(s for s in get_all_species(d) if get_catalyzed_reactions(s))
    rid = get_catalyzed_reactions(cat)[0]
    r = next(x for x in get_all_reactions(d) if x.get("id") == rid)
    n = len(get_all_reactions(d))
    remove_reaction(d, r)
    check("reaction removed", len(get_all_reactions(d)) == n - 1)
    check("catalysis back-reference removed", rid not in get_catalyzed_reactions(cat))
    check("participants kept", cat in get_all_species(d))
    check("no dangling references after reaction removal", dangling(d) == [])
    other = load_diagram(AUTOPHAGY)
    try:
        remove_reaction(d, get_all_reactions(other)[0])
        check("reaction of another diagram refused", False)
    except ValueError:
        check("reaction of another diagram refused", True)


def test_remove_species():
    """A species in use is refused; a complex goes with its members and aliases."""
    d = load_diagram(AUTOPHAGY)
    members = {}
    for s in get_included_species(d):
        members.setdefault(s.find(f"{{{CD}}}annotation/{{{CD}}}complexSpecies").text, []).append(s)
    cx = next(s for s in get_all_species(d) if s.get("id") in members)
    cid = cx.get("id")
    used_by = get_species_reactions(d, cid) + [r for m in members[cid]
                                               for r in get_species_reactions(d, m.get("id"))]
    n_species = len(get_all_species(d))
    if used_by:
        try:
            remove_species(d, cx)
            check("species in a reaction refused", False)
        except ValueError:
            check("species in a reaction refused", len(get_all_species(d)) == n_species)
        for r in {id(r): r for r in used_by}.values():
            remove_reaction(d, r)
    n_aliases = len(get_aliases_for_species(d, cid))
    out = remove_species(d, cx)
    check("complex removed", out["species"] == [cid] and cx not in get_all_species(d))
    check("its members removed", set(out["included_species"]) >= {m.get("id") for m in members[cid]})
    check("its aliases removed", len(out["aliases"]) >= n_aliases and not get_aliases_for_species(d, cid))
    check("no dangling references after complex removal", dangling(d) == [])
    try:
        remove_species(d, get_included_species(d)[0])
        check("complex member refused (not top-level)", False)
    except ValueError:
        check("complex member refused (not top-level)", True)


def test_remove_orphaned_species():
    """Unconnected species go, kept ids stay, a complex with a used member stays."""
    d = load_diagram(IRON)
    included = {s.get("id") for s in get_included_species(d)}
    member_rxn = next(r for r in get_all_reactions(d) if get_reaction_species_ids(r) & included)
    member = next(iter(get_reaction_species_ids(member_rxn) & included))
    parent = next(s for s in get_included_species(d) if s.get("id") == member) \
        .find(f"{{{CD}}}annotation/{{{CD}}}complexSpecies").text
    for r in list(get_all_reactions(d)):
        if r is member_rxn:
            continue
        remove_reaction(d, r)
    candidates = [s.get("id") for s in get_all_species(d)
                  if not get_species_reactions(d, s.get("id"))]
    keep_one = candidates[0]
    out = remove_orphaned_species(d, keep={keep_one})
    left = {s.get("id") for s in get_all_species(d)}
    check("orphans removed", len(out["species"]) > 0 and not (set(out["species"]) & left))
    check("kept id survives", keep_one in left)
    check("complex whose member is in a reaction survives", parent in left)
    remove_unused_entity_definitions(d)
    check("no dangling references after orphan sweep", dangling(d) == [])


def test_add_reaction():
    """A new arc between existing species reads back like any other reaction."""
    d = load_diagram(AUTOPHAGY)
    sp = get_all_species(d)
    a, b = sp[0].get("id"), sp[1].get("id")
    r = add_reaction(d, a, b, "TRIGGER")
    p = get_participants(r)
    check("participants as requested",
          [x["species_id"] for x in p["reactants"]] == [a]
          and [x["species_id"] for x in p["products"]] == [b])
    check("type as requested", get_reaction_type(r) == "TRIGGER")
    check("alias belongs to its species",
          p["reactants"][0]["alias_id"] in {x.get("id") for x in get_aliases_for_species(d, a)})
    ids = [e.get("id") for e in d.root.iter() if isinstance(e.tag, str) and e.get("id")]
    check("new id is unique", ids.count(r.get("id")) == 1)
    add_annotation(r, "isDescribedBy", "pubmed", "28721275", diagram=d)
    set_notes_text(r, "28721275 | mechanism: direct: test | \"q\"\nprovenance: new", diagram=d)
    r2 = add_reaction(d, b, a, "NEGATIVE_INFLUENCE")
    check("second reaction gets a different id", r2.get("id") != r.get("id"))
    check("no dangling references after adding", dangling(d) == [])
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.xml")
        save_diagram(d, out)
        fresh = next(x for x in get_all_reactions(load_diagram(out)) if x.get("id") == r.get("id"))
    check("survives save/reload with annotation and notes",
          get_annotations(fresh).get("isDescribedBy") == ["urn:miriam:pubmed:28721275"]
          and get_notes_text(fresh).endswith("provenance: new"))
    refusals = [
        ("same species", dict(reactant_id=a, product_id=a, reaction_type="TRIGGER")),
        ("Boolean gate", dict(reactant_id=a, product_id=b, reaction_type="BOOLEAN_LOGIC_GATE_AND")),
        ("unknown species", dict(reactant_id=a, product_id="nope", reaction_type="TRIGGER")),
        ("complex member", dict(reactant_id=a, product_id=get_included_species(d)[0].get("id"),
                                reaction_type="TRIGGER")),
        ("foreign alias", dict(reactant_id=a, product_id=b, reaction_type="TRIGGER",
                               reactant_alias=get_aliases_for_species(d, b)[0].get("id"))),
        ("taken id", dict(reactant_id=a, product_id=b, reaction_type="TRIGGER",
                          reaction_id=r.get("id"))),
    ]
    n = len(get_all_reactions(d))
    for label, kwargs in refusals:
        try:
            add_reaction(d, **kwargs)
            check(f"refused: {label}", False)
        except ValueError:
            check(f"refused: {label}", len(get_all_reactions(d)) == n)


def test_review_pipeline_on_ad_kg():
    """The review's write sequence on the real file stays consistent and MINERVA-valid:
    annotate → remove a batch of reactions → sweep orphans (keeping one node) →
    drop unused definitions → add a replacement arc."""
    d = load_diagram(AD_KG)
    keep = next(s.get("id") for s in get_all_species(d)
                if get_species_name(d, s) == "Alzheimer Disease")
    batch = get_all_reactions(d)[:200]
    for r in batch[:5]:
        add_annotation(r, "isDescribedBy", "pubmed", "28721275", diagram=d)
        set_notes_text(r, "28721275 | mechanism: perturbation: x | \"q\"\nprovenance: reviewed",
                       diagram=d)
    survivors = batch[:5]
    for r in batch[5:]:
        remove_reaction(d, r)
    out = remove_orphaned_species(d, keep={keep})
    remove_unused_entity_definitions(d)
    check("batch removed, orphans swept",
          len(get_all_reactions(d)) == 4775 - 195 and len(out["species"]) > 0)
    check("kept node survives the sweep", keep in {s.get("id") for s in get_all_species(d)})
    big = max(get_connected_components(d), key=len)
    a, b = sorted(big)[:2]
    add_reaction(d, a, b, "POSITIVE_INFLUENCE")
    check("survivors keep their evidence",
          all(get_notes_text(r).endswith("provenance: reviewed") for r in survivors))
    check("no dangling references in the edited AD KG", dangling(d) == [])
    data = etree.tostring(d.tree, xml_declaration=True, encoding="UTF-8")
    try:
        validate_xml_bytes(data, label="edited ad_kg")
        check("MINERVA validates the edited AD KG", True)
    except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout) as exc:
        print(f"  skip  MINERVA unreachable ({exc})")


if __name__ == "__main__":
    print("network editing")
    test_dangling_detects_raw_deletion()
    test_reaction_types()
    test_participants_include_complex_members()
    test_components_and_simulated_removal()
    test_remove_reaction_cleans_backrefs()
    test_remove_species()
    test_remove_orphaned_species()
    test_add_reaction()
    test_review_pipeline_on_ad_kg()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
