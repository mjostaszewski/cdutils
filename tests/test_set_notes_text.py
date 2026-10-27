#!/usr/bin/env python3
"""`set_notes_text` — the writer half of `get_notes_text`.

Notes live in two places: SBML `<notes>` on top-level elements, and `<celldesigner:notes>` on
included species, where the element's RDF annotations share the same `<body>`. The tests pin
what a caller can get wrong: the text round-trips through a save, the RDF beside it survives,
a new `<notes>` lands where SBML requires it (first child), markup in the text is escaped
rather than parsed, and a string XML cannot hold is refused before anything is touched.
"""
import os
import socket
import sys
import tempfile
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree

from cdutils import (load_diagram, save_diagram, get_all_reactions, get_included_species,
                     get_annotations, get_annotation_location, add_annotation,
                     get_notes_text, set_notes_text, validate_xml_bytes)
from cdutils.namespaces import SBML, CD

SRC = "/workspace/pdmap/submaps/Autophagy.xml"
# the evidence-block layout of the AD review spec, with characters that need escaping
NOTE = ("12345678 | mechanism: perturbation: Trem2 KO lowers Il1b | "
        "\"Trem2-/- microglia released less IL-1β (p < 0.05) & TNF\"\n"
        "23456789 | mechanism: direct: NLRP3 binds ASC | \"NLRP3 recruits ASC\"\n"
        "provenance: reviewed+pd-match")
passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def _reaction_without_notes(d):
    """Any reaction, stripped of its notes — the fixture is built, not searched for."""
    r = get_all_reactions(d)[0]
    old = r.find(f"{{{SBML}}}notes")
    if old is not None:
        r.remove(old)
    return r


def _annotated_included_species(d):
    """An included species carrying RDF in its notes; annotated here if none already is."""
    for s in get_included_species(d):
        if get_annotations(s):
            return s
    s = get_included_species(d)[0]
    add_annotation(s, "is", "hgnc.symbol", "TREM2")
    return s


def _first_child_tag(el):
    return next(c.tag for c in el if isinstance(c.tag, str))


def test_new_notes_on_reaction():
    """A reaction with no notes gets them, first in order, and they survive save/reload."""
    d = load_diagram(SRC)
    r = _reaction_without_notes(d)
    rid = r.get("id")
    anns = get_annotations(r)
    set_notes_text(r, NOTE, diagram=d)
    check("text round-trips in memory", get_notes_text(r) == NOTE)
    check("<notes> is the first child (SBML order)", _first_child_tag(r) == f"{{{SBML}}}notes")
    check("reaction annotations untouched", get_annotations(r) == anns)
    check("diagram marked dirty", d.is_dirty)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.xml")
        save_diagram(d, out)
        fresh = next(x for x in get_all_reactions(load_diagram(out)) if x.get("id") == rid)
    check("text survives save/reload", get_notes_text(fresh) == NOTE)


def test_replaces_existing():
    """Old text and markup are replaced, not appended to."""
    d = load_diagram(SRC)
    r = get_all_reactions(d)[0]
    set_notes_text(r, "old text that must go")
    body = r.find(f"{{{SBML}}}notes").find(".//{*}body")
    etree.SubElement(body, "{http://www.w3.org/1999/xhtml}p").text = "old paragraph"
    set_notes_text(r, "new")
    check("only the new text remains", get_notes_text(r) == "new")
    check("old markup removed", len(body) == 0)
    check("still exactly one <notes>", len(r.findall(f"{{{SBML}}}notes")) == 1)


def test_included_species_keeps_rdf():
    """Writing notes on a complex member must not cost it its annotations."""
    d = load_diagram(SRC)
    s = _annotated_included_species(d)
    sid = s.get("id")
    anns = get_annotations(s)
    set_notes_text(s, NOTE, diagram=d)
    check("included species: text round-trips", get_notes_text(s) == NOTE)
    check("included species: annotations survive", get_annotations(s) == anns)
    check("included species: RDF still in notes", get_annotation_location(s) == "notes")
    set_notes_text(s, "second write")
    check("included species: rewrite replaces text", get_notes_text(s) == "second write")
    check("included species: annotations survive a rewrite", get_annotations(s) == anns)
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.xml")
        save_diagram(d, out)
        fresh = next(x for x in get_included_species(load_diagram(out)) if x.get("id") == sid)
    check("included species: survives save/reload",
          get_notes_text(fresh) == "second write" and get_annotations(fresh) == anns)


def test_new_notes_on_included_species_go_first():
    """A created <celldesigner:notes> precedes <celldesigner:annotation>, as CellDesigner writes it."""
    d = load_diagram(SRC)
    s = get_included_species(d)[0]
    s.remove(s.find(f"{{{CD}}}notes"))
    set_notes_text(s, "fresh")
    check("created notes are first", _first_child_tag(s) == f"{{{CD}}}notes")
    check("created notes read back", get_notes_text(s) == "fresh")


def test_clear():
    """Empty text clears: a bare reaction loses <notes>; an included species keeps its RDF."""
    d = load_diagram(SRC)
    r = _reaction_without_notes(d)
    set_notes_text(r, "temporary")
    set_notes_text(r, "")
    check("cleared reaction has no <notes>", r.find(f"{{{SBML}}}notes") is None)
    set_notes_text(r, "")
    check("clearing absent notes is a no-op", r.find(f"{{{SBML}}}notes") is None)
    s = _annotated_included_species(d)
    anns = get_annotations(s)
    set_notes_text(s, "temporary")
    set_notes_text(s, "")
    check("cleared included species: no text", get_notes_text(s) == "")
    check("cleared included species: annotations survive", get_annotations(s) == anns)


def test_markup_is_text():
    """`<` and `&` are escaped, never parsed into elements."""
    d = load_diagram(SRC)
    r = _reaction_without_notes(d)
    set_notes_text(r, "<b>bold</b> & co")
    body = r.find(f"{{{SBML}}}notes").find(".//{*}body")
    check("no element created from markup", len(body) == 0)
    check("markup kept verbatim as text", get_notes_text(r) == "<b>bold</b> & co")


def test_rejects_bad_text():
    """A string XML cannot represent, or a non-string, fails with the element unchanged."""
    d = load_diagram(SRC)
    r = get_all_reactions(d)[0]
    before = etree.tostring(r)
    for bad, exc in (("NUL\x00byte", ValueError), ("vertical\x0btab", ValueError),
                     (12345678, TypeError)):
        try:
            set_notes_text(r, bad, diagram=d)
            check(f"rejects {bad!r}", False)
        except exc:
            check(f"rejects {bad!r}", True)
    check("element unchanged after rejections", etree.tostring(r) == before)
    check("diagram not marked dirty", not d.is_dirty)


def test_minerva_accepts_notes():
    """MINERVA round-trips a file with written notes. Skipped when the converter is down."""
    d = load_diagram(SRC)
    set_notes_text(_reaction_without_notes(d), NOTE)
    set_notes_text(_annotated_included_species(d), NOTE)
    data = etree.tostring(d.tree, xml_declaration=True, encoding="UTF-8")
    try:
        validate_xml_bytes(data, label="notes fixture")
        check("MINERVA validates the written notes", True)
    except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout) as exc:
        print(f"  skip  MINERVA unreachable ({exc})")


if __name__ == "__main__":
    print("set_notes_text")
    test_new_notes_on_reaction()
    test_replaces_existing()
    test_included_species_keeps_rdf()
    test_new_notes_on_included_species_go_first()
    test_clear()
    test_markup_is_text()
    test_rejects_bad_text()
    test_minerva_accepts_notes()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
