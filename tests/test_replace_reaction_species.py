#!/usr/bin/env python3
"""`replace_reaction_species` — repoint a reaction from one species to another.

The AD review uses it to move reactions from a mouse/rat species onto the human one. A
reaction names its participants in several places — SBML lists, CellDesigner base
reactants/products, reactant/product links, modifier lists with parallel alias lists,
Boolean-gate members, `<celldesigner:alias>` text, and the catalyst's back-reference — and
missing any of them leaves a reaction half-attached to the old glyph. Each test therefore
checks the whole reaction for leftovers and the whole diagram for dangling references.
"""
import os
import socket
import sys
import tempfile
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from lxml import etree

from cdutils import (load_diagram, save_diagram, get_all_reactions, get_all_species,
                     get_included_species, get_participants, get_reaction_species_ids,
                     get_species_reactions, get_species_name, get_species_class,
                     get_aliases_for_species, get_catalyzed_reactions, get_annotations,
                     replace_reaction_species, remove_orphaned_species,
                     remove_unused_entity_definitions, validate_xml_bytes)
from cdutils.namespaces import CD, SBML
from test_network_edit import dangling

PD = "/workspace/pdmap/submaps"
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


def leftovers(reaction, species_id, alias_ids):
    """References to the old species or its glyphs still inside *reaction*."""
    out = []
    for el in reaction.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in ("species", "reactant", "product", "modifiers"):
            if species_id in [v.strip() for v in (el.get(attr) or "").split(",")]:
                out.append((etree.QName(el).localname, attr))
        for attr in ("alias", "aliases"):
            if set((el.get(attr) or "").split(",")) & alias_ids:
                out.append((etree.QName(el).localname, attr))
        if etree.QName(el).localname == "alias" and (el.text or "").strip() in alias_ids:
            out.append(("alias", "text"))
    return out


def _other_species(d, reaction, exclude=()):
    """A top-level species with a glyph that is not in *reaction*."""
    used = get_reaction_species_ids(reaction) | set(exclude)
    return next(s for s in get_all_species(d)
                if s.get("id") not in used and get_aliases_for_species(d, s.get("id")))


def _old_aliases(d, sid):
    return {a.get("id") for a in get_aliases_for_species(d, sid)}


def test_mouse_to_human_on_ad_kg():
    """Every reaction of a mouse species moves to the human one; the mouse glyph then orphans."""
    d = load_diagram(AD_KG)
    by = {(get_species_name(d, s), get_species_class(s)): s for s in get_all_species(d)}
    pair = next(((m, h) for (n, c), m in by.items()
                 if n != n.upper() and (n.upper(), c) in by
                 and get_species_reactions(d, m.get("id"))
                 for h in [by[(n.upper(), c)]]), None)
    if pair is None:
        check("fixture: a mouse species with a human counterpart", False)
        return
    mouse, human = pair
    mid, hid = mouse.get("id"), human.get("id")
    rxns = get_species_reactions(d, mid)
    old_aliases = _old_aliases(d, mid)
    evidence = {r.get("id"): get_annotations(r) for r in rxns}
    skipped = 0
    for r in rxns:
        if hid in get_reaction_species_ids(r):
            skipped += 1      # mouse→human arc: repointing would self-loop; refused below
            continue
        replace_reaction_species(d, r, mid, hid)
    moved = [r for r in rxns if hid in get_reaction_species_ids(r)]
    check(f"{get_species_name(d, mouse)} -> {get_species_name(d, human)}: "
          f"{len(moved)} reaction(s) now on the human species", len(moved) == len(rxns) - skipped)
    check("no reference to the mouse species or glyphs remains",
          all(not leftovers(r, mid, old_aliases) for r in moved))
    check("reaction evidence untouched", all(get_annotations(r) == evidence[r.get("id")] for r in moved))
    check("new arcs are drawn to a human glyph",
          all(p["alias_id"] in _old_aliases(d, hid)
              for r in moved for role in ("reactants", "products")
              for p in get_participants(r)[role] if p["species_id"] == hid))
    if not skipped:
        out = remove_orphaned_species(d)
        check("mouse species removed by the orphan sweep", mid in out["species"])
    remove_unused_entity_definitions(d)
    check("no dangling references", dangling(d) == [])


def test_catalyst_and_backref():
    """A catalyst's modifier lists, link target and back-reference all move."""
    d = load_diagram(f"{PD}/Autophagy.xml")
    cat = next(s for s in get_all_species(d) if get_catalyzed_reactions(s))
    rid = get_catalyzed_reactions(cat)[0]
    r = next(x for x in get_all_reactions(d) if x.get("id") == rid)
    new = _other_species(d, r)
    old_aliases = _old_aliases(d, cat.get("id"))
    n = replace_reaction_species(d, r, cat.get("id"), new.get("id"))
    check("references rewritten", n > 0)
    check("no reference to the old catalyst remains", not leftovers(r, cat.get("id"), old_aliases))
    mods = get_participants(r)["modifiers"]
    check("new species is a modifier with a typed modification",
          any(m["species_id"] == new.get("id") and m["modifier_type"] for m in mods))
    check("back-reference moved", rid not in get_catalyzed_reactions(cat)
          and rid in get_catalyzed_reactions(new))
    check("no dangling references", dangling(d) == [])


def test_reactant_link():
    """An extra reactant drawn as a reactantLink is repointed in the link and in SBML."""
    d = load_diagram(f"{PD}/Autophagy.xml")
    r = next(x for x in get_all_reactions(d) if x.find(f".//{{{CD}}}reactantLink") is not None)
    link = r.find(f".//{{{CD}}}reactantLink")
    old = link.get("reactant")
    new = _other_species(d, r)
    old_aliases = _old_aliases(d, old)
    replace_reaction_species(d, r, old, new.get("id"))
    check("link points at the new species and one of its glyphs",
          link.get("reactant") == new.get("id")
          and link.get("alias") in _old_aliases(d, new.get("id")))
    check("SBML reactant list updated",
          new.get("id") in [x["species_id"] for x in get_participants(r)["reactants"]])
    check("no reference to the old reactant remains", not leftovers(r, old, old_aliases))
    check("no dangling references", dangling(d) == [])


def _validate(d, label):
    data = etree.tostring(d.tree, xml_declaration=True, encoding="UTF-8")
    try:
        validate_xml_bytes(data, label=label)
        check(f"MINERVA validates: {label}", True)
    except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout) as exc:
        print(f"  skip  MINERVA unreachable ({exc})")


def test_gate_reaction_input():
    """Gate drawn as the reaction itself: inputs are base reactants, GateMember lists aliases."""
    d = load_diagram(f"{PD}/Histamine signalling.xml")
    r = next(x for x in get_all_reactions(d) if x.find(f".//{{{CD}}}GateMember") is not None)
    old = get_participants(r)["reactants"][0]["species_id"]
    new = _other_species(d, r)
    old_aliases = _old_aliases(d, old)
    replace_reaction_species(d, r, old, new.get("id"))
    members = list(r.iter(f"{{{CD}}}GateMember"))
    check("every GateMember alias list rewritten",
          not any(set(m.get("aliases").split(",")) & old_aliases for m in members)
          and any(set(m.get("aliases").split(",")) & _old_aliases(d, new.get("id")) for m in members))
    check("gate reaction: no reference to the old input remains", not leftovers(r, old, old_aliases))
    check("gate reaction: no dangling references", dangling(d) == [])
    _validate(d, "repointed gate reaction")


def test_gate_modifier_input():
    """Gate drawn as a modifier: paired modifiers/aliases lists keep length and alignment."""
    d = load_diagram(f"{PD}/CREB activity.xml")
    r = next(x for x in get_all_reactions(d)
             if any(m.get("type") == "BOOLEAN_LOGIC_GATE_AND" for m in x.iter(f"{{{CD}}}modification")))
    gate = next(m for m in r.iter(f"{{{CD}}}modification") if m.get("type") == "BOOLEAN_LOGIC_GATE_AND")
    old = gate.get("modifiers").split(",")[0]
    n_inputs = len(gate.get("modifiers").split(","))
    new = _other_species(d, r)
    old_aliases = _old_aliases(d, old)
    replace_reaction_species(d, r, old, new.get("id"))
    mods, aliases = gate.get("modifiers").split(","), gate.get("aliases").split(",")
    check("gate lists keep their length and pairing",
          len(mods) == len(aliases) == n_inputs and mods[0] == new.get("id")
          and aliases[0] in _old_aliases(d, new.get("id")))
    check("gate modifier: no reference to the old input remains", not leftovers(r, old, old_aliases))
    check("gate modifier: no dangling references", dangling(d) == [])
    _validate(d, "repointed gate modifier")


def test_explicit_alias_and_round_trip():
    """An explicit glyph is used as given and the result survives save/reload."""
    d = load_diagram(f"{PD}/Autophagy.xml")
    r = get_all_reactions(d)[0]
    old = get_participants(r)["products"][0]["species_id"]
    new = _other_species(d, r)
    glyph = get_aliases_for_species(d, new.get("id"))[-1].get("id")
    replace_reaction_species(d, r, old, new.get("id"), new_alias=glyph)
    check("explicit glyph used", get_participants(r)["products"][0]["alias_id"] == glyph)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.xml")
        save_diagram(d, out)
        fresh = next(x for x in get_all_reactions(load_diagram(out)) if x.get("id") == r.get("id"))
    check("survives save/reload", get_participants(fresh)["products"][0] ==
          {"species_id": new.get("id"), "alias_id": glyph})


def test_refusals():
    """Bad requests fail before anything is written."""
    d = load_diagram(f"{PD}/Autophagy.xml")
    r = get_all_reactions(d)[0]
    p = get_participants(r)
    a, b = p["reactants"][0]["species_id"], p["products"][0]["species_id"]
    outsider = _other_species(d, r)
    before = etree.tostring(r)
    cases = [
        ("species not in the reaction", (outsider.get("id"), a), {}),
        ("same species", (a, a), {}),
        ("would link a species to itself", (a, b), {}),
        ("unknown new species", (a, "nope"), {}),
        ("complex member as new species", (a, get_included_species(d)[0].get("id")), {}),
        ("glyph of another species", (a, outsider.get("id")),
         {"new_alias": get_aliases_for_species(d, b)[0].get("id")}),
    ]
    for label, (old, new), kw in cases:
        try:
            replace_reaction_species(d, r, old, new, **kw)
            check(f"refused: {label}", False)
        except ValueError:
            check(f"refused: {label}", etree.tostring(r) == before)
    check("diagram not marked dirty", not d.is_dirty)


if __name__ == "__main__":
    print("replace_reaction_species")
    test_mouse_to_human_on_ad_kg()
    test_catalyst_and_backref()
    test_reactant_link()
    test_gate_reaction_input()
    test_gate_modifier_input()
    test_explicit_alias_and_round_trip()
    test_refusals()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
