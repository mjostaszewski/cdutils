#!/usr/bin/env python3
"""`decode_cd_name` — the `_underscore_` escape.

`_underscore_` is a literal `_`. Its own underscores can complete a neighbouring escape, so a
naive replace in either order mis-decodes `x_underscore_minus_underscore_y` (a literal
`x_minus_y`) as `x-y`. The tests pin that case, and prove over every name in the PD map and the
AD knowledge graph that names without `_underscore_` decode exactly as they did before.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lxml import etree

from cdutils import (decode_cd_name, load_diagram, get_all_species, get_included_species,
                     get_species_name)

AD = "/workspace/sandbox/pdmap-expansion/ad-interaction"
CORPUS = sorted(glob.glob("/workspace/pdmap/*.xml") + glob.glob("/workspace/pdmap/submaps/*.xml")
                + glob.glob(f"{AD}/ad_kg*.xml"))
passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


def _previous_decoder(encoded):
    """`decode_cd_name` as it was before `_underscore_` was added."""
    for enc, dec in (("_br_", " "), ("_slash_", "/"), ("_plus_", "+"),
                     ("_space_", " "), ("_minus_", "-")):
        encoded = encoded.replace(enc, dec)
    return encoded


def test_underscore_cases():
    cases = {
        "Gamma_underscore_secretase": "Gamma_secretase",
        "p14_underscore_3_underscore_3": "p14_3_3",
        "PINK1_underscore_degraded": "PINK1_degraded",
        "NF_underscore_kappaB_space_survival": "NF_kappaB survival",
        "x_underscore_minus_underscore_y": "x_minus_y",        # literal, not an escape
        "A_underscore__space_B": "A_ B",
        "_underscore_": "_",
        "plain_name": "plain_name",                             # bare underscores untouched
        "Ca2_plus__space_channel": "Ca2+ channel",              # existing escapes unchanged
    }
    for enc, want in cases.items():
        got = decode_cd_name(enc)
        check(f"{enc!r} -> {want!r}", got == want)


def test_no_change_without_underscore_escape():
    """Every name field in the corpus without `_underscore_` decodes exactly as before."""
    total = differ = 0
    for path in CORPUS:
        for el in etree.parse(path).iter():
            if not isinstance(el.tag, str):
                continue
            values = [el.get("name")] if el.get("name") else []
            if etree.QName(el).localname == "name" and el.text:
                values.append(el.text)
            for v in values:
                if "_underscore_" in v:
                    continue
                total += 1
                differ += decode_cd_name(v) != _previous_decoder(v)
    check(f"{total} name values without _underscore_ decode as before", total > 0 and differ == 0)


def test_species_names_fully_decoded():
    """No species name read through cdutils still carries the escape."""
    for path in (f"{AD}/ad_kg.xml", "/workspace/pdmap/submaps/Mitophagy.xml"):
        d = load_diagram(path)
        names = [get_species_name(d, s) for s in get_all_species(d) + get_included_species(d)]
        check(f"{os.path.basename(path)}: no _underscore_ left in species names",
              not any("_underscore_" in n for n in names))


if __name__ == "__main__":
    print("decode_cd_name: _underscore_")
    test_underscore_cases()
    test_no_change_without_underscore_escape()
    test_species_names_fully_decoded()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
