"""Tests for the class-aware annotation model (`cdutils.namespaces`).

The expectations encode `pd-map-housekeeping.md` §0-§5. When a rule in those documents
changes, a test here should change with it.

    python3 -m pytest tests/ -q        (or: python3 tests/test_annotation_model.py)
"""

from cdutils.annotations import _correct_qualifier
from cdutils.namespaces import (
    PROTEIN_HYPOTHETICAL, canonical_namespace, expected_qualifier, is_expected,
)

# (current qualifier, namespace, element class, expected correction or None)
QUALIFIER_CASES = [
    # identity parked under a literature qualifier — the term is right, the qualifier is not
    ("isDescribedBy", "obo.go", "PHENOTYPE", "is"),
    ("isDescribedBy", "obo.chebi", "SIMPLE_MOLECULE", "is"),
    ("isDescribedBy", "pubchem.compound", "SIMPLE_MOLECULE", "is"),
    ("isDescribedBy", "mesh", "SIMPLE_MOLECULE", "is"),          # §0: mesh is identity here
    # qualifiers with no slot in the model at all
    # `reactome` is a reaction identifier under `is` and a pathway identifier under
    # `isPartOf`; equally specific, so the model refuses to choose (needs a lookup).
    ("hasVersion", "reactome", "REACTION", None),
    ("hasVersion", "obo.go", "PHENOTYPE", "is"),
    ("hasVersion", "obo.go", "COMPARTMENT", "is"),
    ("isVersionOf", "kegg.reaction", "REACTION", "is"),   # reaction id, not a pathway
    ("isVersionOf", "pubchem.substance", "SIMPLE_MOLECULE", "is"),
    # literature parked under identity
    ("is", "pubmed", "REACTION", "isDescribedBy"),
    ("is", "pubmed", "COMPARTMENT", "isDescribedBy"),
    # class-specific rules outrank the generic ANY_ELEMENT rule
    ("is", "obo.go", "REACTION", "isPartOf"),
    ("isPartOf", "ec-code", PROTEIN_HYPOTHETICAL, "is"),
    # ec-code has no home on a fully identified protein — left alone, reported for a ruling
    ("isPartOf", "ec-code", "PROTEIN", None),
    ("is", "interpro", "GENE", "encodes"),
    # already valid — never touched
    ("is", "obo.go", PROTEIN_HYPOTHETICAL, None),    # the "PROTEIN (hypothetical)" row
    ("is", "pubchem.substance", "SIMPLE_MOLECULE", None),   # ruling 2026-09-01: SIDs stay
    ("is", "obo.clo", "COMPARTMENT", None),          # §2: Cell Ontology under obo.clo
    ("is", "ec-code", "COMPLEX", None),              # §5: collective function on the parent
    ("occursIn", "taxonomy", "REACTION", None),      # §3: must survive a correction pass
    ("occursIn", "obo.clo", "REACTION", None),
    # The §3 [EXCEPTION] that allowed GO under occursIn on a reaction was withdrawn from
    # the ops docs, so a GO term there is now routed to isPartOf like any other element's.
    ("occursIn", "obo.go", "REACTION", "isPartOf"),
    # §3: a reaction's taxonomy is evidence context, so it belongs under occursIn — the
    # generic "isPartOf taxonomy on ANY ELEMENT" rule is the less specific one here
    ("isPartOf", "taxonomy", "REACTION", "occursIn"),
    ("isDescribedBy", "pubmed", "PROTEIN", None),
    # the InterPro convention, straight out of the table's PROTEIN / PROTEIN (hypothetical)
    # split: family identifier = identity on a group glyph, domain = part on a real protein
    ("hasPart", "interpro", PROTEIN_HYPOTHETICAL, "is"),
    ("isPartOf", "interpro", PROTEIN_HYPOTHETICAL, "is"),
    ("is", "interpro", PROTEIN_HYPOTHETICAL, None),
    ("is", "interpro", "PROTEIN", "isPartOf"),
    ("isPartOf", "interpro", "PROTEIN", None),
    # kegg.reaction identifies the reaction; kegg.pathway places it in a pathway
    ("isPartOf", "kegg.reaction", "REACTION", "is"),
    ("is", "kegg.pathway", "REACTION", "isPartOf"),
    # outside the model — left alone rather than forced
    ("is", "ncit", "COMPARTMENT", None),
    ("is", "omim", "PHENOTYPE", None),
    ("hasVersion", "reactome", "SIMPLE_MOLECULE", None),
]


def test_qualifier_corrections():
    for qualifier, namespace, element_class, want in QUALIFIER_CASES:
        got = _correct_qualifier(qualifier, namespace, element_class)
        assert got == want, (
            f"{qualifier} {namespace} on {element_class}: got {got!r}, want {want!r}")


def test_occurs_in_survives_a_correction_pass():
    """A reaction's occursIn context must not be rewritten as isPartOf.

    This is the failure the ops documents warn about: taxonomy classed globally as
    "isPartOf" wrecks `occursIn` on every reaction it touches.
    """
    for namespace in ("taxonomy", "obo.clo", "obo.bto", "mesh"):
        assert _correct_qualifier("occursIn", namespace, "REACTION") is None


def test_mesh_is_identity_not_literature():
    """§0 lists mesh under bqbiol:is for entities; it is not a literature namespace here."""
    assert is_expected("is", "mesh", "PHENOTYPE")
    assert not is_expected("isDescribedBy", "mesh", "PHENOTYPE")


def test_namespace_aliases():
    assert canonical_namespace("go") == "obo.go"
    assert canonical_namespace("chebi") == "obo.chebi"
    assert canonical_namespace("pubchem.cid") == "pubchem.compound"
    assert canonical_namespace("cl") == "obo.clo"
    # a SID is not a CID, and a symbol is not an HGNC id — neither may be rewritten
    assert canonical_namespace("pubchem.substance") == "pubchem.substance"
    assert canonical_namespace("hgnc.symbol") == "hgnc.symbol"


def test_unknown_namespace_is_left_alone():
    # `omim` was in this list until 2026-09-08, when the curator gave PHENOTYPE an `omim` row:
    # a disease phenotype glyph is legitimately identified by its OMIM entry. `ncit` left it
    # 2026-09-30 for the same reason (see test_ncit_identity below). Moved to positive
    # assertions rather than deleted, so the ruling is what the test encodes.
    for namespace in ("uniprot.isoform", "brenda", "rhea", "pfam"):
        assert expected_qualifier(namespace, "PHENOTYPE") is None


def test_ncit_identity():
    """Curator ruling 2026-09-30, mirroring the curation-ops COMPLEX and PHENOTYPE rows.

    NCIt already identified COMPARTMENT glyphs (2026-09-10); the curator extended it to
    COMPLEX and PHENOTYPE — `globular actin` = NCIT:C32646 "G-actin", a molecular form MeSH
    covers only generically (`Actins` D000199).
    """
    assert expected_qualifier("ncit", "COMPLEX") == "is"
    assert expected_qualifier("ncit", "PHENOTYPE") == "is"
    assert expected_qualifier("ncit", "COMPARTMENT") == "is"
    # An identity namespace only — a reaction is not identified by an NCIt concept here.
    assert expected_qualifier("ncit", "REACTION") is None


def test_omim_identifies_a_phenotype():
    """Curator ruling 2026-09-08, mirroring the curation-ops PHENOTYPE row."""
    assert expected_qualifier("omim", "PHENOTYPE") == "is"
    # It is a PHENOTYPE identity only — a reaction is not identified by a disease entry.
    assert expected_qualifier("omim", "REACTION") is None
    assert expected_qualifier("omim", "PROTEIN") is None


def test_a_sid_can_be_a_complex_component():
    """Curator ruling 2026-09-08: `hasPart` on a COMPLEX admits `pubchem.substance`.

    A component may have no compound record at all (neuromelanin), and the 2026-09-01 ruling
    forbids rewriting a SID to a CID, so the SID has to be admissible where it stands.
    """
    assert expected_qualifier("pubchem.substance", "COMPLEX") in ("is", "hasPart")
    assert is_expected("hasPart", "pubchem.substance", "COMPLEX")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
    print("all tests passed")
