"""Load and save CellDesigner SBML XML files with formatting preservation."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from .namespaces import SBML, CD


class CDDiagram:
    """Thin wrapper around an lxml tree with dirty tracking and path storage."""

    def __init__(self, tree: etree._ElementTree, path: Path | None = None):
        self.tree = tree
        self.path = Path(path) if path is not None else None
        self._dirty = False

    @property
    def root(self) -> etree._Element:
        return self.tree.getroot()

    @property
    def model(self) -> etree._Element:
        return self.root.find(f"{{{SBML}}}model")

    def mark_dirty(self) -> None:
        self._dirty = True

    @property
    def is_dirty(self) -> bool:
        return self._dirty


def load_diagram(path: str | Path) -> CDDiagram:
    """Parse a CellDesigner XML file, preserving all whitespace and formatting.

    Parameters
    ----------
    path:
        Path to the CellDesigner ``.xml`` file.

    Returns
    -------
    CDDiagram
        Wrapper around the parsed lxml tree. ``is_dirty`` is ``False``.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    etree.XMLSyntaxError
        If the file is not valid XML.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Diagram file not found: {path}")
    # parse() without remove_blank_text keeps all whitespace text nodes intact
    tree = etree.parse(str(path))
    return CDDiagram(tree, path)


def get_canvas_size(diagram: CDDiagram) -> tuple[float, float] | None:
    """Return the canvas dimensions ``(width, height)`` from ``modelDisplay``.

    Reads ``@sizeX`` and ``@sizeY`` from
    ``model/annotation/celldesigner:extension/celldesigner:modelDisplay``.

    Returns ``None`` if the element is absent or attributes cannot be parsed.
    """
    model = diagram.model
    ann = model.find(f"{{{SBML}}}annotation")
    if ann is None:
        return None
    ext = ann.find(f"{{{CD}}}extension")
    if ext is None:
        return None
    display = ext.find(f"{{{CD}}}modelDisplay")
    if display is None:
        return None
    try:
        return float(display.get("sizeX", 0)), float(display.get("sizeY", 0))
    except (TypeError, ValueError):
        return None


def save_diagram(
    diagram: CDDiagram,
    path: str | Path | None = None,
    validate: bool = False,
) -> bool:
    """Write the diagram back to disk, but only if it has been modified.

    Parameters
    ----------
    diagram:
        The diagram to save.
    path:
        Destination path. Defaults to the path the diagram was loaded from.
    validate:
        If ``True``, call the MINERVA Platform integrity check before writing.
        The file is **not** written if validation fails.  Requires a network
        connection to ``minerva-service.lcsb.uni.lu``.

    Returns
    -------
    bool
        ``True`` if the file was written, ``False`` if skipped (not dirty).

    Raises
    ------
    ValueError
        If no path is available (diagram was not loaded from a file and no
        ``path`` argument was provided).
    ValidationError
        If ``validate=True`` and the MINERVA integrity check fails.  The file
        is not written in this case.
    """
    if not diagram.is_dirty:
        return False

    out_path = Path(path) if path is not None else diagram.path
    if out_path is None:
        raise ValueError(
            "No output path: provide a path argument or load the diagram from a file."
        )

    if validate:
        # Import here to avoid circular import and keep network dependency optional
        from .validate import validate_diagram
        validate_diagram(diagram, label=str(out_path))

    diagram.tree.write(
        str(out_path),
        xml_declaration=True,
        encoding="UTF-8",
    )
    diagram._dirty = False
    return True
