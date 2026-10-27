"""Operations on CellDesigner compartments."""

from __future__ import annotations

from lxml import etree

from .species import _encode_cd_tag_name
from .namespaces import CD, SBML
from .io import CDDiagram


def get_all_compartments(diagram: CDDiagram) -> list[etree._Element]:
    """Return all ``<compartment>`` elements from ``listOfCompartments``."""
    model = diagram.model
    comp_list = model.find(f"{{{SBML}}}listOfCompartments")
    if comp_list is None:
        return []
    return list(comp_list)


def get_compartment_name(compartment_node: etree._Element) -> str:
    """Return the display name of a compartment, falling back to ``@id``.

    The ``default`` compartment has no ``@name`` attribute.  This function
    returns the ``@id`` value in that case, consistent with the spec.
    """
    name = compartment_node.get("name")
    if name:
        return name
    return compartment_node.get("id", "")


def get_compartment_by_id(
    diagram: CDDiagram, compartment_id: str
) -> etree._Element | None:
    """Find a compartment by its SBML ``@id``."""
    for comp in get_all_compartments(diagram):
        if comp.get("id") == compartment_id:
            return comp
    return None


def rename_compartment(
    diagram: CDDiagram,
    compartment_node: etree._Element,
    new_name: str,
) -> None:
    """Rename a compartment, updating both the SBML attribute and the
    CellDesigner ``<celldesigner:name>`` tag in the compartment's annotation.

    Parameters
    ----------
    diagram:
        The owning diagram (marked dirty on success).
    compartment_node:
        The ``<compartment>`` element to rename.
    new_name:
        The new display name.
    """
    compartment_node.set("name", new_name)

    ann = compartment_node.find(f"{{{SBML}}}annotation")
    if ann is not None:
        ext = ann.find(f"{{{CD}}}extension")
        if ext is not None:
            cd_name_el = ext.find(f"{{{CD}}}name")
            if cd_name_el is not None:
                # The tag keeps the CellDesigner escapes; only the SBML @name is plain —
                # the same split `rename_species` makes, which this did not.
                cd_name_el.text = _encode_cd_tag_name(new_name)

    diagram.mark_dirty()


def get_compartment_hierarchy(diagram: CDDiagram) -> dict[str, str | None]:
    """Return the nesting hierarchy as ``{compartment_id: parent_id_or_None}``.

    Nesting is expressed via the SBML ``@outside`` attribute.  The root
    compartment(s) have no ``@outside`` and map to ``None``.
    """
    result: dict[str, str | None] = {}
    for comp in get_all_compartments(diagram):
        cid = comp.get("id", "")
        outside = comp.get("outside")  # None if not present
        result[cid] = outside
    return result
