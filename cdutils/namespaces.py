"""XML namespace constants and qualifier classification sets for CellDesigner SBML."""

# Core XML namespaces
SBML    = "http://www.sbml.org/sbml/level2/version4"
CD      = "http://www.sbml.org/2001/ns/celldesigner"
RDF     = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
BQBIOL  = "http://biomodels.net/biology-qualifiers/"
BQMODEL = "http://biomodels.net/model-qualifiers/"
DC      = "http://purl.org/dc/elements/1.1/"
DCTERMS = "http://purl.org/dc/terms/"
VCARD   = "http://www.w3.org/2001/vcard-rdf/3.0#"
XHTML   = "http://www.w3.org/1999/xhtml"

# XPath prefix map for lxml (covers all namespaces needed in queries)
NS = {
    "sbml":    SBML,
    "cd":      CD,
    "rdf":     RDF,
    "bqbiol":  BQBIOL,
    "bqmodel": BQMODEL,
    "xhtml":   XHTML,
}

# Namespace map used when building new RDF elements
RDF_NSMAP = {
    "rdf":     RDF,
    "bqbiol":  BQBIOL,
    "bqmodel": BQMODEL,
    "dc":      DC,
    "dcterms": DCTERMS,
    "vCard":   VCARD,
}

# ---------------------------------------------------------------------------
# Annotation model
# ---------------------------------------------------------------------------
#
# Which MIRIAM namespaces are expected under which qualifier, per element class.
# Transcribed from `curation-ops.md` § "Annotation and qualifier model", which is the
# authoritative specification (`pd-map-housekeeping.md` §0 defers to it "without
# exceptions"). Entries the table omits but the surrounding prose requires are marked
# PROSE-ONLY with their source — those are doc gaps, not liberties taken here.
#
# The qualifier for an identifier is NOT a property of the namespace alone — `obo.go` is
# identity on a phenotype, context under `isPartOf` on a protein, and evidence context under
# `occursIn` on a reaction. A flat namespace → qualifier map cannot express that, so the model
# is keyed (qualifier, element class).
#
# `ANY_ELEMENT` applies to every element, reactions included; `REACTION` entries apply only to
# reactions.

ANY_ELEMENT = "ANY"
REACTION = "REACTION"
# Conditional class: the annotation model's "PROTEIN (hypothetical)" row. Resolved per glyph,
# not per element type — see `model_class`.
PROTEIN_HYPOTHETICAL = "PROTEIN (hypothetical)"

# A conditional class also gets everything its base class allows.
CLASS_INHERITS = {PROTEIN_HYPOTHETICAL: "PROTEIN"}

_RNA_LIKE = ("GENE", "RNA", "ANTISENSE_RNA")

ANNOTATION_MODEL: dict[str, dict[str, set[str]]] = {
    "is": {
        "PROTEIN": {"uniprot", "obo.pr"},
        # The table's "PROTEIN (hypothetical)" row: group/function identifiers, legitimate
        # only on a glyph standing for a protein group or function. Inherits PROTEIN via
        # CLASS_INHERITS — hypothetical glyphs do also carry uniprot in this map.
        # pfam added 2026-09-30, mirroring the curation-ops PROTEIN (hypothetical) row the
        # curator extended: a family-protein glyph identified by its Pfam family (e.g.
        # `cyclic nucleotide phosphodiesterase` = PF00233) where InterPro alone was the only slot.
        PROTEIN_HYPOTHETICAL: {"interpro", "ec-code", "mesh", "obo.go", "pfam"},
        **{cls: {"hgnc", "ncbigene", "ensembl", "refseq", "obo.so"} for cls in _RNA_LIKE},
        # omim added 2026-09-08, mirroring the curation-ops PHENOTYPE row: a disease
        # phenotype glyph is legitimately identified by its OMIM entry, and the map
        # already carried four (friedreich ataxia, KRS, mucolipidosis type IV, ceroid
        # lipofuscinosis) that the model had no slot for.
        # ncit added 2026-09-30, mirroring the curation-ops PHENOTYPE row the curator extended.
        "PHENOTYPE": {"obo.go", "mesh", "omim", "ncit"},
        # obo.pr added 2026-09-03, mirroring the curation-ops COMPLEX row: a Protein Ontology
        # family term names a complex glyph that stands for a family (flotillin, PR:000050014)
        # rather than a named assembly. It is on the plain COMPLEX row, not a conditional one,
        # so it does not depend on the glyph being `hypothetical`.
        # obo.chebi added 2026-09-08, mirroring the curation-ops COMPLEX row and closing the
        # question held open since 2026-09-02: a complex whose *identity* is a chemical
        # (`iron-sulfur cluster` CHEBI:30408, `reducing agents` CHEBI:63247) takes it under
        # `is`. The hold was that such a glyph could read as containing itself, since the
        # `hasPart` row also admits obo.chebi — measured across the map, no glyph does: the
        # four heme-named complexes (`PTGS2:heme`, `MT-CYB:heme b`) are member-named, which §5
        # already exempts from `is`.
        # ncit added 2026-09-30, mirroring the curation-ops COMPLEX row the curator extended:
        # a complex glyph standing for a molecular form named in NCI Thesaurus but absent from
        # the other registries (`globular actin` = NCIT:C32646 "G-actin", where MeSH has only
        # the generic `Actins` D000199) is identified by its NCIt concept.
        "COMPLEX": {"obo.go", "mesh", "ec-code", "interpro", "obo.pr", "obo.chebi", "ncit"},
        "SIMPLE_MOLECULE": {"obo.chebi", "pubchem.compound", "pubchem.substance", "mesh"},
        "ION": {"obo.chebi", "pubchem.compound", "pubchem.substance", "mesh"},
        "DRUG": {"drugbank", "chembl", "obo.chebi", "pubchem.compound", "pubchem.substance",
                 "mesh"},
        # `ncit` and `obo.bto` added 2026-09-10, mirroring the curation-ops COMPARTMENT row
        # the curator extended the same day. `ncit` had been in the document and *not* here
        # since before the harmonisation project — 45 correct annotations reported as `Q3` on
        # one diagram — because the mechanical §0 diff covers the two exception *lists* and
        # not the qualifier tables. `obo.bto` (BRENDA Tissue Ontology) is used on anatomical
        # compartments in three diagrams and previously had only an occursIn/REACTION slot.
        # `obo.pato` added 2026-09-11, mirroring the curation-ops COMPARTMENT row (which
        # spells it `pato`; the house form carries the `obo.` prefix, and `pato` is registered
        # in NAMESPACE_ALIASES so both resolve — see the §2 `obo.clo`-not-`cl` convention).
        # PATO supplies the *quality* half of a two-part compartment identity: the curator's
        # `apoptotic neuron` fix is `obo.clo:CL:0000540` (neuron) + `obo.pato:PATO:0000638`
        # (apoptotic), which names the thing and its state separately instead of trying to
        # find one GO term for both.
        "COMPARTMENT": {"obo.clo", "obo.go", "mesh", "ncit", "obo.bto", "obo.pato"},
        # A reaction identifier — as opposed to the pathway identifier that the same
        # namespace carries under isPartOf. `reactome` therefore appears under both, which
        # makes it deliberately ambiguous: telling a Reactome reaction id from a pathway id
        # needs a lookup, not a rule.
        REACTION: {"kegg.reaction", "reactome"},
    },
    "isEncodedBy": {
        "PROTEIN": {"hgnc", "ncbigene", "ensembl"},
    },
    "encodes": {
        **{cls: {"uniprot", "obo.pr", "interpro", "ec-code"} for cls in ("GENE", "RNA")},
    },
    "isPartOf": {
        "PROTEIN": {"interpro"},
        ANY_ELEMENT: {"taxonomy", "obo.go"},
        # pathway identifiers only; `kegg.reaction` is a reaction identifier and sits under `is`
        REACTION: {"reactome", "kegg.pathway", "wikipathways"},
    },
    "hasPart": {
        # A complex named by its function carries its components here, not under `is` —
        # curation-ops table row added 2026-09-02.
        # pubchem.substance added 2026-09-08, mirroring the curation-ops hasPart
        # COMPLEX row: a complex can have a component that only has a SID, and the
        # 2026-09-01 ruling forbids rewriting a SID to pubchem.compound (the same
        # number there is an unrelated record). `neuromelanin C1q complex` is the
        # case — neuromelanin carries pubchem.substance:96022111 and has no
        # compound record at all.
        "COMPLEX": {"uniprot", "obo.pr", "obo.chebi", "pubchem.compound",
                    "pubchem.substance"},
    },
    "occursIn": {
        # obo.go was admitted here while housekeeping §3 carried an [EXCEPTION] allowing GO
        # under occursIn on a reaction. That exception has been removed from the docs, and no
        # reaction in the map uses occursIn at all, so the entry goes with it.
        REACTION: {"taxonomy", "obo.clo", "obo.bto", "mesh"},
    },
    "isDescribedBy": {
        ANY_ELEMENT: {"pubmed", "doi", "wikipedia.en"},
    },
}

# Order used when several qualifiers could host a namespace; identity first.
QUALIFIER_ORDER = ("is", "isEncodedBy", "encodes", "isPartOf", "hasPart", "occursIn",
                   "isDescribedBy")


def expected_namespaces(qualifier: str, element_class: str | None) -> set[str]:
    """Namespaces the model expects under *qualifier* for *element_class*.

    *element_class* is a CellDesigner species class (``"PROTEIN"``, ``"PHENOTYPE"``, …),
    ``"COMPARTMENT"``, or ``"REACTION"``. ``None`` means the class is unknown, in which case
    the union over all classes is returned — enough to tell a plainly wrong qualifier from a
    plausible one, but not enough to correct safely.
    """
    table = ANNOTATION_MODEL.get(qualifier)
    if not table:
        return set()
    if element_class is None:
        return set().union(*table.values())
    allowed = set(table.get(ANY_ELEMENT, set()))
    allowed |= table.get(element_class, set())
    parent = CLASS_INHERITS.get(element_class)
    if parent:
        allowed |= table.get(parent, set())
    return allowed


def model_class(element, species_class: str | None = None) -> str | None:
    """The annotation-model class for *element*, resolving conditional classes.

    A hypothetical protein glyph maps to ``PROTEIN (hypothetical)`` rather than ``PROTEIN``,
    because the model gives the two different identity namespaces. Pass *species_class* if it
    has already been computed.
    """
    from .species import get_species_class, is_hypothetical
    cls = species_class or get_species_class(element)
    if cls == "PROTEIN" and is_hypothetical(element):
        return PROTEIN_HYPOTHETICAL
    return cls


def specificity(qualifier: str, namespace: str, element_class: str | None) -> int:
    """How specifically the model endorses *namespace* under *qualifier* for this class.

    ``3`` a rule naming the exact class · ``2`` a rule naming its base class · ``1`` the
    generic ``ANY_ELEMENT`` rule · ``0`` accepted only because the class is unknown ·
    ``-1`` not accepted at all.

    Comparing specificities is what lets an exact-class rule override an inherited one: on a
    ``PROTEIN (hypothetical)`` glyph ``interpro`` is endorsed under ``is`` at 3 and under
    ``isPartOf`` only at 2 (inherited from ``PROTEIN``), so it belongs under ``is``.
    """
    table = ANNOTATION_MODEL.get(qualifier, {})
    if not table:
        return -1
    if element_class is not None and namespace in table.get(element_class, set()):
        return 3
    parent = CLASS_INHERITS.get(element_class) if element_class else None
    if parent and namespace in table.get(parent, set()):
        return 2
    if namespace in table.get(ANY_ELEMENT, set()):
        return 1
    if element_class is None and namespace in set().union(*table.values(), set()):
        return 0
    return -1


def is_expected(qualifier: str, namespace: str, element_class: str | None) -> bool:
    """True if *namespace* is valid under *qualifier* for this element class."""
    return namespace in expected_namespaces(qualifier, element_class)


# Accepted where they already occur, but never proposed as the target of a correction.
# Empty since the §3 GO-under-occursIn exception was withdrawn; kept as the hook for the next
# "allowed, but not canonical" rule.
NEVER_PROPOSED: dict[str, set[str]] = {}


def expected_qualifier(namespace: str, element_class: str | None) -> str | None:
    """The qualifier *namespace* belongs under for this element class.

    Specificity decides (see :func:`specificity`): a rule naming the exact class beats one
    naming its base class, which beats the generic ``ANY_ELEMENT`` rule. That is what
    implements the InterPro convention — on a ``PROTEIN (hypothetical)`` glyph the family
    identifier is identity (``is``, exact class), while on a plain ``PROTEIN`` the same
    namespace is listed only under ``isPartOf``, so a domain there is a part.

    Returns ``None`` when the model does not know the namespace, or when two *equally*
    specific qualifiers accept it — ``reactome`` on a reaction is a reaction identifier under
    ``is`` and a pathway identifier under ``isPartOf``, and telling those apart needs a
    lookup, not a rule.
    """
    best: list[str] = []
    best_rank = -1
    for qualifier in QUALIFIER_ORDER:
        if namespace in NEVER_PROPOSED.get(qualifier, set()):
            continue
        rank = specificity(qualifier, namespace, element_class)
        if rank < 0:
            continue
        if rank > best_rank:
            best, best_rank = [qualifier], rank
        elif rank == best_rank:
            best.append(qualifier)
    return best[0] if len(best) == 1 else None


# §0 "Namespace / MIRIAM normalisation" — prefix spellings of the *same* identifier.
NAMESPACE_ALIASES = {
    "go": "obo.go",
    "chebi": "obo.chebi",
    "so": "obo.so",
    "pato": "obo.pato",
    "cl": "obo.clo",
    "pubchem.cid": "pubchem.compound",
}

# Namespaces that look like aliases but are not: the identifier itself would have to be
# re-resolved, so a prefix rewrite would silently repoint the annotation at another record.
# `pubchem.substance` holds SIDs, which are unrelated to the CIDs of `pubchem.compound`.
NEVER_ALIASED = {"pubchem.substance", "hgnc.symbol"}


def canonical_namespace(namespace: str) -> str:
    """Canonical spelling of *namespace* per §0, or *namespace* unchanged."""
    if namespace in NEVER_ALIASED:
        return namespace
    return NAMESPACE_ALIASES.get(namespace, namespace)


# ---------------------------------------------------------------------------
# Legacy flat sets — derived from the model, kept for backwards compatibility
# ---------------------------------------------------------------------------
# These cannot express the class dependence above and are therefore only an approximation:
# prefer `expected_qualifier()`. Note `mesh` now appears in IDENTITY_NAMESPACES, because §0
# lists it under `bqbiol:is` for most element classes; it was previously classed as
# literature, which moved entity identities to `isDescribedBy`.

IDENTITY_NAMESPACES = set().union(*ANNOTATION_MODEL["is"].values())
LITERATURE_NAMESPACES = set(ANNOTATION_MODEL["isDescribedBy"][ANY_ELEMENT])
TAXONOMY_NAMESPACES = {"taxonomy"}


# Valid protein types
PROTEIN_TYPES = {"GENERIC", "ION_CHANNEL", "RECEPTOR", "TRUNCATED"}

# Valid species classes
SPECIES_CLASSES = {
    "PROTEIN", "GENE", "RNA", "ANTISENSE_RNA", "COMPLEX",
    "SIMPLE_MOLECULE", "ION", "DRUG", "PHENOTYPE",
    "DEGRADED", "UNKNOWN", "OVAL", "SQUARE",
}

# Valid reaction types
REACTION_TYPES = {
    "STATE_TRANSITION", "HETERODIMER_ASSOCIATION", "DISSOCIATION",
    "TRANSPORT", "TRANSCRIPTION", "TRANSLATION", "TRUNCATION",
    "KNOWN_TRANSITION_OMITTED", "UNKNOWN_TRANSITION",
    "POSITIVE_INFLUENCE", "NEGATIVE_INFLUENCE", "TRIGGER", "MODULATION",
    "BOOLEAN_LOGIC_GATE_AND", "BOOLEAN_LOGIC_GATE_OR",
    "BOOLEAN_LOGIC_GATE_NOT", "BOOLEAN_LOGIC_GATE_UNKNOWN",
    # Influence-style and modifier-style types CellDesigner also writes as a reaction's own
    # type — all in use across the PD map and the AD knowledge graph.
    "BOOLEAN_LOGIC_GATE",
    "CATALYSIS", "UNKNOWN_CATALYSIS", "INHIBITION", "UNKNOWN_INHIBITION",
    "PHYSICAL_STIMULATION",
    "UNKNOWN_POSITIVE_INFLUENCE", "UNKNOWN_NEGATIVE_INFLUENCE",
    "REDUCED_MODULATION", "REDUCED_TRIGGER", "REDUCED_PHYSICAL_STIMULATION",
    "UNKNOWN_REDUCED_MODULATION", "UNKNOWN_REDUCED_TRIGGER",
    "UNKNOWN_REDUCED_PHYSICAL_STIMULATION",
    "TRANSCRIPTIONAL_ACTIVATION", "TRANSCRIPTIONAL_INHIBITION",
    "TRANSLATIONAL_ACTIVATION", "TRANSLATIONAL_INHIBITION",
}

# Valid modifier types (celldesigner:modification/@type)
MODIFIER_TYPES = {
    "CATALYSIS", "PHYSICAL_STIMULATION", "INHIBITION",
    "UNKNOWN_CATALYSIS", "UNKNOWN_INHIBITION", "TRIGGER", "MODULATION",
}
