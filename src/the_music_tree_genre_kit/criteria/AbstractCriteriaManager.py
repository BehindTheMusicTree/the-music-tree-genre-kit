from typing import Any, TypeVar

from django.db import models, transaction
from django.db.models import QuerySet
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.serializer.model.criteria.input.Fields import Fields as InputFields
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.Fields import Fields as TreeImportFields

from .AbstractCriteria import AbstractCriteria
from .Fields import Fields
from .type.CriteriaType import CriteriaType

T = TypeVar("T", bound=AbstractCriteria)


class AbstractCriteriaManager(StandardResourceManager[T]):
    """
    Owns the pure tree-structure logic for criteria (ascendant refresh, root
    propagation, common-ascendant lookup), plus the criteria-playlist
    orchestration around deletion (direct-track transfer to the criteria-less
    playlist, child reparenting) built on the sibling
    AbstractCriteriaPlaylistManager reached via `instance.criteria_playlist`.
    Side effects outside that (playlists, file metadata, etc.) are left to
    subclasses via the `_on_created`/`_on_parent_changed`/`_on_renamed`/
    `_on_track_genre_cleared` hooks.

    Concrete subclasses must set `lineage_rel_model` to their concrete
    AbstractCriteriaLineageRel subclass, and override `_get_criteria_type`
    to return the CriteriaType their model represents. A criteria type whose
    "direct tracks" aren't simply the ones in `TrackPlaylistRel` (e.g. Genre,
    where a track's leaf FK also propagates `TrackPlaylistRel` rows to
    ancestor playlists) must override `_get_direct_tracks`.
    """

    model: type[T]
    lineage_rel_model: type[models.Model]

    def _get_criteria_type(self) -> CriteriaType:
        """Hook: return the CriteriaType this manager's model represents. Must be overridden."""
        raise NotImplementedError

    def _create_lineage_rel(self, *, user: Any, descendant: T, ascendant: T, degree: int) -> None:
        self.lineage_rel_model.objects.create(user=user, descendant=descendant, ascendant=ascendant, degree=degree)

    def _refresh_ascendants_of_instance(self, instance: T):
        instance.ascendants_rels.all().delete()
        current_degree = 1
        current_parent = instance.parent

        while current_parent:
            self._create_lineage_rel(
                user=instance.user, descendant=instance, ascendant=current_parent, degree=current_degree
            )
            current_parent = current_parent.parent
            current_degree = current_degree + 1

    def _refresh_ascendants_of_instance_and_children(self, instance):
        self._refresh_ascendants_of_instance(instance)
        for child in self.filter(parent=instance):
            self._refresh_ascendants_of_instance_and_children(child)

    def _refresh_ascendants_of_descendants(self, instance):
        for child in instance.children.all():
            self._refresh_ascendants_of_instance_and_children(child)

    def get_default_ordering(self) -> list[str]:
        return [Fields.NAME_INTERNAL]

    def _model_has_side_field(self) -> bool:
        """
        Whether this manager's model declares a `side` column. Only a concrete `Genre`
        subtype (via the `AbstractGenreCriteria` mixin) does -- `side` is no longer on
        the shared `AbstractCriteria` table, so this can't be assumed generically.
        """
        return any(field.name == Fields.SIDE for field in self.model._meta.get_fields())

    def _on_created(self, instance: T) -> None:
        """Hook: react to a newly created criteria. No-op by default."""

    def _on_parent_changed(self, instance: T, *, old_parent: T | None, old_root: T, root_changed: bool) -> None:
        """Hook: react to a criteria being reparented (and possibly re-rooted). No-op by default."""

    def _on_renamed(self, instance: T, *, old_name: str) -> None:
        """Hook: react to a criteria being renamed. No-op by default."""

    def _on_track_genre_cleared(self, track: models.Model) -> None:
        """Hook: react to a track's genre FK being cleared/reassigned by a root-criteria deletion. No-op by default."""

    def _get_direct_tracks(self, instance: T) -> QuerySet:
        """
        Tracks directly attached to `instance`'s own playlist (not via a
        descendant's ascendant-propagated `TrackPlaylistRel` row). Default is
        generic (TrackPlaylistRel-based); override for criteria types whose
        leaf FK propagates rows to ancestor playlists (e.g. Genre).
        """
        playlist_manager = type(instance.criteria_playlist).objects
        return playlist_manager.get_direct_tracks(instance.criteria_playlist)

    @transaction.atomic
    def _on_before_delete(self, instance: T) -> None:
        criteria_playlist = instance.criteria_playlist
        playlist_manager = type(criteria_playlist).objects
        track_model = playlist_manager.track_model

        genre_tagged_tracks = list(track_model.objects.filter(genre=instance))
        direct_tracks = self._get_direct_tracks(instance) if instance.is_root else None

        for track in genre_tagged_tracks:
            track.genre = instance.parent
            track.save(update_fields=["genre_id"])
            self._on_track_genre_cleared(track)

        if instance.is_root:
            playlist_manager.transfer_direct_tracks_to_criterialess_playlist(
                direct_tracks=direct_tracks, criteria_playlist=criteria_playlist
            )

        if criteria_playlist.children.exists():
            for child_playlist in criteria_playlist.children.all():
                child_playlist.parent = instance.parent.criteria_playlist if instance.parent else None
                child_playlist.save(update_fields=[Fields.PARENT])

                if not instance.parent:
                    playlist_manager.make_playlist_root(child_playlist)

    @transaction.atomic
    def create(self, **kwargs) -> T:
        criteria_type = self._get_criteria_type()
        instance: T = super().create(type=criteria_type, **kwargs)
        self._on_created(instance)
        self._refresh_ascendants_of_instance(instance)
        return instance

    @transaction.atomic
    def update_instance(self, instance: T, **kwargs) -> T:
        old_root = instance.root
        old_parent = instance.parent
        old_name = instance.name

        updated_instance: T = super().update_instance(instance, **kwargs)

        if old_parent != updated_instance.parent:
            self._refresh_ascendants_of_instance_and_children(updated_instance)

            root_changed = old_root != updated_instance.root
            if root_changed:
                self.update_children_root(criteria=updated_instance, new_root=updated_instance.root)

            self._on_parent_changed(
                updated_instance, old_parent=old_parent, old_root=old_root, root_changed=root_changed
            )

        if old_name != updated_instance.name:
            self._on_renamed(updated_instance, old_name=old_name)

        return updated_instance

    def get_common_ascendant(self, criteria_a: T | None, criteria_b: T | None) -> T | None:
        if not criteria_a or not criteria_b:
            return None

        visited = set()
        current = criteria_a
        while current:
            visited.add(current)
            current = current.parent

        current = criteria_b
        while current:
            if current in visited:
                return current
            current = current.parent

        return None

    @transaction.atomic
    def delete_instance(self, instance: T) -> None:
        """
        Delete a criteria and handle tree relationships.

        When deleting a criteria:
        - If it has children and a parent, children are reassigned to the parent
        - If it has children but no parent, children become root criteria
        Non-tree side effects (uploaded tracks, playlists) are left to `_on_before_delete`.
        """
        if instance.children.exists():
            children = list(instance.children.all())

            for child in children:
                child.parent = instance.parent
                child.root = instance.parent or child
                child.save(update_fields=[Fields.PARENT, Fields.ROOT])
                self._refresh_ascendants_of_instance_and_children(child)
                self.update_children_root(child, child.root)

        # Model-level tree state must be updated before this hook runs: subclass hooks
        # (e.g. playlist maintenance) may re-derive fields from the criteria's current
        # parent/root, so they need the post-reassignment state, not the pre-delete one.
        self._on_before_delete(instance)

        instance.delete()

    def get_roots(self, user: Any) -> QuerySet[T]:
        return self.filter(user=user, parent__isnull=True)

    def update_children_root(self, criteria: T, new_root: T):
        children = criteria.children.all()
        if children.exists():
            children.update(root=new_root)
            for child in children:
                self.update_children_root(child, new_root)

    def build_criteria_tree(self, user: Any) -> list[dict]:
        """
        Builds a tree structure of all criteria for a given user.
        The structure follows the format:
        {
          "name": "Criteria name",
          "children": [
            {
              "name": "Child criteria name",
              "children": []
            }
          ]
        }
        """
        queryset = self.filter(user=user).select_related(Fields.PARENT)
        model_has_side_field = self._model_has_side_field()

        criteria_by_parent = {}
        for criteria in queryset:
            parent_id = criteria.parent.uuid if hasattr(criteria.parent, "uuid") else criteria.parent_id
            if parent_id not in criteria_by_parent:
                criteria_by_parent[parent_id] = []
            criteria_by_parent[parent_id].append(criteria)

        def build_tree(parent_id):
            if parent_id not in criteria_by_parent:
                return []

            result = []
            for criteria in criteria_by_parent[parent_id]:
                child_id = criteria.uuid if hasattr(criteria, "uuid") else criteria.id
                node = {
                    InputFields.NAME_PUBLIC: criteria.name,
                    InputFields.CHILDREN: build_tree(child_id),
                    InputFields.SIDE: criteria.side if model_has_side_field else None,
                }
                result.append(node)

            return result

        return build_tree(None)

    @transaction.atomic
    def import_criteria_tree(self, user: Any, data: dict) -> None:
        """
        Imports a tree structure of criteria, replacing all existing criteria.
        The input should be an array of criteria trees, where each tree follows the format:
        {
          "name": "Criteria name",
          "children": [
            {
              "name": "Child criteria name",
              "children": []
            }
          ]
        }
        """
        if not data:
            return

        self.filter(user=user).delete()

        if isinstance(data, dict) and TreeImportFields.TREE in data:
            tree_data = data[TreeImportFields.TREE]
        elif isinstance(data, list):
            tree_data = data
        else:
            tree_data = []

        if not tree_data:
            return

        model_has_side_field = self._model_has_side_field()

        def create_criteria_tree(nodes, parent=None):
            for node in nodes:
                name = node.get(InputFields.NAME_PUBLIC)
                extra_kwargs = {Fields.SIDE: node.get(InputFields.SIDE)} if model_has_side_field else {}
                criteria = self.create(name=name, parent=parent, user=user, **extra_kwargs)

                children = node.get(InputFields.CHILDREN, [])
                if children is None:
                    children = []

                if children:
                    create_criteria_tree(children, criteria)

        create_criteria_tree(tree_data)
