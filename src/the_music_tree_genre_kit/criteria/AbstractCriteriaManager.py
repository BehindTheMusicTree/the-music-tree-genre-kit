import uuid
from typing import Any, TypeVar

from django.db import IntegrityError, models, transaction
from django.db.models import QuerySet
from django.utils.translation import gettext as _
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.base.bulk_mti import bulk_create_mti
from the_music_tree_genre_kit.base.constraint_violation import constraint_violated
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
        visited_ascendant_ids = {instance.pk}

        while current_parent:
            if current_parent.pk in visited_ascendant_ids:
                raise ValueError(f"Cycle detected in criteria parent chain at {instance.pk!r}")
            visited_ascendant_ids.add(current_parent.pk)
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

    def _model_has_wikidata_id_field(self) -> bool:
        """
        Whether this manager's model declares a `wikidata_id` column. Only a concrete
        `Genre` subtype (via the `AbstractGenreCriteria` mixin) does -- tag-type criteria
        have no such notion of identity, so `import_criteria_tree`/`build_criteria_tree`
        fall back to the plain delete-and-recreate behavior for them.
        """
        return any(field.name == Fields.WIKIDATA_ID for field in self.model._meta.get_fields())

    def _model_has_manual_edit_fields(self) -> bool:
        """
        Whether this manager's model declares the `is_manually_edited`/`is_excluded`
        columns. Only a concrete `Genre` subtype (via `AbstractGenreCriteria`) does --
        without these, `import_criteria_tree` has no override state to respect.
        """
        return any(field.name == "is_manually_edited" for field in self.model._meta.get_fields())

    def _on_created(self, instance: T, *, actor: Any = None) -> None:
        """Hook: react to a newly created criteria. No-op by default."""

    def _on_bulk_created(self, instances: list[T], *, actor: Any = None) -> None:
        """Hook: react to a batch of criteria created by `import_criteria_tree`. No-op by default."""

    def _on_parent_changed(
        self, instance: T, *, old_parent: T | None, old_root: T, root_changed: bool, actor: Any = None
    ) -> None:
        """Hook: react to a criteria being reparented (and possibly re-rooted). No-op by default."""

    def _on_renamed(self, instance: T, *, old_name: str, actor: Any = None) -> None:
        """Hook: react to a criteria being renamed. No-op by default."""

    def _on_track_genre_cleared(self, track: models.Model, *, actor: Any = None) -> None:
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
    def _on_before_delete(self, instance: T, *, actor: Any = None) -> None:
        criteria_playlist = instance.criteria_playlist
        playlist_manager = type(criteria_playlist).objects
        track_model = playlist_manager.track_model

        genre_tagged_tracks = list(track_model.objects.filter(genre=instance))
        direct_tracks = self._get_direct_tracks(instance) if instance.is_root else None

        for track in genre_tagged_tracks:
            track.genre = instance.parent
            track.save(update_fields=["genre_id"])
            self._on_track_genre_cleared(track, actor=actor)

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

    def _create_without_ascendant_refresh(self, actor: Any = None, **kwargs) -> T:
        criteria_type = self._get_criteria_type()
        instance: T = super().create(type=criteria_type, **kwargs)
        self._on_created(instance, actor=actor)
        return instance

    @transaction.atomic
    def create(self, actor: Any = None, **kwargs) -> T:
        instance = self._create_without_ascendant_refresh(actor=actor, **kwargs)
        self._refresh_ascendants_of_instance(instance)
        return instance

    @transaction.atomic
    def update_instance(self, instance: T, actor: Any = None, **kwargs) -> T:
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
                updated_instance, old_parent=old_parent, old_root=old_root, root_changed=root_changed, actor=actor
            )

        if old_name != updated_instance.name:
            self._on_renamed(updated_instance, old_name=old_name, actor=actor)

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
    def delete_instance(self, instance: T, actor: Any = None) -> None:
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
        self._on_before_delete(instance, actor=actor)

        instance.delete()

    def _delete_stale_instances(self, queryset: QuerySet[T], actor: Any = None) -> None:
        """
        Delete instances dropped from an imported tree by routing each one through
        `delete_instance`, leaves first, instead of a raw bulk `.delete()`.

        A raw bulk delete skips `_on_before_delete`'s track reparenting: `Track.genre` is
        `on_delete=DO_NOTHING`, so a track still pointing at a deleted row raises an unhandled
        `IntegrityError`. Processing leaves first mirrors what repeated one-off deletes would do
        -- each instance's tracks and child playlists reparent up to its still-live parent
        (possibly another about-to-be-deleted stale instance, itself processed next) -- so tracks
        end up reparented to the nearest surviving ancestor, or handed to the criteria-less
        playlist once a stale root's turn comes, rather than left dangling.
        """
        instances = list(queryset)
        instances.sort(key=lambda instance: instance.ascendants_rels.count(), reverse=True)
        for instance in instances:
            self.delete_instance(instance, actor=actor)

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
        model_has_wikidata_id_field = self._model_has_wikidata_id_field()

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
                if model_has_wikidata_id_field:
                    node[InputFields.ID] = criteria.wikidata_id
                result.append(node)

            return result

        return build_tree(None)

    @transaction.atomic
    def import_criteria_tree(self, user: Any, data: dict, actor: Any = None) -> None:
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

        Rows with `is_manually_edited=True` (Genre-only, see `AbstractGenreCriteria`) are
        still matched by `wikidata_id`/name so their children keep importing normally, but
        their own `parent`/`_name`/`side`/`root` are left untouched -- an admin edit always
        wins over the next sync. Rows with `is_excluded=True` are skipped entirely (not
        updated, not recursed into) and are protected from the stale-deletion pass below,
        regardless of whether this import's tree still contains their `wikidata_id`.
        """
        if not data:
            return

        model_has_wikidata_id_field = self._model_has_wikidata_id_field()
        model_has_manual_edit_fields = self._model_has_manual_edit_fields()

        existing_by_name: dict[str, T] = {}

        if not model_has_wikidata_id_field:
            self._delete_stale_instances(self.filter(user=user), actor=actor)
            existing_by_wikidata_id: dict[str, T] = {}
        else:
            existing_by_wikidata_id = {}
            for criteria in self.filter(user=user):
                existing_by_name[criteria.name] = criteria
                if criteria.wikidata_id:
                    existing_by_wikidata_id[criteria.wikidata_id] = criteria

        # Excluded wikidata_ids are never touched by import -- neither recreated nor
        # deleted -- regardless of whether this run's tree still contains them.
        protected_wikidata_ids: set[str] = set()
        if model_has_manual_edit_fields:
            protected_wikidata_ids = {
                wikidata_id for wikidata_id, criteria in existing_by_wikidata_id.items() if criteria.is_excluded
            }

        if isinstance(data, dict) and TreeImportFields.TREE in data:
            tree_data = data[TreeImportFields.TREE]
        elif isinstance(data, list):
            tree_data = data
        else:
            tree_data = []

        if not tree_data:
            if model_has_wikidata_id_field:
                stale_wikidata_ids = existing_by_wikidata_id.keys() - protected_wikidata_ids
                self._delete_stale_instances(self.filter(user=user, wikidata_id__in=stale_wikidata_ids), actor=actor)
            return

        criteria_type = self._get_criteria_type()
        model_has_side_field = self._model_has_side_field()

        new_instances: list[T] = []
        matched_instances: list[T] = []
        matched_wikidata_ids: set[str] = set()

        def build_criteria_tree(nodes, parent: T | None, root: T | None):
            for node in nodes:
                extra_kwargs = {Fields.SIDE: node.get(InputFields.SIDE)} if model_has_side_field else {}
                node_name = node.get(InputFields.NAME_PUBLIC)
                wikidata_id = node.get(InputFields.ID) if model_has_wikidata_id_field else None
                matched_criteria = existing_by_wikidata_id.get(wikidata_id) if wikidata_id else None
                if matched_criteria is None and model_has_wikidata_id_field and not wikidata_id:
                    # No id on this node: fall back to matching an existing row by name, so
                    # that repeat imports of an id-less tree (e.g. a consumer's bundled seed
                    # tree with no wikidataIds) stay idempotent instead of re-inserting every
                    # node and hitting unique_name_per_user. `name` is already unique per user
                    # regardless of parent, so matching on name alone is sufficient.
                    matched_criteria = existing_by_name.get(node_name)

                if matched_criteria is not None and model_has_manual_edit_fields and matched_criteria.is_excluded:
                    # Admin-excluded: keep it (and its subtree) out of this import entirely.
                    existing_by_name.pop(node_name, None)
                    continue

                is_locked = False
                if matched_criteria is not None:
                    criteria: T = matched_criteria
                    is_locked = model_has_manual_edit_fields and criteria.is_manually_edited
                    if not is_locked:
                        criteria.parent = parent
                        for field_name, value in extra_kwargs.items():
                            setattr(criteria, field_name, value)
                        criteria._name = node_name
                        criteria.root = root if root is not None else criteria
                    if wikidata_id:
                        matched_wikidata_ids.add(wikidata_id)
                    elif matched_criteria.wikidata_id:
                        # Matched by name onto a row that still carries its own wikidata_id
                        # (this import's node just didn't repeat it): keep it out of the
                        # stale-wikidata_id deletion pass below.
                        matched_wikidata_ids.add(matched_criteria.wikidata_id)
                    existing_by_name.pop(node_name, None)
                    matched_instances.append(criteria)
                else:
                    criteria = self.model(user=user, type=criteria_type, parent=parent, **extra_kwargs)

                    # Pre-generate the PK ourselves (rather than relying on the field's
                    # `default=uuid.uuid4`): for an MTI model the PK and the inherited
                    # base-table `uuid` are two distinct Python attributes and must be
                    # forced to the same value, since plain construction defaults each
                    # independently.
                    pk = uuid.uuid4()
                    criteria.uuid = pk
                    criteria.pk = pk
                    criteria._name = node_name
                    criteria.root = root if root is not None else criteria
                    if model_has_wikidata_id_field:
                        criteria.wikidata_id = wikidata_id
                    new_instances.append(criteria)

                if hasattr(criteria, "_validate_side"):
                    criteria._validate_side()

                children = node.get(InputFields.CHILDREN) or []
                if children:
                    # A locked row's own root wasn't touched above (it may not even match
                    # this branch's tree-walk root, if an admin moved it elsewhere) -- recurse
                    # using its real current root so descendants land under the right tree.
                    child_root = criteria.root if is_locked else (root if root is not None else criteria)
                    build_criteria_tree(children, criteria, child_root)

        build_criteria_tree(tree_data, None, None)

        if model_has_wikidata_id_field:
            stale_wikidata_ids = existing_by_wikidata_id.keys() - matched_wikidata_ids - protected_wikidata_ids
            if stale_wikidata_ids:
                self._delete_stale_instances(self.filter(user=user, wikidata_id__in=stale_wikidata_ids), actor=actor)

        matched_update_fields = [Fields.NAME_INTERNAL, Fields.PARENT, Fields.ROOT]
        if model_has_side_field:
            matched_update_fields.append(Fields.SIDE)

        try:
            bulk_create_mti(new_instances, using=self.db)
            for criteria in matched_instances:
                if model_has_manual_edit_fields and criteria.is_manually_edited:
                    continue  # locked: nothing was mutated above, nothing to persist
                # Pass `update_fields` explicitly: `AbstractCriteria._prepare_save` calls
                # `_set_root()`, and when root changes, `BaseModel.save()` (the-music-tree-api-kit)
                # restricts the UPDATE to only the fields it saw explicitly modified via
                # `ctx.add_modified_field` -- silently dropping our plain attribute assignments
                # (name/parent/side) above unless we list them here too.
                criteria.save(update_fields=matched_update_fields)
        except IntegrityError as e:
            error_message = str(e)
            if constraint_violated(model=self.model, error_message=error_message, constraint_name="non_empty_name"):
                raise AppValidationException(
                    field_name=Fields.NAME_PUBLIC,
                    message=_("Name cannot be empty"),
                    field_validation_error_code=FieldValidationErrorCode.NAME_EMPTY,
                )
            if constraint_violated(
                model=self.model, error_message=error_message, constraint_name="unique_name_per_user"
            ):
                raise AppValidationException(
                    field_name=Fields.NAME_PUBLIC,
                    message=_("A criteria name is already used"),
                    field_validation_error_code=FieldValidationErrorCode.NAME_DUPLICATE,
                )
            # Let other database integrity errors propagate to be handled as system errors
            raise

        for top_level_node in (*new_instances, *matched_instances):
            if top_level_node.parent_id is None:
                self._refresh_ascendants_of_instance_and_children(top_level_node)

        self._on_bulk_created(new_instances, actor=actor)
