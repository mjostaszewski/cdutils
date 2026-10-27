# CellDesigner SBML XML Specification

CellDesigner is a process diagram editor, used to construct molecular interaction diagrams.
Its files are .xml, and its data format is a mix of SBML 2.4 and its own schema.

## Quick reference for parsers

- The word "species" means elements (molecules, complexes, phenotypes, etc.)
- species (`listOfSpecies`), reactions (`listOfReactions`) and compartments (`listOfCompartments`) follow SBML Level 2 Version 4
  - CellDesigner tags inside these provide additional semantic and layout information
- `<annotation>` tags contain structured annotations (RDF, bqbiol namespaces), using outdated MIRIAM URI encoding
- Complexes are a special type of species with "nesting"; elements inside complexes are NOT listed among `sbml:species`, but as `celldesigner:species` in `listOfIncludedSpecies`
- Included species: CellDesigner does not allow included species to have `<annotation>` tags. To provide structured annotations, sometimes RDF XML is embedded in `<notes>` XHTML body
- Aliases are instances of species and compartments carrying graphical and layout information
- CellDesigner-specific elements: unique classes for Proteins, Genes, RNAs, AntisenseRNAs, etc.

---

## 1. Namespaces

| Prefix | URI | Used for |
|--------|-----|----------|
| *(default)* | `http://www.sbml.org/sbml/level2/version4` | SBML Level 2 Version 4 |
| `celldesigner:` | `http://www.sbml.org/2001/ns/celldesigner` | CellDesigner extensions |
| `rdf:` | `http://www.w3.org/1999/02/22-rdf-syntax-ns#` | RDF annotations |
| `bqbiol:` | `http://biomodels.net/biology-qualifiers/` | Biological qualifiers |
| `bqmodel:` | `http://biomodels.net/model-qualifiers/` | Model qualifiers |
| `dc:` | `http://purl.org/dc/elements/1.1/` | Dublin Core metadata |
| `dcterms:` | `http://purl.org/dc/terms/` | Dublin Core terms |
| `vCard:` | `http://www.w3.org/2001/vcard-rdf/3.0#` | vCard (inside RDF) |
| *(xhtml)* | `http://www.w3.org/1999/xhtml` | Inside `<notes>` blocks |

RDF namespace declarations are inline on each `rdf:RDF` block, not on the root element.

---

## 2. Document structure

```
sbml [@level="2" @version="4"]
  model [@metaid @id]
    notes                                          # XHTML: author info, description
    annotation
      celldesigner:extension
        celldesigner:modelVersion                  # always "4.0"
        celldesigner:modelDisplay                  # canvas size (@sizeX, @sizeY)
        celldesigner:listOfIncludedSpecies         # species inside complexes
        celldesigner:listOfCompartmentAliases       # compartment layout
        celldesigner:listOfComplexSpeciesAliases    # complex layout
        celldesigner:listOfSpeciesAliases           # species layout
        celldesigner:listOfGroups                   # often empty
        celldesigner:listOfProteins                 # protein definitions
        celldesigner:listOfGenes                    # gene definitions
        celldesigner:listOfRNAs                     # RNA definitions
        celldesigner:listOfAntisenseRNAs            # antisense RNA definitions
        celldesigner:listOfLayers                   # often empty
        celldesigner:listOfBlockDiagrams            # often empty
    listOfUnitDefinitions                          # SBML standard units
    listOfCompartments                             # cellular locations
    listOfSpecies                                  # all top-level species
    listOfReactions                                # all reactions
```

---

## 3. Model-level notes

```xml
<model metaid="..." id="...">
  <notes>
    <html xmlns="http://www.w3.org/1999/xhtml">
      <head><title/></head>
      <body>Author info and description as plain text with <br/> tags</body>
    </html>
  </notes>
```

Notes always wrap content in XHTML `<html>/<head>/<body>`. The `<title/>` is typically empty/self-closing.

---

## 4. Compartments (`listOfCompartments`)

```xml
<compartment metaid="c5" id="c5" name="cell" size="1" units="volume" outside="c2">
  <annotation>
    <celldesigner:extension>
      <celldesigner:name>cell</celldesigner:name>
    </celldesigner:extension>
    <rdf:RDF ...>
      <rdf:Description rdf:about="#c5">
        <bqbiol:is>
          <rdf:Bag>
            <rdf:li rdf:resource="urn:miriam:obo.go:GO%3A0005737"/>
          </rdf:Bag>
        </bqbiol:is>
      </rdf:Description>
    </rdf:RDF>
  </annotation>
</compartment>
```

**Key points:**
- Nesting is expressed via the `outside` attribute (SBML L2 convention): e.g. nucleus has `outside="cell"`, cell has `outside="human host"`
- A `default` compartment always exists (no `outside` attribute); it represents the area not covered by any named compartment and is the implicit root — all top-level compartments have `outside="default"`. It has **no `name` attribute** (only `id="default"`), cannot be annotated, and cannot be interacted with in CellDesigner. When reading compartment names, fall back to `id` if `name` is absent.
- Each compartment has `celldesigner:extension` with `celldesigner:name`
- RDF annotations on compartments use `bqbiol:is` with GO term URIs (URL-encoded, e.g. `GO%3A0005737`)

**Compartment names found across diagrams (63 unique):** nucleus, endoplasmic reticulum, mitochondrion, Golgi apparatus, cell membrane, lysosome, blood, various vesicle types, extracellular space, etc.

---

## 5. Species (`listOfSpecies`)

### 5.1 Species classes

The `celldesigner:class` element defines the molecular type. Classes found across all diagrams:

| Class | Reference element | Description |
|-------|------------------|-------------|
| `PROTEIN` | `proteinReference` | Protein; references `listOfProteins` |
| `GENE` | `geneReference` | Gene; references `listOfGenes` |
| `RNA` | `rnaReference` | RNA molecule; references `listOfRNAs` |
| `ANTISENSE_RNA` | `antisenseRNAReference` | Antisense RNA; references `listOfAntisenseRNAs` |
| `COMPLEX` | *(none — uses `name`)* | Molecular complex; subunits in `listOfIncludedSpecies` |
| `SIMPLE_MOLECULE` | *(uses `name`)* | Small molecule (ATP, ions, etc.) |
| `ION` | *(uses `name`)* | Ion species |
| `DRUG` | *(uses `name`)* | Drug/pharmaceutical |
| `PHENOTYPE` | *(uses `name`)* | Biological process/outcome (e.g. "Apoptosis") |
| `DEGRADED` | *(uses `name`)* | Degradation product |
| `UNKNOWN` | *(uses `name`)* | Unknown/unclassified entity |
| `OVAL` | *(uses `name`)* | Oval-shaped generic entity |
| `SQUARE` | *(uses `name`)* | Square-shaped generic entity |

### 5.2 Species structure

```xml
<species metaid="s15" id="s15" name="BCL2" compartment="c1" initialAmount="0">
  <notes>
    <html xmlns="http://www.w3.org/1999/xhtml">
      <head><title/></head>
      <body>free-text annotations, aliases, database IDs</body>
    </html>
  </notes>
  <annotation>
    <celldesigner:extension>
      <celldesigner:positionToCompartment>inside</celldesigner:positionToCompartment>
      <celldesigner:speciesIdentity>
        <celldesigner:class>PROTEIN</celldesigner:class>
        <celldesigner:proteinReference>pr12</celldesigner:proteinReference>
        <celldesigner:state>                                <!-- optional -->
          <celldesigner:listOfModifications>
            <celldesigner:modification residue="rs1" state="phosphorylated"/>
          </celldesigner:listOfModifications>
        </celldesigner:state>
      </celldesigner:speciesIdentity>
      <celldesigner:listOfCatalyzedReactions>              <!-- optional -->
        <celldesigner:catalyzed reaction="re4"/>
      </celldesigner:listOfCatalyzedReactions>
    </celldesigner:extension>
    <rdf:RDF ...>...</rdf:RDF>
  </annotation>
</species>
```

**SBML attributes on species:** `metaid`, `id`, `name`, `compartment`, `initialAmount` (always 0).

**CellDesigner extension elements:**
- `positionToCompartment`: always `"inside"`
- `speciesIdentity`: contains `class` + type-specific reference + optional `state`
- `listOfCatalyzedReactions`: optional list of reactions this species catalyzes
- `hypothetical`: `"true"` on some COMPLEX species

### 5.3 Modification states

The `celldesigner:modification` element inside `speciesIdentity > state > listOfModifications` uses:
- `@residue`: references a residue ID from the protein/gene definition
- `@state`: one of: **`phosphorylated`**, **`ubiquitinated`**, **`acetylated`**, **`glycosylated`**, **`empty`**, **`don't care`**

### 5.6 Homomultimers

A species can be flagged as a homomultimer via `<celldesigner:homodimer>N</celldesigner:homodimer>` inside `speciesIdentity/state`, where N is the number of copies (typically 2):

```xml
<celldesigner:speciesIdentity>
  <celldesigner:class>PROTEIN</celldesigner:class>
  <celldesigner:proteinReference>pr42</celldesigner:proteinReference>
  <celldesigner:state>
    <celldesigner:homodimer>2</celldesigner:homodimer>
  </celldesigner:state>
</celldesigner:speciesIdentity>
```

**Visual effect:** CellDesigner renders the alias as N overlapping copies of the glyph, offset slightly. This makes the alias physically larger than a non-multimer of the same type — typically ~86×46 for a homodimer protein vs ~47×28 for a regular one in original layouts. Any tool that resizes species by class must check for the homodimer flag and skip or handle these separately, since the visual overlap is intentional and sizing is not straightforward.

### 5.4 Complex species

Complexes use a two-level system:

1. **SBML level:** A `<species>` with class `COMPLEX` in `listOfSpecies`. Has `hypothetical` and `name`, no reference element.
2. **CellDesigner level:** Subunits are in `celldesigner:listOfIncludedSpecies` (inside `model > annotation > celldesigner:extension`). Each has `celldesigner:complexSpecies` pointing to the parent complex ID.
3. **Layout level:** Complex has a `complexSpeciesAlias`; each subunit has a `speciesAlias` with `@complexSpeciesAlias` attribute.

The same protein can appear multiple times with different IDs in different complexes, referencing the same `proteinReference` but with different modification states.

### 5.5 Included species (`listOfIncludedSpecies`)

```xml
<celldesigner:listOfIncludedSpecies>
  <celldesigner:species id="s1" name="MAPK8">
    <celldesigner:notes>
      <html xmlns="http://www.w3.org/1999/xhtml">
        <head><title/></head>
        <body>
          alias:JNK1 HGNC:6881 Uniprot:P45983 Entrez:5599
        </body>
      </html>
    </celldesigner:notes>
    <celldesigner:annotation>
      <celldesigner:complexSpecies>s86</celldesigner:complexSpecies>
      <celldesigner:speciesIdentity>
        <celldesigner:class>PROTEIN</celldesigner:class>
        <celldesigner:proteinReference>pr1</celldesigner:proteinReference>
        <celldesigner:state>
          <celldesigner:listOfModifications>
            <celldesigner:modification residue="rs1" state="phosphorylated"/>
          </celldesigner:listOfModifications>
        </celldesigner:state>
      </celldesigner:speciesIdentity>
    </celldesigner:annotation>
  </celldesigner:species>
</celldesigner:listOfIncludedSpecies>
```

**Critical parser consideration:** Included species use `celldesigner:annotation` (NOT SBML `annotation`). They cannot have SBML-level `<annotation>` tags. To provide structured annotations, some files embed RDF XML directly inside the `<celldesigner:notes>` XHTML body:

```xml
<celldesigner:notes>
  <html><head><title/></head>
    <body>
      Symbol: C6
      HGNC_ID: 1339
      <rdf:RDF xmlns:bqbiol="..." ...>
        <rdf:Description rdf:about="#s_id_sa320">
          <bqbiol:isDescribedBy>
            <rdf:Bag><rdf:li rdf:resource="urn:miriam:..."/></rdf:Bag>
          </bqbiol:isDescribedBy>
        </rdf:Description>
      </rdf:RDF>
    </body>
  </html>
</celldesigner:notes>
```

**A parser must check both `<annotation>` and `<notes>` for RDF blocks.**

---

## 6. CellDesigner entity definitions

### 6.1 Proteins (`listOfProteins`)

```xml
<celldesigner:protein id="pr12" name="BCL2" type="GENERIC">
  <celldesigner:listOfModificationResidues>
    <celldesigner:modificationResidue id="rs1" angle="1.178" side="none"/>
  </celldesigner:listOfModificationResidues>
</celldesigner:protein>
```

- `@id`: referenced by `proteinReference` in species
- `@name`: display name — **must be kept in sync with `sbml:species/@name`** (see below)
- `@type`: `GENERIC`, `ION_CHANNEL`, `RECEPTOR`, `TRUNCATED` — affects the glyph shape rendered by CellDesigner; `RECEPTOR` has a distinct visual style (taller glyph with a channel region)
- `listOfModificationResidues`: optional; each residue has `@id`, `@angle` (radians, visual position on glyph), `@side`

**Resolving protein type from a species alias:** the chain is `speciesAlias/@species` → `listOfSpecies/species` or `listOfIncludedSpecies/species` → `speciesIdentity/proteinReference` → `listOfProteins/protein/@type`. Both top-level and included species must be checked.

**Renaming a species requires updating two locations:**
1. `sbml:species/@name` — the SBML-level name attribute on the species element
2. `celldesigner:protein/@name` in `listOfProteins` — the CellDesigner display name, reached via `speciesIdentity/proteinReference` ID

Both must be updated together. If only `sbml:species/@name` is changed, CellDesigner will still render the old name (it reads from the protein definition). Similarly for genes: update `celldesigner:gene/@name` in `listOfGenes` via `geneReference`. Multiple species can share the same protein/gene definition (same `proteinReference` ID) — updating the definition renames all of them simultaneously.

### 6.2 Genes (`listOfGenes`)

```xml
<celldesigner:gene id="gn1" name="ACE2" type="GENE"/>
```

Similar structure to proteins. Referenced by `geneReference` in species.

### 6.3 RNAs (`listOfRNAs`)

```xml
<celldesigner:RNA id="rn1" name="mRNA-S" type="GENERIC"/>
```

Referenced by `rnaReference` in species.

### 6.4 AntisenseRNAs (`listOfAntisenseRNAs`)

```xml
<celldesigner:antisenseRNA id="ar1" name="miR-155" type="GENERIC"/>
```

Referenced by `antisenseRNAReference` in species.

---

## 7. Reactions (`listOfReactions`)

### 7.1 Reaction types

All reaction types found across diagrams:

| Type | Description |
|------|-------------|
| `STATE_TRANSITION` | Change of state (e.g. phosphorylation, conformational change) |
| `HETERODIMER_ASSOCIATION` | Two different molecules forming a complex |
| `DISSOCIATION` | Complex breaking apart |
| `TRANSPORT` | Movement between compartments |
| `TRANSCRIPTION` | DNA to RNA |
| `TRANSLATION` | RNA to protein |
| `TRUNCATION` | Protein cleavage |
| `KNOWN_TRANSITION_OMITTED` | Known reaction with details omitted |
| `UNKNOWN_TRANSITION` | Reaction with unknown mechanism |
| `POSITIVE_INFLUENCE` | Stimulatory effect |
| `NEGATIVE_INFLUENCE` | Inhibitory effect |
| `TRIGGER` | Causal influence triggering a downstream process |
| `MODULATION` | Regulatory effect (neither purely positive nor negative) |
| `BOOLEAN_LOGIC_GATE_AND` | Logical AND combining inputs |
| `BOOLEAN_LOGIC_GATE_OR` | Logical OR combining inputs |
| `BOOLEAN_LOGIC_GATE_NOT` | Logical NOT |
| `BOOLEAN_LOGIC_GATE_UNKNOWN` | Unspecified logic gate |

### 7.2 Reaction structure

Reactions have two parallel representations — CellDesigner (layout + semantic detail) and SBML (logical):

```xml
<reaction metaid="re2" id="re2" reversible="false">
  <notes><html>...<body>experimental context</body></html></notes>
  <annotation>
    <celldesigner:extension>
      <!-- Semantic detail -->
      <celldesigner:reactionType>STATE_TRANSITION</celldesigner:reactionType>
      <celldesigner:baseReactants>
        <celldesigner:baseReactant species="s60" alias="sa44"/>
      </celldesigner:baseReactants>
      <celldesigner:baseProducts>
        <celldesigner:baseProduct species="s6" alias="sa5">
          <celldesigner:linkAnchor position="W"/>
        </celldesigner:baseProduct>
      </celldesigner:baseProducts>
      <!-- Layout -->
      <celldesigner:connectScheme connectPolicy="direct" rectangleIndex="0">
        <celldesigner:listOfLineDirection>
          <celldesigner:lineDirection index="0" value="unknown"/>
        </celldesigner:listOfLineDirection>
      </celldesigner:connectScheme>
      <celldesigner:line width="1.0" color="ff000000"/>
      <celldesigner:editPoints>0.5,0.0</celldesigner:editPoints>  <!-- optional bend points -->
      <!-- Modifiers -->
      <celldesigner:listOfModification>
        <celldesigner:modification type="PHYSICAL_STIMULATION" modifiers="s49"
              aliases="csa2" targetLineIndex="-1,4" editPoints="0.649,-0.299">
          <celldesigner:connectScheme connectPolicy="direct">
            <celldesigner:listOfLineDirection>
              <celldesigner:lineDirection index="0" value="unknown"/>
            </celldesigner:listOfLineDirection>
          </celldesigner:connectScheme>
          <celldesigner:linkTarget species="s49" alias="csa2">
            <celldesigner:linkAnchor position="E"/>
          </celldesigner:linkTarget>
          <celldesigner:line width="1.0" color="ff000000"/>
        </celldesigner:modification>
      </celldesigner:listOfModification>
    </celldesigner:extension>
    <rdf:RDF ...>...</rdf:RDF>
  </annotation>

  <!-- Standard SBML participants -->
  <listOfReactants>
    <speciesReference metaid="CDMT00008" species="s60">
      <annotation>
        <celldesigner:extension>
          <celldesigner:alias>sa44</celldesigner:alias>
        </celldesigner:extension>
      </annotation>
    </speciesReference>
  </listOfReactants>
  <listOfProducts>
    <speciesReference metaid="CDMT00009" species="s6">
      <annotation>
        <celldesigner:extension>
          <celldesigner:alias>sa5</celldesigner:alias>
        </celldesigner:extension>
      </annotation>
    </speciesReference>
  </listOfProducts>
  <listOfModifiers>
    <modifierSpeciesReference metaid="CDMT00001" species="s49">
      <annotation>
        <celldesigner:extension>
          <celldesigner:alias>csa2</celldesigner:alias>
        </celldesigner:extension>
      </annotation>
    </modifierSpeciesReference>
  </listOfModifiers>
</reaction>
```

### 7.3 Modifier types in CellDesigner reactions

The `celldesigner:modification/@type` attribute specifies the regulatory role:
- `CATALYSIS` — enzymatic catalysis
- `PHYSICAL_STIMULATION` — non-enzymatic activation
- `INHIBITION` — inhibitory effect
- `UNKNOWN_CATALYSIS` — catalysis with unknown mechanism
- `UNKNOWN_INHIBITION` — inhibition with unknown mechanism
- `TRIGGER` — triggering effect
- `MODULATION` — general regulatory effect

### 7.4 Link anchor positions

Connection points on glyphs follow compass notation: `W`, `E`, `N`, `S`, `NW`, `NE`, `SW`, `SE`, `NNW`, `NNE`, `SSW`, `SSE`, `WNW`, `WSW`, `ENE`, `ESE`

**No kinetic laws** are present — these are qualitative/topological models, not quantitative.

---

## 8. Annotation patterns (RDF/MIRIAM)

### 8.1 Standard RDF block structure

```xml
<rdf:RDF xmlns:rdf="..." xmlns:dc="..." xmlns:dcterms="..."
         xmlns:vCard="..." xmlns:bqbiol="..." xmlns:bqmodel="...">
  <rdf:Description rdf:about="#{metaid}">
    <bqbiol:{qualifier}>
      <rdf:Bag>
        <rdf:li rdf:resource="urn:miriam:{database}:{identifier}"/>
      </rdf:Bag>
    </bqbiol:{qualifier}>
  </rdf:Description>
</rdf:RDF>
```

### 8.2 Qualifiers used — intended semantics vs. actual usage in the map

The COMBINE qualifier specification (qualifiers-1.1) defines the intended semantics. The table below shows both what each qualifier *should* mean and how it is *actually* used in the COVID-19 disease map (counted across all 22 diagrams, 2026-04-02).

| Qualifier | Intended semantics (COMBINE spec) | Top databases actually annotated with it | Assessment |
|-----------|----------------------------------|------------------------------------------|------------|
| `bqbiol:is` | Exact biological identity | uniprot (209), obo.go (100), kegg.reaction (72), taxonomy (70), ncbiprotein (23) | ✅ Mostly correct. Taxonomy here should use `bqbiol:isPartOf` instead. |
| `bqbiol:isDescribedBy` | Described by a publication or supporting resource | **ncbigene (2702), hgnc.symbol (2562)**, pubmed (2430), **uniprot (2009), ensembl (1256), refseq (1241), hgnc (1222)**, ec-code (1407) | ❌ Misused as a generic "annotated with." Only pubmed citations are correct. Identity annotations (UniProt, HGNC, Ensembl, RefSeq, NCBI gene) should use `bqbiol:is`. |
| `bqbiol:isEncodedBy` | This protein/RNA is encoded by the referenced **gene** | **uniprot (467), taxonomy (368), obo.chebi (351), obo.go (256), hgnc (130), hgnc.symbol (121), ncbiprotein (74)** | ❌ Systematically misused. None of these are encoding genes. UniProt/NCBI protein should be `bqbiol:is`; taxonomy should be `bqbiol:isPartOf`; ChEBI/GO do not encode proteins. |
| `bqbiol:hasTaxon` | Taxonomic restriction of this entity | *(not observed)* | ❌ Not supported by CellDesigner — silently drops all annotations on elements that use it. Use `bqbiol:isPartOf` for taxonomy instead. |
| `bqbiol:hasPart` | Entity physically or logically includes this component | hgnc (48), mesh (14) | ⚠️ Plausible for complexes; HGNC used here is likely an error. |
| `bqbiol:isVersionOf` | More specific instance of a general concept | uniprot (12), obo.chebi (11) | ✅ Semantically acceptable for proteins as instances of a protein family/class. |
| `bqbiol:encodes` | This gene encodes the referenced entity | hgnc.symbol (11), ncbigene (1) | ⚠️ Direction is plausible for gene-class elements but targets are symbols, not proteins. |
| `bqbiol:occursIn` | Physically limited to this location | taxonomy (156), obo.bto (90) | ⚠️ Used for tissue/organism context; semantically borderline (should be `isPartOf` for organism). |
| `bqmodel:is` | The *model object* (whole model) is identical to this resource | uniprot (73), pubmed (21), ncbiprotein (7) | ❌ `bqmodel:` qualifiers are for model-level metadata, not individual biological species. These should use `bqbiol:is`. |
| `bqmodel:isDescribedBy` | The *model object* is described by this resource | uniprot (74), pubmed (62), ncbiprotein (47) | ❌ Same issue: `bqmodel:` applied to individual species. Should use `bqbiol:is` or `bqbiol:isDescribedBy`. |

**Systemic qualifier issues in the map (pre-existing, out of scope for the harmonisation task):**

1. `bqbiol:isDescribedBy` is used as a catch-all "annotated with" for identity annotations (~7,200 cases of ncbigene, hgnc, uniprot, ensembl, refseq). The correct qualifier for an exact identity is `bqbiol:is`.
2. `bqbiol:isEncodedBy` is applied to protein UniProt accessions, taxonomy IDs, ChEBI terms, and GO terms (~1,200 cases) — none of which are genes that encode anything. This qualifier should only appear when linking a protein to its encoding gene.
3. `bqmodel:is` / `bqmodel:isDescribedBy` appear on individual species (~150 cases) rather than on the model as a whole.
4. `bqbiol:hasTaxon` is not supported by CellDesigner and must not be used — it silently drops all annotations on any element that carries it. Use `bqbiol:isPartOf` for taxonomy annotations instead.

**Practical guidance for parsers and annotation tools:**

- Do not rely on qualifier semantics to infer annotation type — the same database (e.g. UniProt) appears under `bqbiol:is`, `bqbiol:isDescribedBy`, `bqbiol:isEncodedBy`, and `bqmodel:is` across different elements. Use the URI prefix (e.g. `uniprot:`, `pubmed:`) to determine annotation type.
- When **adding** new annotations programmatically, use `bqbiol:is` for identities and `bqbiol:isDescribedBy` for literature. Do not perpetuate the existing misuse.
- When **replacing** an existing annotation, keep the original qualifier to avoid introducing additional inconsistencies until a systematic qualifier correction pass is done.

### 8.3 MIRIAM URI patterns

All identifiers use the `urn:miriam:{database}:{id}` format. 36 databases found across diagrams:

| URI pattern | Example | Count context |
|------------|---------|---------------|
| `urn:miriam:pubmed:{pmid}` | `urn:miriam:pubmed:31226023` | Literature |
| `urn:miriam:uniprot:{acc}` | `urn:miriam:uniprot:P45983` | Protein |
| `urn:miriam:hgnc.symbol:{sym}` | `urn:miriam:hgnc.symbol:ACE2` | Gene symbol |
| `urn:miriam:hgnc:{id}` | `urn:miriam:hgnc:6881` | HGNC numeric ID |
| `urn:miriam:ncbigene:{id}` | `urn:miriam:ncbigene:5599` | Entrez Gene |
| `urn:miriam:ensembl:{id}` | `urn:miriam:ensembl:ENSG00000107643` | Ensembl |
| `urn:miriam:refseq:{acc}` | `urn:miriam:refseq:NM_001278547` | RefSeq |
| `urn:miriam:taxonomy:{id}` | `urn:miriam:taxonomy:9606` | Organism |
| `urn:miriam:obo.go:GO%3A{id}` | `urn:miriam:obo.go:GO%3A0005737` | Gene Ontology (URL-encoded `:`) |
| `urn:miriam:ec-code:{ec}` | `urn:miriam:ec-code:2.7.11.1` | Enzyme Commission |
| `urn:miriam:chebi:CHEBI%3A{id}` | `urn:miriam:chebi:CHEBI%3A15422` | Chemical entity |
| `urn:miriam:kegg.compound:{id}` | `urn:miriam:kegg.compound:C00002` | KEGG compound |
| `urn:miriam:pubchem.substance:{id}` | — | PubChem substance |
| `urn:miriam:mesh:{id}` | — | MeSH |
| `urn:miriam:doi:{doi}` | — | DOI |
| `urn:miriam:ncbiprotein:{acc}` | — | NCBI protein |
| `urn:miriam:reactome:{id}` | — | Reactome pathway |
| `urn:miriam:wikipathways:{id}` | — | WikiPathways |

**Note:** Multiple `rdf:Bag` blocks per qualifier are common (one bag per identifier, rather than multiple `rdf:li` in one bag). A parser should collect all `rdf:li` across all bags for a given qualifier.

### 8.4 Individual Nsp protein identifiers

Individual Nsp proteins (processed products of ORF1ab polyprotein) should be annotated using **PRO Consortium identifiers** in the `obo.pr` namespace, not with UniProt chain (`#PRO_`) suffixes.

**Reason:** CellDesigner uses an older XML schema that does not accept the `uniprot:P0DTD1#PRO_XXXXXXXXXX` format. Although identifiers.org's `uniprot` namespace pattern allows the optional `#PRO_\d+` suffix, CellDesigner rejects it during validation.

**Correct format in XML:**
```xml
<rdf:li rdf:resource="urn:miriam:obo.pr:PR%3A000050276"/>
```

The `obo.pr` namespace is registered in identifiers.org. Internal colons within the identifier are URL-encoded as `%3A` in the XML attribute value (compact form `obo.pr:PR:000050276`).

**Critical:** UniProt `PRO_XXXXXXXXXX` chain IDs do **not** correspond 1:1 to PRO Consortium `PR:XXXXXXXXX` IDs. For example, for Nsp7: `PRO_0000449625` ≠ `PR:000050276`. Always use the PRO Consortium `PR:` IDs verified against proconsortium.org, not derived from UniProt chain numbers.

Full Nsp→PR mapping is in `specifications-harmonise-ids.md`.

### 8.5 Annotation location variation

- **Standard location:** RDF inside `<annotation>` alongside `celldesigner:extension`
- **Notes-embedded (included species):** RDF inside `<celldesigner:notes>` XHTML body — required because CellDesigner does not allow `<annotation>` on included species
- **Some files** (e.g. Coagulation pathway, Virus replication cycle) use notes-embedded RDF more extensively, even mixing free text and RDF in the same body element

---

## 9. Layout and alias system

### 9.1 Alias types overview

| Alias type | ID prefix | Located in | References |
|------------|-----------|-----------|------------|
| `compartmentAlias` | `ca` | `listOfCompartmentAliases` | `@compartment` → SBML compartment ID |
| `complexSpeciesAlias` | `csa` | `listOfComplexSpeciesAliases` | `@species` → SBML species ID, `@compartmentAlias` → compartment alias |
| `speciesAlias` | `sa` | `listOfSpeciesAliases` | `@species` → SBML species ID, either `@compartmentAlias` OR `@complexSpeciesAlias` |

### 9.2 Compartment alias

```xml
<celldesigner:compartmentAlias id="ca1" compartment="c1">
  <celldesigner:class>SQUARE</celldesigner:class>
  <celldesigner:bounds x="953.0" y="675.0" w="317.0" h="155.0"/>
  <celldesigner:namePoint x="1099.5" y="792.5"/>
  <celldesigner:doubleLine thickness="12.0" outerWidth="2.0" innerWidth="1.0"/>
  <celldesigner:paint color="ffcccc00" scheme="Color"/>
  <celldesigner:info state="empty" angle="-1.5707963267948966"/>
</celldesigner:compartmentAlias>
```

### 9.3 Complex species alias

```xml
<celldesigner:complexSpeciesAlias id="csa1" species="s86" compartmentAlias="ca5">
  <celldesigner:activity>inactive</celldesigner:activity>
  <celldesigner:bounds x="716.0" y="652.0" w="142.0" h="168.0"/>
  <celldesigner:font size="18"/>
  <celldesigner:view state="usual"/>
  <celldesigner:backupSize w="0.0" h="0.0"/>
  <celldesigner:backupView state="none"/>
  <celldesigner:usualView>
    <celldesigner:innerPosition x="660.0" y="444.0"/>
    <celldesigner:boxSize width="142.0" height="168.0"/>
    <celldesigner:singleLine width="2.0"/>
    <celldesigner:paint color="fff7f7f7" scheme="Color"/>
  </celldesigner:usualView>
  <celldesigner:briefView>
    <celldesigner:innerPosition x="0.0" y="0.0"/>
    <celldesigner:boxSize width="80.0" height="60.0"/>
    <celldesigner:singleLine width="2.0"/>
    <celldesigner:paint color="fff7f7f7" scheme="Color"/>
  </celldesigner:briefView>
  <celldesigner:info state="empty" angle="-1.5707963267948966"/>
</celldesigner:complexSpeciesAlias>
```

### 9.4 Species alias

Two variants depending on containment:

**Standalone (inside a compartment):**
```xml
<celldesigner:speciesAlias id="sa4" species="s5" compartmentAlias="ca5">
```

**Inside a complex:**
```xml
<celldesigner:speciesAlias id="sa1" species="s1" complexSpeciesAlias="csa1">
```

Both variants share the same child element structure (`activity`, `bounds`, `font`, `view`, `usualView`, `briefView`, `info`) but species aliases do NOT have `backupSize`/`backupView`.

### 9.5 Layout attributes reference

| Element | Attributes | Notes |
|---------|-----------|-------|
| `bounds` | `x`, `y`, `w`, `h` | **Absolute** canvas position and size in pixels |
| `innerPosition` | `x`, `y` | **Relative** offset from parent bounds origin (see 9.6) |
| `boxSize` | `width`, `height` | Glyph dimensions — must equal `bounds` `w`/`h` for the active view |
| `paint` | `color`, `scheme` | ARGB 8-hex-digit color; scheme always `"Color"` |
| `singleLine` | `width` | Border line width |
| `doubleLine` | `thickness`, `outerWidth`, `innerWidth` | Compartment double border |
| `font` | `size` | Label font size |
| `line` | `width`, `color`, `type` | Reaction line; type can be `"Straight"` |
| `info` | `state`, `angle` | State tag; angle in radians |
| `view` | `state` | `"usual"` or `"brief"` — which view is active |
| `activity` | — | `"inactive"` or `"active"` |

### 9.6 Coordinate system and the bounds / innerPosition relationship

**Critical for any parser or layout tool that modifies positions.**

Every alias carries two redundant representations of its position:

- **`bounds/@x, @y`** — absolute coordinates on the canvas (same coordinate space for all elements regardless of nesting)
- **`usualView/innerPosition/@x, @y`** — position relative to the *parent* alias's `bounds` origin

The relationship is:

```
bounds.x = parent.bounds.x + innerPosition.x
bounds.y = parent.bounds.y + innerPosition.y
```

For a `speciesAlias` inside a compartment, the parent is the `compartmentAlias`. For a `speciesAlias` or `complexSpeciesAlias` inside another complex, the parent is that `complexSpeciesAlias`. The `briefView/innerPosition` follows the same convention but for the collapsed view.

**`boxSize` must stay in sync with `bounds`:** `usualView/boxSize/@width` must equal `bounds/@w`, and `boxSize/@height` must equal `bounds/@h`. CellDesigner uses `boxSize` for rendering the glyph outline and `bounds` for hit-testing and reaction routing — if they diverge the element is drawn at a different size from where clicks register.

**Nesting is unbounded:** a `complexSpeciesAlias` can itself be a child of another `complexSpeciesAlias` to arbitrary depth. When modifying positions, all descendants must be translated together; moving a complex without moving its children leaves them with stale absolute `bounds` while the parent shifts.

**Parent resolution for `innerPosition`:**

| Alias type | Parent for `innerPosition` |
|------------|---------------------------|
| `speciesAlias` with `@compartmentAlias` | `compartmentAlias` with that id |
| `speciesAlias` with `@complexSpeciesAlias` | `complexSpeciesAlias` with that id |
| `complexSpeciesAlias` with `@compartmentAlias` | `compartmentAlias` with that id |
| `complexSpeciesAlias` with `@complexSpeciesAlias` | `complexSpeciesAlias` with that id |

### 9.7 Glyph outline (`singleLine`)

`usualView/singleLine/@width` and `briefView/singleLine/@width` control the border stroke width of a species glyph. This attribute is present on both `speciesAlias` and `complexSpeciesAlias`. Typical observed values are `1.0` (thin, default for most proteins) and `2.0` (thicker, used on complexes). Any layout tool that rewrites alias nodes should preserve or explicitly set this attribute — it is not derived from `bounds` or `boxSize`.

### 9.8 Complex label area

CellDesigner renders the complex name as a label **inside the bottom** of the complex bounding box. The default layout places children close to the bottom of the complex bounds, often leaving little or no space for the label text to be legible. When computing complex bounds from children programmatically, adding explicit padding at the bottom (e.g. 15px beyond the standard uniform padding) is necessary to ensure the label is visible.

### 9.9 Observed color conventions

| Color (ARGB hex) | Typical usage |
|-------------------|--------------|
| `ffccffcc` | Human proteins (light green) |
| `ffffcccc` | Viral proteins (light pink) |
| `ffcc99ff` | Phenotype entities (light purple) |
| `fff7f7f7` | Complex backgrounds (light gray) |
| `ffcccc00` | Some compartments (yellow) |
| `ff000000` | Reaction lines (black) |

---

## 10. Cross-reference chains for parsers

A parser must follow these reference chains to resolve the full data model:

1. **Species identity:** `speciesAlias/@species` → `listOfSpecies/species/@id` → `speciesIdentity/proteinReference` → `listOfProteins/protein/@id`
2. **Complex membership:** `listOfIncludedSpecies/species/complexSpecies` → `listOfSpecies/species/@id` (parent complex)
3. **Layout nesting:** `speciesAlias/@complexSpeciesAlias` → `complexSpeciesAlias/@id` → `complexSpeciesAlias/@compartmentAlias` → `compartmentAlias/@compartment` → SBML compartment
4. **Reaction participants:** `reaction/listOfReactants/speciesReference/@species` → species ID; `celldesigner:alias` → alias ID for layout
5. **Modification residues:** `species/modification/@residue` → `protein/modificationResidue/@id`
6. **Absolute position from nesting:** `alias/bounds` gives the absolute position directly; `usualView/innerPosition` gives position relative to the parent alias's `bounds` origin — both are always present and must be kept consistent (see 9.6)

---

## 11. File-to-file variation

- **ID naming conventions vary:** Some files use simple IDs (`s1`, `pr1`, `sa1`), others use compound IDs (`s_id_sa320`, `p_s_id_sa320`)
- **Annotation location varies:** Some files keep RDF strictly in `<annotation>` blocks; others embed RDF inside XHTML `<body>` in `<celldesigner:notes>` blocks
- **Canvas size varies significantly:** from 1800×1150 (small diagrams) to 6010×5412+ (large diagrams)
- **All files share:** SBML L2v4 namespace, CellDesigner namespace, modelVersion 4.0, identical structural hierarchy

---

## 12. Dataset statistics (22 diagrams)

| Metric | Value |
|--------|-------|
| Total files | 22 (21 submaps + 1 "Next steps") |
| Total size | ~18 MB (~450K lines) |
| Unique XML element types | ~130+ |
| Unique species classes | 12 |
| Unique compartment names | 63 |
| Unique MIRIAM URIs | ~5,134 across 36 databases |
| Reaction types | 17 |
| Most common elements | `rdf:li` (~19K), `paint` (~11.7K), `boxSize`/`innerPosition`/`singleLine` (~11.5K each) |