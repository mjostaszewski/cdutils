"""Graphical property accessors and mutators for CellDesigner alias nodes.

Alias types
-----------
CellDesigner stores layout in *alias* nodes, which are separate from the
semantic species/reaction/compartment elements:

* ``<celldesigner:speciesAlias>`` — instances of top-level or included species
* ``<celldesigner:complexSpeciesAlias>`` — instances of COMPLEX species
* ``<celldesigner:compartmentAlias>`` — instances of compartments

All alias lists live inside ``model/annotation/celldesigner:extension``.

Colour encoding
---------------
Colours are stored as ARGB 8-hex-digit strings (e.g. ``"ffccffcc"``), in the
``paint/@color`` attribute of alias nodes.

Line width
----------
Stored in ``usualView/singleLine/@width`` **and** ``briefView/singleLine/@width``
— both must be kept in sync.

Bounds and innerPosition
------------------------
``bounds/@x,@y,@w,@h`` hold absolute canvas coordinates.  After changing
``bounds``, ``usualView/boxSize/@width,@height`` and
``usualView/innerPosition/@x,@y`` must be re-synchronised:

    innerPosition.x = bounds.x − parent.bounds.x
    innerPosition.y = bounds.y − parent.bounds.y

Parent resolution: ``@complexSpeciesAlias`` takes precedence over
``@compartmentAlias``.
"""

from __future__ import annotations

import logging
import re

from lxml import etree

from .namespaces import CD, SBML
from .io import CDDiagram

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alias node lookups
# ---------------------------------------------------------------------------

def _get_extension(diagram: CDDiagram) -> etree._Element | None:
    """Return ``model/annotation/celldesigner:extension``."""
    model = diagram.model
    ann = model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return None
    return ann.find(f"{{{CD}}}extension")


def get_aliases_for_species(
    diagram: CDDiagram, species_id: str
) -> list[etree._Element]:
    """Return all ``<speciesAlias>`` nodes that reference *species_id*.

    Also returns ``<complexSpeciesAlias>`` nodes when *species_id* matches a
    COMPLEX species.
    """
    ext = _get_extension(diagram)
    if ext is None:
        return []
    result = []
    for list_tag in (
        f"{{{CD}}}listOfSpeciesAliases",
        f"{{{CD}}}listOfComplexSpeciesAliases",
    ):
        alias_list = ext.find(list_tag)
        if alias_list is None:
            continue
        for alias in alias_list:
            if alias.get("species") == species_id:
                result.append(alias)
    return result


def get_all_species_aliases(diagram: CDDiagram) -> list[etree._Element]:
    """Return all ``<speciesAlias>`` nodes."""
    ext = _get_extension(diagram)
    if ext is None:
        return []
    alias_list = ext.find(f"{{{CD}}}listOfSpeciesAliases")
    if alias_list is None:
        return []
    return list(alias_list)


def get_all_complex_aliases(diagram: CDDiagram) -> list[etree._Element]:
    """Return all ``<complexSpeciesAlias>`` nodes."""
    ext = _get_extension(diagram)
    if ext is None:
        return []
    alias_list = ext.find(f"{{{CD}}}listOfComplexSpeciesAliases")
    if alias_list is None:
        return []
    return list(alias_list)


def get_all_compartment_aliases(diagram: CDDiagram) -> list[etree._Element]:
    """Return all ``<compartmentAlias>`` nodes."""
    ext = _get_extension(diagram)
    if ext is None:
        return []
    alias_list = ext.find(f"{{{CD}}}listOfCompartmentAliases")
    if alias_list is None:
        return []
    return list(alias_list)


def get_alias_by_id(diagram: CDDiagram, alias_id: str) -> etree._Element | None:
    """Find any alias node (species, complex, compartment) by its ``@id``."""
    ext = _get_extension(diagram)
    if ext is None:
        return None
    for list_tag in (
        f"{{{CD}}}listOfSpeciesAliases",
        f"{{{CD}}}listOfComplexSpeciesAliases",
        f"{{{CD}}}listOfCompartmentAliases",
    ):
        alias_list = ext.find(list_tag)
        if alias_list is None:
            continue
        for alias in alias_list:
            if alias.get("id") == alias_id:
                return alias
    return None


# ---------------------------------------------------------------------------
# Activity and view state
# ---------------------------------------------------------------------------

def get_activity(alias_node: etree._Element) -> str | None:
    """Return the activity state (``"inactive"`` or ``"active"``), or ``None``."""
    activity = alias_node.find(f"{{{CD}}}activity")
    return activity.text if activity is not None else None


def set_activity(
    diagram: "CDDiagram",
    alias_node: etree._Element,
    activity: str,
) -> None:
    """Set the activity flag on a species or complex alias.

    CellDesigner stores this per *alias*, not per species — the double border that marks a
    glyph "active" is a view property, so one species drawn twice can be active in one place
    and not the other. Callers that mean "this species is active" must therefore set it on
    every alias returned by `get_aliases_for_species`.

    Parameters
    ----------
    diagram:
        The owning diagram (marked dirty on success).
    alias_node:
        A ``<celldesigner:speciesAlias>`` or ``<celldesigner:complexSpeciesAlias>`` element.
    activity:
        ``"active"`` or ``"inactive"``. CellDesigner writes the element on every alias and
        defaults it to ``"inactive"``, so there is no "absent" state to restore; clearing an
        active glyph means setting ``"inactive"``.

    Raises
    ------
    ValueError
        If *activity* is not ``"active"`` or ``"inactive"``.
    """
    if activity not in ("active", "inactive"):
        raise ValueError(
            f"activity must be 'active' or 'inactive'; got {activity!r}"
        )
    el = alias_node.find(f"{{{CD}}}activity")
    if el is None:
        el = etree.SubElement(alias_node, f"{{{CD}}}activity")
    el.text = activity
    diagram.mark_dirty()


def get_view_state(alias_node: etree._Element) -> str | None:
    """Return the active view (``"usual"`` or ``"brief"``) from ``view/@state``."""
    view = alias_node.find(f"{{{CD}}}view")
    if view is None:
        return None
    return view.get("state")


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

_ARGB_RE = re.compile(r"^[0-9a-fA-F]{8}$")


def get_colour(alias_node: etree._Element) -> str | None:
    """Return the ARGB colour string from ``usualView/paint/@color``, or ``None``."""
    usual = alias_node.find(f"{{{CD}}}usualView")
    if usual is None:
        return None
    paint = usual.find(f"{{{CD}}}paint")
    if paint is None:
        return None
    return paint.get("color")


def set_colour(
    alias_node: etree._Element,
    colour: str,
    diagram: CDDiagram | None = None,
) -> None:
    """Set the alias colour.

    Parameters
    ----------
    alias_node:
        A species, complex, or compartment alias element.
    colour:
        ARGB 8-hex-digit string, e.g. ``"ffccffcc"``.
    diagram:
        If supplied, marked dirty on success.

    Raises
    ------
    ValueError
        If *colour* is not an 8-hex-digit ARGB string.
    """
    if not _ARGB_RE.match(colour):
        raise ValueError(
            f"Colour must be an 8-hex-digit ARGB string (e.g. 'ffccffcc'); got {colour!r}"
        )
    usual = alias_node.find(f"{{{CD}}}usualView")
    if usual is None:
        raise RuntimeError("Alias node has no <celldesigner:usualView> child")
    paint = usual.find(f"{{{CD}}}paint")
    if paint is None:
        raise RuntimeError("Alias node has no <celldesigner:usualView/paint> child")
    paint.set("color", colour)
    # Keep briefView in sync if present
    brief = alias_node.find(f"{{{CD}}}briefView")
    if brief is not None:
        brief_paint = brief.find(f"{{{CD}}}paint")
        if brief_paint is not None:
            brief_paint.set("color", colour)
    if diagram is not None:
        diagram.mark_dirty()


# ---------------------------------------------------------------------------
# Line width
# ---------------------------------------------------------------------------

def get_line_width(alias_node: etree._Element) -> float | None:
    """Return the outline stroke width from ``usualView/singleLine/@width``."""
    usual = alias_node.find(f"{{{CD}}}usualView")
    if usual is None:
        return None
    single = usual.find(f"{{{CD}}}singleLine")
    if single is None:
        return None
    w = single.get("width")
    return float(w) if w is not None else None


def set_line_width(
    alias_node: etree._Element,
    width: float,
    diagram: CDDiagram | None = None,
) -> None:
    """Set the outline stroke width in both ``usualView`` and ``briefView``.

    Parameters
    ----------
    alias_node:
        A species or complex alias element.
    width:
        Stroke width in pixels (e.g. ``1.0``, ``2.0``).
    diagram:
        If supplied, marked dirty on success.
    """
    width_str = str(float(width))
    for view_tag in (f"{{{CD}}}usualView", f"{{{CD}}}briefView"):
        view = alias_node.find(view_tag)
        if view is None:
            continue
        single = view.find(f"{{{CD}}}singleLine")
        if single is not None:
            single.set("width", width_str)
    if diagram is not None:
        diagram.mark_dirty()


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

def get_bounds(alias_node: etree._Element) -> tuple[float, float, float, float] | None:
    """Return ``(x, y, w, h)`` from the alias ``bounds`` element, or ``None``."""
    bounds = alias_node.find(f"{{{CD}}}bounds")
    if bounds is None:
        return None
    try:
        return (
            float(bounds.get("x", 0)),
            float(bounds.get("y", 0)),
            float(bounds.get("w", 0)),
            float(bounds.get("h", 0)),
        )
    except (TypeError, ValueError):
        return None


def get_parent_alias(
    diagram: CDDiagram, alias_node: etree._Element
) -> etree._Element | None:
    """Return the parent alias node, resolving ``@complexSpeciesAlias`` first,
    then ``@compartmentAlias``.

    Returns ``None`` for top-level aliases with no parent.
    """
    parent_id = alias_node.get("complexSpeciesAlias") or alias_node.get("compartmentAlias")
    if parent_id is None:
        return None
    return get_alias_by_id(diagram, parent_id)


def set_bounds(
    alias_node: etree._Element,
    x: float,
    y: float,
    w: float,
    h: float,
    diagram: CDDiagram | None = None,
) -> None:
    """Set the alias bounding box and synchronise dependent attributes.

    Updates:

    * ``bounds/@x,@y,@w,@h`` — absolute canvas position/size
    * ``usualView/boxSize/@width,@height`` — must equal ``w``, ``h``
    * ``usualView/innerPosition/@x,@y`` — relative to parent bounds origin
    * ``briefView/boxSize/@width,@height`` (if present)

    Parameters
    ----------
    alias_node:
        A species or complex alias element.
    x, y:
        New absolute canvas position (pixels).
    w, h:
        New size (pixels).
    diagram:
        If supplied, used to resolve the parent alias and marked dirty.

    Raises
    ------
    RuntimeError
        If ``bounds`` element is missing.
    """
    bounds = alias_node.find(f"{{{CD}}}bounds")
    if bounds is None:
        raise RuntimeError("Alias node has no <celldesigner:bounds> child")

    bounds.set("x", str(float(x)))
    bounds.set("y", str(float(y)))
    bounds.set("w", str(float(w)))
    bounds.set("h", str(float(h)))

    # Sync boxSize in usualView and briefView
    for view_tag in (f"{{{CD}}}usualView", f"{{{CD}}}briefView"):
        view = alias_node.find(view_tag)
        if view is None:
            continue
        box = view.find(f"{{{CD}}}boxSize")
        if box is not None:
            box.set("width", str(float(w)))
            box.set("height", str(float(h)))

    # Sync innerPosition relative to parent
    if diagram is not None:
        parent = get_parent_alias(diagram, alias_node)
        if parent is not None:
            parent_bounds = get_bounds(parent)
            if parent_bounds is not None:
                px, py, _, _ = parent_bounds
                rel_x = x - px
                rel_y = y - py
                usual = alias_node.find(f"{{{CD}}}usualView")
                if usual is not None:
                    inner = usual.find(f"{{{CD}}}innerPosition")
                    if inner is not None:
                        inner.set("x", str(float(rel_x)))
                        inner.set("y", str(float(rel_y)))

    if diagram is not None:
        diagram.mark_dirty()


# ---------------------------------------------------------------------------
# Compartment nesting (geometric)
# ---------------------------------------------------------------------------
#
# ``<compartmentAlias>`` nodes carry ``bounds`` but **no parent pointer**, so
# compartment-in-compartment nesting is recoverable only from box geometry.
# (A ``speciesAlias``/``complexSpeciesAlias`` *does* point at its immediate
# container via ``@compartmentAlias``/``@complexSpeciesAlias`` — resolved by
# :func:`get_parent_alias` — but that only gives the innermost compartment, not
# the chain above it.)  The SBML ``@outside`` chain is a *referential* parent
# chain that can diverge from the drawn geometry when a compartment has several
# aliases; where they disagree, the geometry is what the curator drew and what
# MINERVA renders.


def bounds_contain(
    outer: tuple[float, float, float, float],
    inner: tuple[float, float, float, float],
    *,
    tol: float = 1.0,
) -> bool:
    """Return ``True`` if box *outer* encloses box *inner*.

    Both are ``(x, y, w, h)`` tuples (as returned by :func:`get_bounds`).
    Containment is allowed to be loose by *tol* pixels on each edge, absorbing
    shared borders and float rounding.  A box does not contain one larger than
    itself, and (with the default positive *tol*) a box trivially contains an
    identical box — callers wanting strict enclosure should exclude the node
    itself, as :func:`get_enclosing_compartment_alias` does.
    """
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return (
        ix >= ox - tol
        and iy >= oy - tol
        and ix + iw <= ox + ow + tol
        and iy + ih <= oy + oh + tol
    )


def get_enclosing_compartment_alias(
    diagram: CDDiagram,
    alias_node: etree._Element,
    *,
    tol: float = 1.0,
) -> etree._Element | None:
    """Return the smallest ``<compartmentAlias>`` geometrically containing *alias_node*.

    Scans every compartment alias, keeps those whose bounds contain the node's
    bounds (excluding the node itself), and returns the **smallest-area** one —
    the immediate geometric parent compartment.  Returns ``None`` if the node has
    no bounds or nothing encloses it (a top-level/root compartment).
    """
    node_bounds = get_bounds(alias_node)
    if node_bounds is None:
        return None
    node_id = alias_node.get("id")

    best: etree._Element | None = None
    best_area = float("inf")
    for ca in get_all_compartment_aliases(diagram):
        if ca.get("id") == node_id:
            continue
        cb = get_bounds(ca)
        if cb is None:
            continue
        if not bounds_contain(cb, node_bounds, tol=tol):
            continue
        area = cb[2] * cb[3]
        if area < best_area:
            best, best_area = ca, area
    return best


def get_compartment_alias_chain(
    diagram: CDDiagram,
    alias_node: etree._Element,
    *,
    tol: float = 1.0,
) -> list[etree._Element]:
    """Return the compartment nesting chain of *alias_node*, innermost → outermost.

    Repeatedly applies :func:`get_enclosing_compartment_alias`, starting from the
    node's immediate geometric parent compartment and walking outward.  Each
    element is a ``<compartmentAlias>`` node.  Returns ``[]`` for a node sitting
    directly on the canvas.  A visited-set guards against pathological
    self-containment cycles.
    """
    chain: list[etree._Element] = []
    seen: set[str] = set()
    cur = get_enclosing_compartment_alias(diagram, alias_node, tol=tol)
    while cur is not None:
        cid = cur.get("id", "")
        if cid in seen:
            logger.warning("compartment-alias containment cycle at %s; truncating chain", cid)
            break
        seen.add(cid)
        chain.append(cur)
        cur = get_enclosing_compartment_alias(diagram, cur, tol=tol)
    return chain


def locate_species(
    diagram: CDDiagram,
    species_id: str,
    *,
    tol: float = 1.0,
) -> list[dict]:
    """Resolve where a species sits, one entry per on-canvas glyph.

    A species may be drawn several times (multiple ``speciesAlias`` glyphs) in
    different compartments, so this returns a **list**, one dict per alias:

    ``alias_id``
        The ``speciesAlias`` id for this glyph.
    ``geometry_alias_chain``
        ``compartmentAlias`` ids, innermost → outermost, from box geometry.
    ``geometry_chain``
        The SBML compartment ids those aliases instantiate (each alias's
        ``@compartment``), innermost → outermost — the **drawn** placement.
    ``outside_chain``
        The referential SBML ``@outside`` chain starting from the innermost
        compartment id — the **model's** placement.
    ``diverges``
        ``True`` when ``geometry_chain`` is **not a prefix of** ``outside_chain``
        — the drawn nesting departs from what ``@outside`` records (e.g. a
        staging/"to move" compartment the model doesn't reflect).  A trailing
        undrawn root (``default``) in ``outside_chain`` alone does **not** count
        as divergence, since geometry legitimately stops at the outermost drawn
        compartment.

    For an **included-species** glyph (one inside a complex), the innermost
    compartment is found by walking the referential complex-alias chain
    (:func:`get_parent_alias`) up to the enclosing ``compartmentAlias``, and the
    geometric walk continues from there for any compartment-in-compartment
    nesting above it.
    """
    outside = {
        c.get("id", ""): c.get("outside")
        for c in _iter_compartments(diagram)
    }

    results: list[dict] = []
    for sa in get_aliases_for_species(diagram, species_id):
        # Innermost compartment alias: prefer the referential container (walk up
        # through complex aliases), else fall back to pure geometry.
        inner_ca = _innermost_compartment_alias(diagram, sa)
        if inner_ca is None:
            alias_chain = get_compartment_alias_chain(diagram, sa, tol=tol)
        else:
            alias_chain = [inner_ca] + get_compartment_alias_chain(diagram, inner_ca, tol=tol)

        geometry_alias_chain = [ca.get("id", "") for ca in alias_chain]
        geometry_chain = [ca.get("compartment", "") for ca in alias_chain]

        # Referential @outside chain from the innermost compartment.
        outside_chain: list[str] = []
        if geometry_chain:
            seen: set[str] = set()
            cid = geometry_chain[0]
            while cid and cid not in seen:
                outside_chain.append(cid)
                seen.add(cid)
                cid = outside.get(cid)

        results.append({
            "alias_id": sa.get("id", ""),
            "geometry_alias_chain": geometry_alias_chain,
            "geometry_chain": geometry_chain,
            "outside_chain": outside_chain,
            # Agreement = geometry chain is a prefix of the @outside chain; the
            # latter may extend to an undrawn root (e.g. `default`). Divergence
            # = geometry draws a parent @outside skips, or a deeper nesting.
            "diverges": geometry_chain != outside_chain[: len(geometry_chain)],
        })
    return results


def _iter_compartments(diagram: CDDiagram) -> list[etree._Element]:
    """Return ``<compartment>`` elements from ``listOfCompartments`` (local helper)."""
    model = diagram.model
    lst = model.find(f"{{{SBML}}}listOfCompartments")
    if lst is None:
        return []
    return list(lst)


def _innermost_compartment_alias(
    diagram: CDDiagram, species_alias: etree._Element
) -> etree._Element | None:
    """Walk a species alias up its referential container chain to the enclosing
    ``compartmentAlias`` (through any number of complex aliases).  Returns
    ``None`` if the alias has no referential container (resolve by geometry)."""
    cur = get_parent_alias(diagram, species_alias)
    seen: set[str] = set()
    while cur is not None:
        cid = cur.get("id", "")
        if cid in seen:
            break
        seen.add(cid)
        if cur.tag == f"{{{CD}}}compartmentAlias":
            return cur
        cur = get_parent_alias(diagram, cur)
    return None
