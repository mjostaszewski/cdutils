"""Read and write RDF/MIRIAM annotations on CellDesigner diagram components.

Annotation locations
--------------------
* **Top-level species, reactions, compartments**: RDF block lives inside
  ``<annotation>/<rdf:RDF>`` alongside the ``<celldesigner:extension>`` element.
* **Included species** (complex subunits): CellDesigner forbids SBML-level
  ``<annotation>`` on included species. Their RDF is embedded as an actual
  child element of the ``<body>`` inside ``<celldesigner:notes>``.

Both locations are handled transparently by :func:`get_annotations` and
:func:`set_annotations`.

MIRIAM URI encoding
-------------------
All identifiers use ``urn:miriam:{namespace}:{id}``. Some namespaces contain
a colon in the identifier (e.g. ``obo.pr:PR:000050270``) which must be
URL-encoded as ``%3A`` in the stored URI:
``urn:miriam:obo.pr:PR%3A000050270``.

Qualifier correction
--------------------
The map uses qualifiers inconsistently. When ``correct_qualifiers=True``,
:func:`set_annotations` routes each identifier to the qualifier the annotation model
expects — see :data:`cdutils.namespaces.ANNOTATION_MODEL`, transcribed from
``curation-ops.md`` § "Annotation and qualifier model".

The correct qualifier depends on the **element class**, not on the namespace alone:
``obo.go`` is identity on a phenotype but context under ``isPartOf`` on a reaction, and
``mesh`` is identity on an entity but evidence context under ``occursIn`` on a reaction. The
class is derived from the element being written, so a reaction's ``occursIn taxonomy`` is no
longer rewritten as ``isPartOf``.

Nothing is changed when the current qualifier is already valid for that element class, when
the namespace is outside the model, or when two equally specific qualifiers would accept it
(``interpro`` on a protein is valid under both ``is`` and ``isPartOf``) — an ambiguous case
is a curation decision, not something to guess at.
"""

from __future__ import annotations

import copy
import logging
import re
from urllib.parse import quote, unquote

from lxml import etree

from .namespaces import (
    BQBIOL,
    BQMODEL,
    CD,
    DCTERMS,
    IDENTITY_NAMESPACES,
    LITERATURE_NAMESPACES,
    NS,
    RDF,
    RDF_NSMAP,
    SBML,
    TAXONOMY_NAMESPACES,
    XHTML,
    expected_qualifier,
    is_expected,
    specificity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MIRIAM URI helpers
# ---------------------------------------------------------------------------

_MIRIAM_PREFIX = "urn:miriam:"


def parse_miriam_uri(uri: str) -> tuple[str, str]:
    """Split a MIRIAM URI into ``(namespace, identifier)``.

    URL-encoded characters in the identifier are decoded:
    ``urn:miriam:obo.pr:PR%3A000050270`` → ``("obo.pr", "PR:000050270")``.

    Raises
    ------
    ValueError
        If ``uri`` does not start with ``urn:miriam:`` or has fewer than two
        colon-separated parts after the prefix.
    """
    if not uri.startswith(_MIRIAM_PREFIX):
        raise ValueError(f"Not a MIRIAM URI: {uri!r}")
    rest = uri[len(_MIRIAM_PREFIX):]
    # rest is "namespace:identifier" — split on first colon only
    parts = rest.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"MIRIAM URI missing identifier part: {uri!r}")
    namespace, identifier = parts
    return namespace, unquote(identifier)


def make_miriam_uri(namespace: str, identifier: str) -> str:
    """Build a MIRIAM URI, URL-encoding any colons inside the identifier.

    ``("obo.pr", "PR:000050270")`` → ``urn:miriam:obo.pr:PR%3A000050270``
    """
    encoded_id = quote(identifier, safe="")
    return f"{_MIRIAM_PREFIX}{namespace}:{encoded_id}"


# ---------------------------------------------------------------------------
# Qualifier correction
# ---------------------------------------------------------------------------

def _element_class(element: etree._Element) -> str | None:
    """Classify *element* for the annotation model: a species class, ``"REACTION"``,
    ``"COMPARTMENT"``, or ``None`` when it cannot be determined."""
    if element is None:
        return None
    tag = etree.QName(element)
    if tag.localname == "reaction":
        return "REACTION"
    if tag.localname == "compartment":
        return "COMPARTMENT"
    if tag.localname == "species":
        # local import: species.py imports from this module
        from .namespaces import model_class
        try:
            return model_class(element)
        except Exception:
            return None
    return None


def _correct_qualifier(
    qualifier_localname: str,
    namespace: str,
    element_class: str | None = None,
) -> str | None:
    """Return the qualifier *namespace* should sit under, or ``None`` for no change.

    ``None`` is returned when the current qualifier is already valid for this element class,
    when the model does not know the namespace, or when the choice is ambiguous (see
    :func:`cdutils.namespaces.expected_qualifier`) — an ambiguous case is a curation decision
    and is deliberately left alone.

    *element_class* comes from :func:`_element_class`. Without it the check falls back to the
    union over all classes, which can only catch a plainly invalid qualifier.
    """
    # Strip bqbiol: / bqmodel: prefix to compare localnames
    local = (qualifier_localname.split(":")[-1] if ":" in qualifier_localname
             else qualifier_localname)

    correct = expected_qualifier(namespace, element_class)
    if correct is None or correct == local:
        return None

    # The current qualifier may be *accepted* yet less specific than the right one: a
    # hypothetical protein inherits `isPartOf interpro` from PROTEIN, but its own class puts
    # interpro under `is`. Only leave it alone when nothing more specific applies.
    if specificity(local, namespace, element_class) >= specificity(
            correct, namespace, element_class):
        return None
    return correct


# ---------------------------------------------------------------------------
# Locating RDF blocks
# ---------------------------------------------------------------------------

def _is_included_species(element: etree._Element) -> bool:
    """Return True if *element* is a ``<celldesigner:species>`` (included species)."""
    return etree.QName(element).localname == "species" and \
           etree.QName(element).namespace == CD


def _find_rdf_in_annotation(element: etree._Element) -> etree._Element | None:
    """Return the ``<rdf:RDF>`` child of the SBML ``<annotation>`` block, or None."""
    ann = element.find(f"{{{SBML}}}annotation")
    if ann is None:
        return None
    return ann.find(f"{{{RDF}}}RDF")


def _find_rdf_in_notes(element: etree._Element) -> etree._Element | None:
    """Return the ``<rdf:RDF>`` embedded in ``<celldesigner:notes>/<html>/<body>``."""
    notes = element.find(f"{{{CD}}}notes")
    if notes is None:
        return None
    # Walk html/body — namespace may be XHTML or absent
    for html in notes:
        for body in html:
            rdf = body.find(f"{{{RDF}}}RDF")
            if rdf is not None:
                return rdf
    return None


def _locate_rdf(element: etree._Element) -> tuple[etree._Element | None, str]:
    """Find the RDF block for *element* and report its location.

    Returns
    -------
    (rdf_element_or_None, location)
        *location* is ``"annotation"`` or ``"notes"``.
    """
    if _is_included_species(element):
        return _find_rdf_in_notes(element), "notes"
    rdf = _find_rdf_in_annotation(element)
    if rdf is not None:
        return rdf, "annotation"
    # Fall back: check notes even for top-level elements (rare but exists)
    rdf = _find_rdf_in_notes(element)
    return rdf, "notes"


def is_included_species(element: etree._Element) -> bool:
    """True if *element* is an included species (a ``<celldesigner:species>`` complex member).

    Included species cannot carry an SBML ``<annotation>``; their RDF is written into
    ``<celldesigner:notes>`` instead. Reading and writing handle that automatically, so this
    is only needed when the *placement itself* matters.
    """
    return _is_included_species(element)


def get_annotation_location(element: etree._Element) -> str | None:
    """Where *element*'s RDF actually sits: ``"annotation"``, ``"notes"``, or ``None``.

    ``None`` means the element carries no RDF block at all. Use this rather than
    :func:`get_notes_text`, which strips RDF out of the notes text and so always reports
    nothing for a notes-RDF element — it is not a placement detector.
    """
    rdf, location = _locate_rdf(element)
    return location if rdf is not None else None


# ---------------------------------------------------------------------------
# Reading annotations
# ---------------------------------------------------------------------------

def get_annotations(element: etree._Element) -> dict[str, list[str]]:
    """Return all RDF annotations on *element* as ``{qualifier: [miriam_uri, ...]}``.

    The qualifier keys are ``bqbiol:*`` or ``bqmodel:*`` local names with
    their prefix (e.g. ``"isDescribedBy"``, ``"is"``, ``"isPartOf"``).

    Checks both ``<annotation>`` and ``<celldesigner:notes>`` so included
    species are handled transparently.

    Returns an empty dict if no RDF block is present.
    """
    rdf, _ = _locate_rdf(element)
    if rdf is None:
        return {}

    result: dict[str, list[str]] = {}
    # Each qualifier is a direct child of rdf:Description
    desc = rdf.find(f"{{{RDF}}}Description")
    if desc is None:
        return {}

    for child in desc:
        tag = etree.QName(child)
        if tag.namespace not in (BQBIOL, BQMODEL):
            continue
        qualifier = tag.localname
        for bag in child.findall(f"{{{RDF}}}Bag"):
            lis = bag.findall(f"{{{RDF}}}li")
            if len(lis) > 1:
                logger.warning(
                    "Grouped annotations found: qualifier %s has %d URIs in one Bag",
                    qualifier,
                    len(lis),
                )
            for li in lis:
                resource = li.get(f"{{{RDF}}}resource")
                if resource:
                    result.setdefault(qualifier, []).append(resource)

    return result


# ---------------------------------------------------------------------------
# Writing annotations
# ---------------------------------------------------------------------------

def _build_rdf_block(
    about: str,
    annotations: dict[str, list[str]],
    correct_qualifiers: bool,
    element_class: str | None = None,
) -> etree._Element:
    """Build a new ``<rdf:RDF>`` element from *annotations*.

    Parameters
    ----------
    about:
        The ``rdf:about`` value (typically ``"#{metaid}"``).
    annotations:
        ``{qualifier_localname: [miriam_uri, ...]}``. The qualifier may be
        given with or without a ``bqbiol:``/``bqmodel:`` prefix.
    correct_qualifiers:
        If ``True``, remap qualifiers to semantically correct values per
        the map's annotation conventions.
    element_class:
        Element class the annotations belong to (see :func:`_element_class`). The correct
        qualifier depends on it, so without it only plainly invalid qualifiers are corrected.
    """
    rdf_el = etree.Element(f"{{{RDF}}}RDF", nsmap=RDF_NSMAP)
    desc = etree.SubElement(rdf_el, f"{{{RDF}}}Description")
    desc.set(f"{{{RDF}}}about", about)

    for qualifier, uris in annotations.items():
        base_local = qualifier.split(":")[-1] if ":" in qualifier else qualifier
        base_ns = BQMODEL if qualifier.startswith("bqmodel:") else BQBIOL

        for uri in uris:
            uri_local = base_local
            uri_ns = base_ns

            if correct_qualifiers:
                try:
                    ns, _ = parse_miriam_uri(uri)
                    correction = _correct_qualifier(uri_local, ns, element_class)
                    if correction is not None:
                        logger.warning(
                            "Qualifier corrected: %s:%s → bqbiol:%s for URI %s",
                            "bqbiol" if uri_ns == BQBIOL else "bqmodel",
                            uri_local,
                            correction,
                            uri,
                        )
                        uri_local = correction
                        uri_ns = BQBIOL
                except ValueError:
                    pass

            qual_el = etree.SubElement(desc, f"{{{uri_ns}}}{uri_local}")
            bag = etree.SubElement(qual_el, f"{{{RDF}}}Bag")
            li = etree.SubElement(bag, f"{{{RDF}}}li")
            li.set(f"{{{RDF}}}resource", uri)

    return rdf_el


def _get_or_create_annotation(element: etree._Element) -> etree._Element:
    """Return the SBML ``<annotation>`` child of *element*, creating it if absent."""
    ann = element.find(f"{{{SBML}}}annotation")
    if ann is None:
        ann = etree.SubElement(element, f"{{{SBML}}}annotation")
    return ann


def _get_notes_body(element: etree._Element) -> etree._Element | None:
    """Return the ``<body>`` element inside ``<celldesigner:notes>/<html>``."""
    notes = element.find(f"{{{CD}}}notes")
    if notes is None:
        return None
    for html in notes:
        for body in html:
            if etree.QName(body).localname == "body":
                return body
    return None


def set_annotations(
    element: etree._Element,
    annotations: dict[str, list[str]],
    correct_qualifiers: bool = True,
    diagram=None,
) -> None:
    """Replace all RDF annotations on *element* with *annotations*.

    The existing RDF block (in whichever location it lives) is removed and
    rebuilt from *annotations*.  If *annotations* is empty, the existing RDF
    block is removed and nothing is written.

    Parameters
    ----------
    element:
        A species, reaction, or compartment lxml element.
    annotations:
        ``{qualifier: [miriam_uri, ...]}``.  Qualifier may be a bare local
        name (``"is"``) or prefixed (``"bqbiol:is"``).
    correct_qualifiers:
        Remap qualifiers to semantically correct values and emit warnings.
    diagram:
        If supplied (a :class:`~cdutils.io.CDDiagram`), marks it dirty after
        a successful write.

    Raises
    ------
    RuntimeError
        If the element cannot be written to (e.g. no suitable parent node).
    """
    # Determine metaid for rdf:about
    metaid = element.get("metaid") or element.get("id") or ""
    about = f"#{metaid}" if metaid else ""

    # Save a snapshot of the element for rollback on failure
    snapshot = copy.deepcopy(element)

    try:
        _do_set_annotations(element, annotations, about, correct_qualifiers)
    except Exception as exc:
        # Restore element to its pre-modification state
        element[:] = snapshot[:]
        for attr, val in snapshot.attrib.items():
            element.set(attr, val)
        raise RuntimeError(
            f"set_annotations failed and was rolled back: {exc}"
        ) from exc

    if diagram is not None:
        diagram.mark_dirty()


def _do_set_annotations(
    element: etree._Element,
    annotations: dict[str, list[str]],
    about: str,
    correct_qualifiers: bool,
) -> None:
    """Internal: perform the actual annotation write without rollback logic."""
    if _is_included_species(element):
        _write_to_notes(element, annotations, about, correct_qualifiers)
    else:
        _write_to_annotation(element, annotations, about, correct_qualifiers)


def _write_to_annotation(
    element: etree._Element,
    annotations: dict[str, list[str]],
    about: str,
    correct_qualifiers: bool,
) -> None:
    """Write RDF into SBML-level ``<annotation>``."""
    ann = _get_or_create_annotation(element)
    # Remove old RDF block if present
    old_rdf = ann.find(f"{{{RDF}}}RDF")
    if old_rdf is not None:
        ann.remove(old_rdf)
    if annotations:
        new_rdf = _build_rdf_block(about, annotations, correct_qualifiers,
                                   _element_class(element))
        ann.append(new_rdf)


def _get_or_create_notes_body(element: etree._Element) -> etree._Element:
    """Return the ``<body>`` inside ``<celldesigner:notes>/<html>``, creating the
    full structure if any part is missing. A new ``<celldesigner:notes>`` goes first,
    ahead of ``<celldesigner:annotation>``, where CellDesigner writes it."""
    notes = element.find(f"{{{CD}}}notes")
    if notes is None:
        notes = etree.Element(f"{{{CD}}}notes")
        element.insert(0, notes)

    html = None
    for child in notes:
        if etree.QName(child).localname == "html":
            html = child
            break
    if html is None:
        html = etree.SubElement(notes, f"{{{XHTML}}}html")

    for child in html:
        if etree.QName(child).localname == "body":
            return child
    return etree.SubElement(html, f"{{{XHTML}}}body")


def _write_to_notes(
    element: etree._Element,
    annotations: dict[str, list[str]],
    about: str,
    correct_qualifiers: bool,
) -> None:
    """Write RDF into ``<celldesigner:notes>/<html>/<body>`` for included species,
    creating the notes structure if it does not exist."""
    body = _get_or_create_notes_body(element)
    # Remove existing RDF child
    old_rdf = body.find(f"{{{RDF}}}RDF")
    if old_rdf is not None:
        body.remove(old_rdf)
    if annotations:
        new_rdf = _build_rdf_block(about, annotations, correct_qualifiers,
                                   _element_class(element))
        body.append(new_rdf)


# ---------------------------------------------------------------------------
# Notes text access
# ---------------------------------------------------------------------------

def get_notes_text(element: etree._Element) -> str:
    """Return plain text from notes, excluding any embedded ``<rdf:RDF>`` block.

    For included species (``<celldesigner:species>``): reads text nodes from
    ``<celldesigner:notes>/<html>/<body>``, skipping the ``<rdf:RDF>`` child
    but collecting all other text content.

    For top-level elements: reads all text from the SBML ``<notes>`` child.

    Returns an empty string if no notes element is present or if the notes
    contain no text outside the RDF block.
    """
    if _is_included_species(element):
        body = _get_notes_body(element)
        if body is None:
            return ""
        parts: list[str] = []
        if body.text:
            parts.append(body.text)
        for child in body:
            if etree.QName(child).namespace == RDF:
                # Skip RDF content; include trailing text (tail) if any
                if child.tail:
                    parts.append(child.tail)
            else:
                # Include all text from non-RDF elements (itertext excludes tail)
                parts.extend(child.itertext())
                if child.tail:
                    parts.append(child.tail)
        return "".join(parts).strip()
    else:
        notes = element.find(f"{{{SBML}}}notes")
        if notes is None:
            return ""
        return "".join(notes.itertext()).strip()


def _get_or_create_sbml_notes_body(element: etree._Element) -> etree._Element:
    """Return the ``<body>`` inside SBML ``<notes>/<html>`` of a top-level element, creating
    whatever is missing in the layout CellDesigner writes (``<head><title/></head>``).

    SBML requires ``<notes>`` to precede ``<annotation>``, so a new one is the first child.
    """
    notes = element.find(f"{{{SBML}}}notes")
    if notes is None:
        notes = etree.Element(f"{{{SBML}}}notes")
        element.insert(0, notes)

    html = next((c for c in notes
                 if isinstance(c.tag, str) and etree.QName(c).localname == "html"), None)
    if html is None:
        html = etree.SubElement(notes, f"{{{XHTML}}}html", nsmap={None: XHTML})
        head = etree.SubElement(html, f"{{{XHTML}}}head")
        etree.SubElement(head, f"{{{XHTML}}}title")

    body = next((c for c in html
                 if isinstance(c.tag, str) and etree.QName(c).localname == "body"), None)
    if body is None:
        body = etree.SubElement(html, f"{{{XHTML}}}body")
    return body


def set_notes_text(
    element: etree._Element,
    text: str,
    diagram=None,
) -> None:
    """Replace the plain-text notes of *element* with *text*, keeping any embedded RDF.

    The writer half of :func:`get_notes_text`: afterwards ``get_notes_text(element)`` returns
    ``text.strip()``.

    * **Top-level species, reactions, compartments**: writes ``<notes>/<html>/<body>``,
      creating it (as the first child, where SBML requires it) when absent.
    * **Included species**: writes ``<celldesigner:notes>/<html>/<body>``. Their RDF lives in
      that same body; it is kept in place, so annotations survive the write.

    Everything else in the body — the previous text and any markup such as ``<p>`` or
    ``<br/>`` — is replaced. Newlines are stored as-is, which is how CellDesigner keeps
    multi-line notes; ``<`` and ``&`` in *text* are escaped, not interpreted as markup.

    An empty *text* clears the notes. A top-level element left with no RDF in its notes
    loses the ``<notes>`` element entirely.

    Parameters
    ----------
    element:
        A species, reaction, or compartment lxml element.
    text:
        The new notes text.
    diagram:
        If supplied (a :class:`~cdutils.io.CDDiagram`), marks it dirty after a successful
        write.

    Raises
    ------
    TypeError
        If *text* is not a string.
    ValueError
        If *text* holds characters XML 1.0 cannot represent (NUL, most control
        characters). Raised before anything is touched.
    RuntimeError
        If the write fails part-way; *element* is rolled back.
    """
    if not isinstance(text, str):
        raise TypeError(f"Notes text must be a string, not {type(text).__name__}")
    # lxml rejects XML-incompatible strings on assignment; probe a scratch element so a bad
    # string fails before the real element is modified.
    etree.Element("probe").text = text

    snapshot = copy.deepcopy(element)
    try:
        _do_set_notes_text(element, text)
    except Exception as exc:
        element[:] = snapshot[:]
        for attr, val in snapshot.attrib.items():
            element.set(attr, val)
        raise RuntimeError(f"set_notes_text failed and was rolled back: {exc}") from exc

    if diagram is not None:
        diagram.mark_dirty()


def _do_set_notes_text(element: etree._Element, text: str) -> None:
    """Internal: perform the notes write without rollback logic."""
    included = _is_included_species(element)
    if included:
        body = _get_or_create_notes_body(element)
    elif not text and element.find(f"{{{SBML}}}notes") is None:
        return  # nothing to clear
    else:
        body = _get_or_create_sbml_notes_body(element)

    rdf_blocks = [c for c in body
                  if isinstance(c.tag, str) and etree.QName(c).namespace == RDF]
    for child in list(body):
        body.remove(child)
    body.text = text or None
    for rdf in rdf_blocks:
        # a tail would be read back by get_notes_text as part of the text
        rdf.tail = None
        body.append(rdf)

    if not included and not text and not rdf_blocks:
        element.remove(element.find(f"{{{SBML}}}notes"))


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def add_annotation(
    element: etree._Element,
    qualifier: str,
    namespace: str,
    identifier: str,
    diagram=None,
) -> None:
    """Add a single identifier without replacing existing annotations.

    Parameters
    ----------
    element:
        Target element.
    qualifier:
        Qualifier local name, e.g. ``"is"`` or ``"bqbiol:isDescribedBy"``.
    namespace:
        MIRIAM namespace, e.g. ``"uniprot"``.
    identifier:
        Identifier value, e.g. ``"P0DTC2"``.
    diagram:
        If supplied, marks it dirty.
    """
    current = get_annotations(element)
    uri = make_miriam_uri(namespace, identifier)
    local = qualifier.split(":")[-1] if ":" in qualifier else qualifier
    uris = current.setdefault(local, [])
    if uri not in uris:
        uris.append(uri)
    set_annotations(element, current, correct_qualifiers=False, diagram=diagram)


def remove_annotation(
    element: etree._Element,
    namespace: str,
    identifier: str | None = None,
    diagram=None,
) -> None:
    """Remove annotations by namespace, optionally filtered by identifier.

    Parameters
    ----------
    element:
        Target element.
    namespace:
        MIRIAM namespace to remove, e.g. ``"hgnc.symbol"``.
    identifier:
        If given, remove only the URI for this specific identifier.
        If ``None``, remove all URIs in *namespace*.
    diagram:
        If supplied, marks it dirty.
    """
    current = get_annotations(element)
    if not current:
        return

    changed = False
    for qualifier, uris in list(current.items()):
        filtered = []
        for uri in uris:
            try:
                ns, ident = parse_miriam_uri(uri)
            except ValueError:
                filtered.append(uri)
                continue
            if ns == namespace and (identifier is None or ident == identifier):
                changed = True
            else:
                filtered.append(uri)
        if filtered:
            current[qualifier] = filtered
        else:
            del current[qualifier]

    if changed:
        set_annotations(element, current, correct_qualifiers=False, diagram=diagram)
