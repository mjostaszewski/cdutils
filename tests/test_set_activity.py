#!/usr/bin/env python3
"""`set_activity` — the writer half of `get_activity`.

CellDesigner keeps the "active" double border on the *alias*, not the species, so the tests
below pin the three things a caller can get wrong: that it round-trips, that it rejects a
value CellDesigner would not understand, and that setting one alias of a two-alias species
leaves the other alone.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cdutils import (load_diagram, save_diagram, get_all_species_aliases, get_activity,
                     set_activity, get_aliases_for_species)

SRC = "/workspace/pdmap/submaps/Endoplasmic Reticulum activity.xml"
passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def test_round_trip():
    """active -> inactive survives a save/reload, and back again.

    The starting state is set here rather than searched for. Looking for an alias that is
    already active ties the test to whatever the map happens to hold — and once the map was
    harmonised there were none left, so this died with StopIteration instead of failing
    cleanly. Same lesson as `test_per_alias_not_per_species` below: build the fixture.
    """
    d = load_diagram(SRC)
    alias = next(iter(get_all_species_aliases(d)))
    aid = alias.get("id")
    set_activity(d, alias, "active")
    check("precondition: alias set active", get_activity(alias) == "active")
    set_activity(d, alias, "inactive")
    check("in-memory flip to inactive", get_activity(alias) == "inactive")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "out.xml")
        save_diagram(d, out)
        fresh = load_diagram(out)
        again = next(a for a in get_all_species_aliases(fresh) if a.get("id") == aid)
        check("inactive persisted to disk", get_activity(again) == "inactive")
        set_activity(fresh, again, "active")
        out2 = os.path.join(tmp, "out2.xml")
        save_diagram(fresh, out2)
        back = load_diagram(out2)
        a3 = next(a for a in get_all_species_aliases(back) if a.get("id") == aid)
        check("active restored", get_activity(a3) == "active")


def test_rejects_bad_value():
    """Anything but active/inactive is refused, so a typo cannot silently land."""
    d = load_diagram(SRC)
    alias = next(iter(get_all_species_aliases(d)))
    for bad in ("ACTIVE", "on", "", "activated", None):
        try:
            set_activity(d, alias, bad)
        except ValueError:
            continue
        except TypeError:
            continue
        check(f"refused {bad!r}", False)
        return
    check("refuses values CellDesigner would not understand", True)


def test_per_alias_not_per_species():
    """A species drawn twice: setting one alias must not touch the other.

    The fixture is built rather than found. An earlier version searched the map for a
    two-alias species that happened to be active on both, which made the test decay the
    moment the map was harmonised — it silently fell back to a no-op branch and the check
    count dropped. Setting the precondition here keeps it meaningful whatever the map holds.
    """
    d = load_diagram(SRC)
    sibs = None
    for a in get_all_species_aliases(d):
        candidates = get_aliases_for_species(d, a.get("species"))
        if len(candidates) > 1:
            sibs = candidates
            break
    if sibs is None:
        check("per-alias isolation — FIXTURE HAS NO MULTI-ALIAS SPECIES", False)
        return
    for x in sibs:
        set_activity(d, x, "active")
    set_activity(d, sibs[0], "inactive")
    check("first alias flipped", get_activity(sibs[0]) == "inactive")
    check("sibling aliases untouched",
          all(get_activity(x) == "active" for x in sibs[1:]))


if __name__ == "__main__":
    print("set_activity")
    test_round_trip()
    test_rejects_bad_value()
    test_per_alias_not_per_species()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
