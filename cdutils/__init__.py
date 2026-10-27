"""cdutils — Python utilities for reading and editing CellDesigner SBML XML.

Quick start
-----------
>>> from cdutils import load_diagram, save_diagram
>>> from cdutils import get_all_species, get_annotations, set_annotations
>>>
>>> d = load_diagram("Viral_replication.xml")
>>> species = get_all_species(d)
>>> anns = get_annotations(species[0])
>>> set_annotations(species[0], {"is": ["urn:miriam:uniprot:P0DTC2"]}, diagram=d)
>>> save_diagram(d)

Modules
-------
io          — load_diagram, save_diagram, CDDiagram
annotations — get/set/add/remove annotations; get/set notes text; parse_miriam_uri, make_miriam_uri
species     — get_all_species, get_included_species, rename_species, remove_species, …
reactions   — get_all_reactions, get_reaction_type, change_reaction_type, add/remove_reaction,
              replace_reaction_species, get_connected_components, …
compartments— get_all_compartments, get_compartment_hierarchy
query       — find_by_name, find_by_class, find_by_annotation, …
layout      — get/set colour, line width, bounds; get_aliases_for_species
namespaces  — XML namespace URI constants and qualifier classification sets
"""

# I/O
from .io import CDDiagram, load_diagram, save_diagram, get_canvas_size

# Validation
from .validate import ValidationError, validate_diagram, validate_file, validate_xml_bytes

# Annotations
from .annotations import (
    add_annotation,
    get_annotations,
    get_annotation_location,
    is_included_species,
    get_notes_text,
    set_notes_text,
    make_miriam_uri,
    parse_miriam_uri,
    remove_annotation,
    set_annotations,
)

# Species
from .species import (
    change_protein_type,
    decode_cd_name,
    encode_cd_name,
    get_all_species,
    get_catalyzed_reactions,
    get_complex_children,
    get_included_species,
    get_modifications,
    get_structural_state,
    get_species_state,
    set_structural_state,
    get_protein_residues,
    get_entity_definitions,
    remove_unused_entity_definitions,
    remove_species,
    remove_orphaned_species,
    merge_entity_definitions,
    get_position_to_compartment,
    get_protein_type,
    get_species_by_id,
    get_species_class,
    get_species_name,
    is_homodimer,
    get_multimer_cardinality,
    is_hypothetical,
    rename_species,
)

# Reactions
from .reactions import (
    add_reaction,
    change_reaction_type,
    get_all_reactions,
    get_connected_components,
    get_participants,
    get_reaction_species_ids,
    get_reaction_type,
    get_species_reactions,
    remove_reaction,
    replace_reaction_species,
)

# Compartments
from .compartments import (
    get_all_compartments,
    get_compartment_by_id,
    get_compartment_hierarchy,
    get_compartment_name,
    rename_compartment,
)

# Query
from .query import (
    find_by_annotation,
    find_by_class,
    find_by_name,
    find_by_protein_type,
    find_by_reaction_type,
    find_equivalent_species,
)

# Layout
from .layout import (
    bounds_contain,
    get_activity, set_activity,
    get_alias_by_id,
    get_aliases_for_species,
    get_all_compartment_aliases,
    get_all_complex_aliases,
    get_all_species_aliases,
    get_bounds,
    get_colour,
    get_compartment_alias_chain,
    get_enclosing_compartment_alias,
    get_line_width,
    get_parent_alias,
    get_view_state,
    locate_species,
    set_bounds,
    set_colour,
    set_line_width,
)

__all__ = [
    # io
    "CDDiagram", "load_diagram", "save_diagram", "get_canvas_size",
    # validation
    "ValidationError", "validate_diagram", "validate_file", "validate_xml_bytes",
    # annotations
    "get_annotations", "set_annotations", "add_annotation", "remove_annotation",
    "parse_miriam_uri", "make_miriam_uri", "get_notes_text", "set_notes_text",
    # species
    "get_all_species", "get_included_species", "get_species_by_id",
    "get_species_class", "get_species_name", "get_position_to_compartment",
    "get_protein_type", "is_homodimer", "get_multimer_cardinality", "is_hypothetical",
    "get_modifications", "get_structural_state", "get_species_state", "set_structural_state",
    "get_protein_residues", "get_catalyzed_reactions",
    "get_entity_definitions", "remove_unused_entity_definitions",
    "merge_entity_definitions", "remove_species", "remove_orphaned_species",
    "rename_species", "change_protein_type",
    "get_complex_children", "encode_cd_name", "decode_cd_name",
    # reactions
    "get_all_reactions", "get_reaction_type", "get_participants",
    "change_reaction_type", "add_reaction", "remove_reaction",
    "get_reaction_species_ids", "get_species_reactions", "get_connected_components",
    "replace_reaction_species",
    # compartments
    "get_all_compartments", "get_compartment_by_id", "get_compartment_hierarchy",
    "get_compartment_name", "rename_compartment",
    # query
    "find_by_name", "find_by_class", "find_by_annotation",
    "find_by_protein_type", "find_by_reaction_type", "find_equivalent_species",
    # layout
    "get_aliases_for_species", "get_all_species_aliases", "get_all_complex_aliases",
    "get_all_compartment_aliases",
    "get_alias_by_id", "get_parent_alias",
    "get_activity", "set_activity", "get_view_state",
    "get_colour", "set_colour",
    "get_line_width", "set_line_width",
    "get_bounds", "set_bounds",
    "bounds_contain", "get_enclosing_compartment_alias",
    "get_compartment_alias_chain", "locate_species",
]
