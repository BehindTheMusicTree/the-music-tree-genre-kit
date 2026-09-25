from enum import StrEnum


class CriteriaOutputFieldKey(StrEnum):
    CREATED_ON = "created_on"
    UPDATED_ON = "updated_on"
    UUID = "uuid"
    NAME = "name"
    NAME_INTERNAL = "_name"
    ROOT = "root"
    PARENT = "parent"
    ASCENDANTS = "ascendants"
    DESCENDANTS = "descendants"
    CHILDREN = "children"
    SIDE = "side"
    SUMMARY = "summary"
    ALLOWS_MULTIPLE_PRIMARY_PARENTS = "allows_multiple_primary_parents"
    PRIMARY_PARENTS = "primary_parents"
    SECONDARY_PARENTS = "secondary_parents"
