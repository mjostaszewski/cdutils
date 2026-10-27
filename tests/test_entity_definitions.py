#!/usr/bin/env python3
"""Tests for entity-definition inventory, orphan removal and merging.

The interesting cases are all about ``modificationResidue`` ids being *local to a
declaration*: the same id means different residues in two declarations of the same
protein, so a merge that carries ids across silently rewrites which residue a glyph
claims is modified. These tests pin that down in both directions — the safe remap,
and the refusals.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cdutils
from cdutils import (
    load_diagram, get_entity_definitions, remove_unused_entity_definitions,
    merge_entity_definitions, get_all_species, get_included_species,
    get_modifications, get_protein_residues, get_species_by_id,
)

CD = "http://www.sbml.org/2001/ns/celldesigner"

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
 <model id="m">
  <annotation>
   <celldesigner:extension xmlns:celldesigner="{cd}">
    <celldesigner:modelVersion>4.0</celldesigner:modelVersion>
    <celldesigner:listOfProteins>
     <celldesigner:protein id="pr1" name="TP53" type="GENERIC">
      <celldesigner:listOfModificationResidues>
       <celldesigner:modificationResidue id="rs1" name="S15" side="none" angle="0"/>
       <celldesigner:modificationResidue id="rs2" name="" side="none" angle="1"/>
      </celldesigner:listOfModificationResidues>
     </celldesigner:protein>
     <celldesigner:protein id="pr2" name="TP53" type="GENERIC">
      <celldesigner:listOfModificationResidues>
       <celldesigner:modificationResidue id="rs1" name="" side="none" angle="0"/>
       <celldesigner:modificationResidue id="rs2" name="S15" side="none" angle="1"/>
      </celldesigner:listOfModificationResidues>
     </celldesigner:protein>
     <celldesigner:protein id="pr3" name="TP53" type="GENERIC">
      <celldesigner:listOfModificationResidues>
       <celldesigner:modificationResidue id="rs1" name="S15" side="none" angle="0"/>
       <celldesigner:modificationResidue id="rs2" name="" side="none" angle="1"/>
      </celldesigner:listOfModificationResidues>
     </celldesigner:protein>
     <celldesigner:protein id="pr9" name="ORPHAN" type="GENERIC"/>
     <celldesigner:protein id="pr8" name="TP53" type="TRUNCATED"/>
    </celldesigner:listOfProteins>
   </celldesigner:extension>
  </annotation>
  <listOfSpecies>
   {species}
  </listOfSpecies>
 </model>
</sbml>
"""

SPECIES = """
   <species id="s1" name="TP53">
    <annotation><celldesigner:extension xmlns:celldesigner="{cd}">
     <celldesigner:speciesIdentity>
      <celldesigner:class>PROTEIN</celldesigner:class>
      <celldesigner:proteinReference>pr1</celldesigner:proteinReference>
      <celldesigner:state><celldesigner:listOfModifications>
        <celldesigner:modification residue="rs1" state="phosphorylated"/>
      </celldesigner:listOfModifications></celldesigner:state>
     </celldesigner:speciesIdentity>
    </celldesigner:extension></annotation>
   </species>
   <species id="s2" name="TP53">
    <annotation><celldesigner:extension xmlns:celldesigner="{cd}">
     <celldesigner:speciesIdentity>
      <celldesigner:class>PROTEIN</celldesigner:class>
      <celldesigner:proteinReference>pr2</celldesigner:proteinReference>
      <celldesigner:state><celldesigner:listOfModifications>
        <celldesigner:modification residue="rs2" state="phosphorylated"/>
      </celldesigner:listOfModifications></celldesigner:state>
     </celldesigner:speciesIdentity>
    </celldesigner:extension></annotation>
   </species>
   <species id="s3" name="TP53">
    <annotation><celldesigner:extension xmlns:celldesigner="{cd}">
     <celldesigner:speciesIdentity>
      <celldesigner:class>PROTEIN</celldesigner:class>
      <celldesigner:proteinReference>pr3</celldesigner:proteinReference>
      <celldesigner:state><celldesigner:listOfModifications>
        <celldesigner:modification residue="rs1" state="phosphorylated"/>
      </celldesigner:listOfModifications></celldesigner:state>
     </celldesigner:speciesIdentity>
    </celldesigner:extension></annotation>
   </species>
"""


def build():
    xml = TEMPLATE.format(cd=CD, species=SPECIES.format(cd=CD))
    path = Path(tempfile.mkdtemp()) / "t.xml"
    path.write_text(xml, encoding="utf-8")
    return load_diagram(str(path))


def residue_label(d, species_id):
    """The label of the residue a species is modified at — what a merge must preserve."""
    sp = get_species_by_id(d, species_id)
    residues = {r["id"]: r["name"] for r in get_protein_residues(d, sp)}
    return [residues[m["residue"]] for m in get_modifications(sp)]


failures = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    if not ok:
        print(f"          got  {got!r}\n          want {want!r}")
        failures.append(label)


def check_raises(label, fn, needle):
    try:
        fn()
    except ValueError as exc:
        ok = needle in str(exc)
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
        if not ok:
            print(f"          message {str(exc)!r} lacks {needle!r}")
            failures.append(label)
    else:
        print(f"  FAIL  {label} — no ValueError raised")
        failures.append(label)


print("get_entity_definitions")
d = build()
defs = {e["ref_id"]: e for e in get_entity_definitions(d)}
check("finds every declaration", sorted(defs), ["pr1", "pr2", "pr3", "pr8", "pr9"])
check("reports referencing species", defs["pr1"]["species_ids"], ["s1"])
check("reports orphan as unreferenced", defs["pr9"]["species_ids"], [])
check("reports residue labels", defs["pr2"]["residues"], {"rs1": "", "rs2": "S15"})
check("restricts by class", get_entity_definitions(d, classes={"GENE"}), [])

print("\nremove_unused_entity_definitions")
d = build()
removed = remove_unused_entity_definitions(d)
check("removes only orphans", sorted(r["ref_id"] for r in removed), ["pr8", "pr9"])
check("leaves referenced declarations",
      sorted(e["ref_id"] for e in get_entity_definitions(d)), ["pr1", "pr2", "pr3"])
check("second call is a no-op", remove_unused_entity_definitions(d), [])

print("\nmerge_entity_definitions — identical id maps need no remap")
d = build()
res = merge_entity_definitions(d, "pr1", ["pr3"])
check("pr3 gone", sorted(e["ref_id"] for e in get_entity_definitions(d)),
      ["pr1", "pr2", "pr8", "pr9"])
check("s3 repointed", res["repointed"], [("s3", "pr3")])
check("no residue remap needed", res["residues_remapped"], [])
check("s3 still modified at S15", residue_label(d, "s3"), ["S15"])

print("\nmerge_entity_definitions — differing id maps remap by label")
d = build()
res = merge_entity_definitions(d, "pr1", ["pr2"])
check("s2 repointed", res["repointed"], [("s2", "pr2")])
check("residue remapped rs2->rs1", res["residues_remapped"], [("s2", "rs2", "rs1", "S15")])
check("s1 unchanged, still S15", residue_label(d, "s1"), ["S15"])
check("s2 MEANING preserved (S15, not the unnamed residue)", residue_label(d, "s2"), ["S15"])

print("\nmerge_entity_definitions — refusals")
d = build()
check_raises("different type is not the same entity",
             lambda: merge_entity_definitions(d, "pr1", ["pr8"]), "not the same entity")
check_raises("unknown ref",
             lambda: merge_entity_definitions(d, "pr1", ["nope"]), "no such entity definition")
check_raises("keep == drop",
             lambda: merge_entity_definitions(d, "pr1", ["pr1"]), "both kept and dropped")
check("refusal wrote nothing", sorted(e["ref_id"] for e in get_entity_definitions(d)),
      ["pr1", "pr2", "pr3", "pr8", "pr9"])

# a glyph modified at a residue the kept declaration does not have at all
d = build()
sp = get_species_by_id(d, "s2")
for mod in sp.iter(f"{{{CD}}}modification"):
    mod.set("residue", "rs1")          # rs1 in pr2 is the *unnamed* residue
# pr1 has an unnamed residue too, so this must SUCCEED and map to it
res = merge_entity_definitions(d, "pr1", ["pr2"])
check("unnamed residue maps to the kept unnamed residue",
      res["residues_remapped"], [("s2", "rs1", "rs2", "")])
check("s2 still modified at an unnamed residue", residue_label(d, "s2"), [""])


# ---------------------------------------------------------------------------
# Multimer cardinality — the third, easily-missed piece of species state
# ---------------------------------------------------------------------------

from cdutils import get_multimer_cardinality, is_homodimer, get_species_state
from cdutils.query import _state_key

MULTIMER = """<?xml version="1.0" encoding="UTF-8"?>
<sbml xmlns="http://www.sbml.org/sbml/level2/version4" level="2" version="4">
 <model id="m"><annotation><celldesigner:extension xmlns:celldesigner="{cd}">
   <celldesigner:listOfProteins>
    <celldesigner:protein id="pr1" name="BAK1" type="GENERIC"/>
   </celldesigner:listOfProteins>
  </celldesigner:extension></annotation>
  <listOfSpecies>{species}</listOfSpecies>
 </model>
</sbml>
"""


def _sp(sid, homodimer=None):
    inner = f"<celldesigner:homodimer>{homodimer}</celldesigner:homodimer>" if homodimer else ""
    state = f"<celldesigner:state>{inner}</celldesigner:state>" if inner else ""
    return f"""
   <species id="{sid}" name="BAK1">
    <annotation><celldesigner:extension xmlns:celldesigner="{CD}">
     <celldesigner:speciesIdentity>
      <celldesigner:class>PROTEIN</celldesigner:class>
      <celldesigner:proteinReference>pr1</celldesigner:proteinReference>
      {state}
     </celldesigner:speciesIdentity>
    </celldesigner:extension></annotation>
   </species>"""


print("\nget_multimer_cardinality")
xml = MULTIMER.format(cd=CD, species="".join([
    _sp("mono"), _sp("dimer", "2"), _sp("trimer", "3"),
    _sp("explicit_one", "1"), _sp("junk", "two"), _sp("blank", " ")]))
mpath = Path(tempfile.mkdtemp()) / "m.xml"
mpath.write_text(xml, encoding="utf-8")
md = load_diagram(str(mpath))
card = lambda sid: get_multimer_cardinality(get_species_by_id(md, sid))

check("absent tag means monomer, not unknown", card("mono"), 1)
check("dimer reads 2", card("dimer"), 2)
check("trimer reads 3", card("trimer"), 3)
check("explicit 1 stays 1", card("explicit_one"), 1)
check("non-numeric falls back to 1", card("junk"), 1)
check("blank falls back to 1", card("blank"), 1)
check("is_homodimer is cardinality > 1, not tag presence",
      [is_homodimer(get_species_by_id(md, s))
       for s in ("mono", "explicit_one", "dimer", "trimer")],
      [False, False, True, True])
check("get_species_state carries it",
      get_species_state(get_species_by_id(md, "trimer")),
      {"structural_state": None, "modifications": [], "multimer_cardinality": 3})
check("monomer and dimer are NOT the same state",
      get_species_state(get_species_by_id(md, "mono"))
      != get_species_state(get_species_by_id(md, "dimer")), True)
check("find_equivalent_species' key separates monomer from trimer",
      _state_key(get_species_state(get_species_by_id(md, "mono")))
      != _state_key(get_species_state(get_species_by_id(md, "trimer"))), True)
print(f"\n{'ALL PASS' if not failures else str(len(failures)) + ' FAILURE(S): ' + str(failures)}")
sys.exit(1 if failures else 0)
