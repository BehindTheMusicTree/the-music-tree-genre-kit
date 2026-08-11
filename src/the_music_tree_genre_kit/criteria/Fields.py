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
    CHILDREN = "children"
