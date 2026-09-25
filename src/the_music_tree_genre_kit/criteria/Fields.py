from the_music_tree_api_kit.private_unique_resource.Fields import Fields as PrivateUniqueResourceFields


class Fields(PrivateUniqueResourceFields):
    NAME_PUBLIC = "name"
    NAME_INTERNAL = f"_{NAME_PUBLIC}"
    ASCENDANTS = "ascendants"
    ASCENDANTS_RELS = "ascendants_rels"
    DESCENDANTS = "descendants"
    DESCENDANTS_RELS = "descendants_rels"
    ROOT = "root"
    PARENT = "parent"
    ALLOWS_MULTIPLE_PRIMARY_PARENTS = "allows_multiple_primary_parents"
    ADDITIONAL_PRIMARY_PARENTS = "additional_primary_parents"
    ADDITIONAL_PRIMARY_CHILDREN = "additional_primary_children"
    SECONDARY_PARENTS = "secondary_parents"
    SECONDARY_CHILDREN = "secondary_children"
    CHILDREN = "children"
    SIDE = "side"
    SUMMARY = "summary"
    WIKIDATA_ID = "wikidata_id"
