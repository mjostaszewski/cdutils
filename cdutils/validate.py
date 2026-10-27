"""MINERVA Platform integrity check for CellDesigner SBML files.

The MINERVA API round-trips the XML through its own CellDesigner parser.
A 200 response with a non-empty body means the file is structurally valid.
Any other outcome (non-200, empty body, network error) means the file is
likely corrupt or malformed.

API reference: https://minerva-service.lcsb.uni.lu/minerva/docs/converter.html
Section: "1. Conversion to systems biology formats"

Equivalent curl call:
    curl 'https://minerva-service.lcsb.uni.lu/minerva/api/convert/CellDesigner_SBML:CellDesigner_SBML' \\
         -X POST --data-binary @file.xml -H 'Content-Type: text/plain'
"""

from __future__ import annotations

import os
import urllib.request
import urllib.error
from pathlib import Path

from lxml import etree

_MINERVA_URL = (
    "https://minerva-service.lcsb.uni.lu/minerva/api/convert/"
    "CellDesigner_SBML:CellDesigner_SBML"
)
_DEFAULT_TIMEOUT = 60

# The convert endpoint and request timeout may be overridden per environment —
# e.g. to point at a faster local MINERVA instance — without editing this file.
# The defaults above reproduce the original behaviour (public LCSB service).
#   MINERVA_CONVERT_URL      full convert URL (…/api/convert/CellDesigner_SBML:CellDesigner_SBML)
#   MINERVA_CONVERT_TIMEOUT  socket timeout in seconds
# Read at call time so an override set after import still takes effect.


def _convert_url() -> str:
    return os.environ.get("MINERVA_CONVERT_URL", _MINERVA_URL)


def _convert_timeout() -> float:
    raw = os.environ.get("MINERVA_CONVERT_TIMEOUT")
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT


class ValidationError(Exception):
    """Raised when the MINERVA integrity check fails."""


def validate_xml_bytes(xml_bytes: bytes, label: str = "<in-memory>") -> None:
    """POST *xml_bytes* to the MINERVA converter API and assert a valid response.

    Parameters
    ----------
    xml_bytes:
        Raw XML content to validate.
    label:
        Human-readable name used in error messages (e.g. a file path).

    Raises
    ------
    ValidationError
        If the API returns a non-200 status, an empty body, or if a network
        error occurs.
    """
    req = urllib.request.Request(
        _convert_url(),
        data=xml_bytes,
        method="POST",
        headers={"Content-Type": "text/plain"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_convert_timeout()) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise ValidationError(
            f"MINERVA validation failed for {label!r}: "
            f"HTTP {exc.code} {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ValidationError(
            f"MINERVA validation failed for {label!r}: "
            f"Network error — {exc.reason}"
        ) from exc

    if status != 200:
        raise ValidationError(
            f"MINERVA validation failed for {label!r}: HTTP {status}"
        )
    if not body or len(body) == 0:
        raise ValidationError(
            f"MINERVA validation returned an empty body for {label!r}; "
            "file is likely corrupt."
        )


def validate_diagram(diagram, label: str | None = None) -> None:
    """Validate a :class:`~cdutils.io.CDDiagram` via the MINERVA API.

    Serialises the in-memory lxml tree to bytes and POSTs it.

    Parameters
    ----------
    diagram:
        A :class:`~cdutils.io.CDDiagram` instance.
    label:
        Optional display name for error messages. Defaults to
        ``diagram.path`` if available.

    Raises
    ------
    ValidationError
        If the integrity check fails.
    """
    if label is None:
        label = str(diagram.path) if diagram.path is not None else "<in-memory>"

    xml_bytes = etree.tostring(
        diagram.tree.getroot(),
        xml_declaration=True,
        encoding="UTF-8",
    )
    validate_xml_bytes(xml_bytes, label=label)


def validate_file(path: str | Path) -> None:
    """Validate a CellDesigner XML file on disk via the MINERVA API.

    Parameters
    ----------
    path:
        Path to the ``.xml`` file to check.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValidationError
        If the integrity check fails.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    xml_bytes = path.read_bytes()
    validate_xml_bytes(xml_bytes, label=str(path))
