import uuid
from collections import defaultdict
from typing import Any, TypeVar

from django.db import IntegrityError, models, transaction
from django.db.models import QuerySet
from django.utils import timezone
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
    propagation, primary-parent track moves), plus the criteria-playlist
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
        for ascendant, degree in instance.primary_ascendants().values():
            self._create_lineage_rel(user=instance.user, descendant=instance, ascendant=ascendant, degree=degree)

    def _primary_children(self, instance: T) -> QuerySet[T]:
        return self.filter(models.Q(parent=instance) | models.Q(additional_primary_parents=instance)).distinct()

    def _refresh_ascendants_of_instance_and_children(self, *instances: T) -> None:
        """`_refresh_ascendants_of_instance` for `instances` and every primary descendant, computed
        in memory from one load of the owner's primary-parent graph: one delete and one bulk insert
        instead of per-row queries (a full tree import touches every row)."""
        if not instances:
            return
        user_id = instances[0].user_id
        parents_by_pk: dict[Any, list[Any]] = {
            pk: [parent_id] if parent_id else []
            for pk, parent_id in self.filter(user_id=user_id).values_list("pk", Fields.PARENT)
        }
        field = self.model._meta.get_field(Fields.ADDITIONAL_PRIMARY_PARENTS)
        child_col, parent_col = field.m2m_field_name(), field.m2m_reverse_field_name()
        for child_pk, parent_pk in field.remote_field.through.objects.filter(
            **{f"{child_col}__user_id": user_id}
        ).values_list(child_col, parent_col):
            parents_by_pk[child_pk].append(parent_pk)

        children_by_pk: dict[Any, list[Any]] = defaultdict(list)
        for pk, parent_pks in parents_by_pk.items():
            for parent_pk in parent_pks:
                children_by_pk[parent_pk].append(pk)
        affected: set[Any] = set()
        stack = [instance.pk for instance in instances]
        while stack:
            pk = stack.pop()
            if pk not in affected:
                affected.add(pk)
                stack.extend(children_by_pk[pk])

        rels = []
        for pk in affected:
            degree_by_ascendant: dict[Any, int] = {}
            frontier, degree = [pk], 0
            while frontier:
                degree += 1
                next_frontier = []
                for node_pk in frontier:
                    for parent_pk in parents_by_pk[node_pk]:
                        if parent_pk == pk:
                            raise ValueError(f"Cycle detected in criteria primary parents at {pk!r}")
                        if parent_pk not in degree_by_ascendant:
                            degree_by_ascendant[parent_pk] = degree
                            next_frontier.append(parent_pk)
                frontier = next_frontier
            rels.extend(
                self.lineage_rel_model(user_id=user_id, descendant_id=pk, ascendant_id=ascendant_pk, degree=d)
                for ascendant_pk, d in degree_by_ascendant.items()
            )
        self.lineage_rel_model.objects.filter(descendant_id__in=affected).delete()
        self.lineage_rel_model.objects.bulk_create(rels, batch_size=1000)

    def _validate_parents(self, instance: T) -> None:
        """Fail fast on any broken primary/secondary parent invariant (see `AbstractCriteria`)."""
        additional = list(instance.additional_primary_parents.all())
        secondary = list(instance.secondary_parents.all())
        primary = [instance.parent, *additional] if instance.parent else additional

        def fail(field_name: str, message: str, code: FieldValidationErrorCode):
            raise AppValidationException(field_name=field_name, message=message, field_validation_error_code=code)

        if additional and not instance.allows_multiple_primary_parents:
            fail(
                Fields.ADDITIONAL_PRIMARY_PARENTS,
                _("Only a criteria allowing multiple primary parents can have additional primary parents"),
                FieldValidationErrorCode.DEPENDENCY_MISSING,
            )
        if additional and not instance.parent:
            fail(
                Fields.ADDITIONAL_PRIMARY_PARENTS,
                _("A criteria without a parent cannot have additional primary parents"),
                FieldValidationErrorCode.DEPENDENCY_MISSING,
            )
        if not instance.allows_multiple_primary_parents and any(p.allows_multiple_primary_parents for p in primary):
            fail(
                Fields.ALLOWS_MULTIPLE_PRIMARY_PARENTS,
                _("A child of a criteria allowing multiple primary parents must allow them too"),
                FieldValidationErrorCode.DEPENDENCY_MISSING,
            )

        parent_ids = [p.pk for p in (*primary, *secondary)]
        if instance.pk in parent_ids:
            fail(Fields.PARENT, _("A criteria cannot be its own parent"), FieldValidationErrorCode.SELF_REFERENCE)
        if len(parent_ids) != len(set(parent_ids)):
            fail(Fields.PARENT, _("A parent can only be linked once"), FieldValidationErrorCode.DUPLICATE)
        for parent in (*primary, *secondary):
            if parent.type_id != instance.type_id:
                fail(Fields.PARENT, _("A parent must have the same type"), FieldValidationErrorCode.REFERENCE_INVALID)
            if parent.is_descendant_of(instance):
                fail(Fields.PARENT, _("A parent cannot be a descendant"), FieldValidationErrorCode.ANCESTOR_REFERENCE)

    def _set_parent_links(self, instance: T, additional_primary_parents, secondary_parents) -> None:
        if additional_primary_parents is not None:
            instance.additional_primary_parents.set(additional_primary_parents)
        if secondary_parents is not None:
            instance.secondary_parents.set(secondary_parents)
        self._validate_parents(instance)

    def _primary_ascendants_by_pk(self, instance: T) -> dict[Any, T]:
        return {pk: ascendant for pk, (ascendant, _degree) in instance.primary_ascendants().items()}

    def _move_tracks_after_primary_parents_changed(self, instance: T, old_ascendants: dict[Any, T]) -> None:
        """
        Re-propagates the tracks in `instance`'s playlist after its primary parents changed:
        added to every gained ascendant's playlist, removed from every lost one unless the
        track still reaches it through another primary path (its genre's current lineage).
        Non-genre criteria have no track-to-criteria link, so lost ascendants always drop them.
        """
        from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

        new_ascendants = self._primary_ascendants_by_pk(instance)
        gained_ids = new_ascendants.keys() - old_ascendants.keys()
        lost_ids = old_ascendants.keys() - new_ascendants.keys()
        if not gained_ids and not lost_ids:
            return

        playlist_manager = type(instance.criteria_playlist).objects
        rel_model = playlist_manager.track_playlist_rel_model
        tracks = list(playlist_manager.get_direct_tracks(instance.criteria_playlist))

        for ascendant_id in gained_ids:
            playlist = new_ascendants[ascendant_id].criteria_playlist
            present_ids = set(rel_model.objects.filter(playlist=playlist).values_list("track_id", flat=True))
            for track in tracks:
                if track.pk not in present_ids:
                    playlist_manager._create_track_rel(user=instance.user, playlist=playlist, track=track)

        if not lost_ids:
            return
        reached_ids_by_genre_id: dict[Any, set[Any]] = {}
        if instance.type_id == int(CriteriaTypePks.GENRE):
            for genre in {track.genre for track in tracks if track.genre_id}:
                reached_ids_by_genre_id[genre.pk] = {genre.pk, *genre.primary_ascendants()}
        for lost in (old_ascendants[pk] for pk in lost_ids):
            dropped_ids = [
                track.pk for track in tracks if lost.pk not in reached_ids_by_genre_id.get(track.genre_id, set())
            ]
            playlist_manager._delete_track_rels_and_fill_positions(
                instance=lost.criteria_playlist, tracks=playlist_manager.track_model.objects.filter(pk__in=dropped_ids)
            )

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

    def _model_has_name_conflict_field(self) -> bool:
        return any(field.name == "has_name_conflict" for field in self.model._meta.get_fields())

    def _disambiguate_conflicting_names(self, user: Any, instances: list[T], excluded_pks: set[Any]) -> None:
        """
        Renames each of `instances` whose name (case-insensitively) is already taken by another
        of the user's criteria -- or by an earlier one of `instances` -- to `"<name> (<wikidata_id>)"`,
        flagging it `has_name_conflict` for admin review instead of failing the whole import on the
        unique-name constraint. `excluded_pks` are rows about to be deleted, whose names are free.
        """
        has_flag = self._model_has_name_conflict_field()
        # The unique-name constraint spans the shared base criteria table (tags too), not just this subtype.
        base_model = (self.model._meta.get_parent_list() or [self.model])[-1]
        taken = {
            name.lower()
            for name in base_model._base_manager.filter(user=user)
            .exclude(pk__in={c.pk for c in instances} | excluded_pks)
            .values_list(Fields.NAME_INTERNAL, flat=True)
        }
        for criteria in instances:
            conflict = criteria._name.lower() in taken
            if conflict:
                criteria._name = f"{criteria._name} ({criteria.wikidata_id})"
            if has_flag:
                criteria.has_name_conflict = conflict
            taken.add(criteria._name.lower())

    def _require_node_keys(self, nodes: list[dict]) -> None:
        """
        Every node in a wikidata_id-bearing model's import must carry a non-empty
        `id` (a real wikidata QID or a synthetic key) -- matching happens by key only,
        so a key-less node can never be found again on the next import, which is how
        NULL-id duplicates were created historically. Reject the whole payload rather
        than silently dropping or duplicating such a node.
        """
        for node in nodes:
            if not node.get(InputFields.ID):
                raise AppValidationException(
                    field_name=InputFields.ID,
                    message=_("Each node requires a wikidata_id or synthetic key"),
                    field_validation_error_code=FieldValidationErrorCode.REQUIRED,
                )
            self._require_node_keys(node.get(InputFields.CHILDREN) or [])

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

        # Tracks re-genred to the main parent below no longer reach the additional primary branches.
        if genre_tagged_tracks and instance.parent:
            kept_ids = {instance.parent.pk, *instance.parent.primary_ascendants()}
            for lost_pk, lost in self._primary_ascendants_by_pk(instance).items():
                if lost_pk not in kept_ids:
                    playlist_manager._delete_track_rels_and_fill_positions(
                        instance=lost.criteria_playlist,
                        tracks=track_model.objects.filter(pk__in=[track.pk for track in genre_tagged_tracks]),
                    )

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
                # `delete_instance` already spliced the child criteria onto its new main parent.
                new_parent = child_playlist.criteria.parent
                if new_parent is None:
                    playlist_manager.make_playlist_root(child_playlist)
                    continue
                child_playlist.parent = new_parent.criteria_playlist
                child_playlist.save(update_fields=[Fields.PARENT])
                playlist_manager.update_instance_and_children_root(child_playlist, child_playlist.parent.root)

    def _create_without_ascendant_refresh(self, actor: Any = None, **kwargs) -> T:
        criteria_type = self._get_criteria_type()
        instance: T = super().create(type=criteria_type, **kwargs)
        self._on_created(instance, actor=actor)
        return instance

    @transaction.atomic
    def create(self, actor: Any = None, **kwargs) -> T:
        additional_primary_parents = kwargs.pop(Fields.ADDITIONAL_PRIMARY_PARENTS, None)
        secondary_parents = kwargs.pop(Fields.SECONDARY_PARENTS, None)
        instance = self._create_without_ascendant_refresh(actor=actor, **kwargs)
        self._set_parent_links(instance, additional_primary_parents, secondary_parents)
        self._refresh_ascendants_of_instance(instance)
        return instance

    @transaction.atomic
    def update_instance(self, instance: T, actor: Any = None, **kwargs) -> T:
        old_root = instance.root
        old_parent = instance.parent
        old_name = instance.name
        old_primary_parent_ids = {parent.pk for parent in instance.primary_parents}
        old_ascendants = self._primary_ascendants_by_pk(instance)

        additional_primary_parents = kwargs.pop(Fields.ADDITIONAL_PRIMARY_PARENTS, None)
        secondary_parents = kwargs.pop(Fields.SECONDARY_PARENTS, None)
        updated_instance: T = super().update_instance(instance, **kwargs)
        self._set_parent_links(updated_instance, additional_primary_parents, secondary_parents)

        if old_primary_parent_ids != {parent.pk for parent in updated_instance.primary_parents}:
            self._refresh_ascendants_of_instance_and_children(updated_instance)
            self._move_tracks_after_primary_parents_changed(updated_instance, old_ascendants)

        if old_parent != updated_instance.parent:
            root_changed = old_root != updated_instance.root
            if root_changed:
                self.update_children_root(criteria=updated_instance, new_root=updated_instance.root)

            self._on_parent_changed(
                updated_instance, old_parent=old_parent, old_root=old_root, root_changed=root_changed, actor=actor
            )

        if old_name != updated_instance.name:
            self._on_renamed(updated_instance, old_name=old_name, actor=actor)

        return updated_instance

    @transaction.atomic
    def delete_instance(self, instance: T, actor: Any = None) -> None:
        """
        Delete a criteria and handle tree relationships.

        The criteria is spliced out of the primary graph: each primary child (main or
        additional) gets the deleted criteria's primary parents in its place. A child left
        without a main parent promotes its first additional primary parent, or becomes a
        root criteria when it has none. Non-tree side effects (uploaded tracks, playlists)
        are left to `_on_before_delete`.
        """
        replacement_parents = instance.primary_parents
        for child in list(self._primary_children(instance)):
            new_primary: dict[Any, T] = {}
            for parent in child.primary_parents:
                for new_parent in replacement_parents if parent.pk == instance.pk else [parent]:
                    new_primary.setdefault(new_parent.pk, new_parent)
            main_parent, *additional = new_primary.values() or [None]

            child.parent = main_parent
            child.root = main_parent.root if main_parent else child
            child.save(update_fields=[Fields.PARENT, Fields.ROOT])
            child.additional_primary_parents.set(additional)
            child.secondary_parents.remove(*new_primary.values())
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

    def build_criteria_tree(self, user: Any, *, allows_multiple_primary_parents: bool) -> list[dict]:
        """
        Builds a tree structure of the user's criteria with the given
        `allows_multiple_primary_parents` flag. Nesting follows `parent`; a node whose
        parent is outside this set is top-level and lists it first in `primary_parents`.
        Additional primary and secondary parents are exported as refs (wikidata id, else name).
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
        model_has_side_field = self._model_has_side_field()
        model_has_wikidata_id_field = self._model_has_wikidata_id_field()
        ref_by_pk = {
            criteria.pk: (criteria.wikidata_id if model_has_wikidata_id_field else None) or criteria.name
            for criteria in self.filter(user=user)
        }
        queryset = list(
            self.filter(user=user, allows_multiple_primary_parents=allows_multiple_primary_parents).prefetch_related(
                Fields.ADDITIONAL_PRIMARY_PARENTS, Fields.SECONDARY_PARENTS
            )
        )
        queryset_pks = {criteria.pk for criteria in queryset}

        criteria_by_parent = {}
        for criteria in queryset:
            parent_id = criteria.parent_id if criteria.parent_id in queryset_pks else None
            if parent_id not in criteria_by_parent:
                criteria_by_parent[parent_id] = []
            criteria_by_parent[parent_id].append(criteria)

        def build_tree(parent_id):
            if parent_id not in criteria_by_parent:
                return []

            result = []
            for criteria in criteria_by_parent[parent_id]:
                node = {
                    InputFields.NAME_PUBLIC: criteria.name,
                    InputFields.CHILDREN: build_tree(criteria.pk),
                    InputFields.SIDE: criteria.side if model_has_side_field else None,
                }
                if model_has_wikidata_id_field:
                    node[InputFields.ID] = criteria.wikidata_id
                primary_parent_ids = [parent.pk for parent in criteria.additional_primary_parents.all()]
                if criteria.parent_id and parent_id is None:
                    primary_parent_ids.insert(0, criteria.parent_id)
                if primary_parent_ids:
                    node[InputFields.PRIMARY_PARENTS] = [ref_by_pk[pk] for pk in primary_parent_ids]
                if secondary_parents := criteria.secondary_parents.all():
                    node[InputFields.SECONDARY_PARENTS] = [ref_by_pk[parent.pk] for parent in secondary_parents]
                result.append(node)

            return result

        return build_tree(None)

    @transaction.atomic
    def import_criteria_tree(
        self, user: Any, data: dict, actor: Any = None, dry_run: bool = False, force: bool = False
    ) -> dict[str, Any]:
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
        still matched by key so their children keep importing normally, but their own
        `parent`/`_name`/`side`/`root` are left untouched -- an admin edit always wins over
        the next sync. Rows with `is_excluded=True` are skipped entirely (not updated, not
        recursed into) and are protected from the stale-deletion pass below, regardless of
        whether this import's tree still contains their key.

        On a wikidata_id-bearing model (Genre), every node must carry a non-empty `id` (a
        wikidata QID or a synthetic key) -- see `_require_node_keys` -- matching is by that
        key only, no name fallback. Each applied run is recorded as an `ImportRun`; every
        row this run creates or updates gets `last_seen_run` set to it, and the stale pass
        deletes only `source=pipeline` rows (not locked) whose `last_seen_run` isn't this
        run. A stale-deletion pass that would remove more than
        `settings.CRITERIA_TREE_IMPORT_STALE_DELETE_MAX_FRACTION` of existing pipeline rows
        is refused unless `force=True`. `dry_run=True` runs the whole plan-and-apply inside
        this transaction and then rolls it back, so the returned counts reflect what would
        happen without persisting anything.

        `data["allows_multiple_primary_parents"]` is required: the import only matches,
        stamps and stale-deletes rows with that flag, so the two sets import independently
        (single-primary-parent tree first, since the other references it). Node
        `primary_parents`/`secondary_parents` are refs (wikidata id, else name) to any of the
        user's rows, resolved after all rows exist; a top-level node's first primary ref
        becomes its `parent`.

        A node whose name is already taken (case-insensitively) by another of the user's
        criteria is imported as `"<name> (<id>)"` with `has_name_conflict=True` instead of
        failing the run -- see `_disambiguate_conflicting_names`.

        Returns `{"created_count", "updated_count", "deleted_count", "dry_run"}`.
        """
        empty_result = {"created_count": 0, "updated_count": 0, "deleted_count": 0, "dry_run": dry_run}
        if not data:
            return empty_result

        allows_multiple_primary_parents: bool = data[TreeImportFields.ALLOWS_MULTIPLE_PRIMARY_PARENTS]
        tree_data = data[TreeImportFields.TREE]

        model_has_wikidata_id_field = self._model_has_wikidata_id_field()
        model_has_manual_edit_fields = self._model_has_manual_edit_fields()

        if not model_has_wikidata_id_field:
            self._delete_stale_instances(
                self.filter(user=user, allows_multiple_primary_parents=allows_multiple_primary_parents), actor=actor
            )
            result = self._import_tree_without_keys(
                user=user,
                tree_data=tree_data,
                actor=actor,
                allows_multiple_primary_parents=allows_multiple_primary_parents,
            )
        else:
            result = self._import_tree_with_keys(
                user=user,
                tree_data=tree_data,
                actor=actor,
                force=force,
                model_has_manual_edit_fields=model_has_manual_edit_fields,
                allows_multiple_primary_parents=allows_multiple_primary_parents,
            )

        result["dry_run"] = dry_run
        if dry_run:
            transaction.set_rollback(True)
        return result

    def _node_parent_refs(self, node: dict, allows_multiple_primary_parents: bool) -> tuple[list[str], list[str]]:
        primary_refs = node.get(InputFields.PRIMARY_PARENTS) or []
        if primary_refs and not allows_multiple_primary_parents:
            raise AppValidationException(
                field_name=TreeImportFields.PRIMARY_PARENTS,
                message=_("Only a tree allowing multiple primary parents can list primary parents"),
                field_validation_error_code=FieldValidationErrorCode.DEPENDENCY_MISSING,
            )
        return primary_refs, node.get(InputFields.SECONDARY_PARENTS) or []

    def _import_tree_without_keys(
        self, user: Any, tree_data: list, actor: Any, allows_multiple_primary_parents: bool
    ) -> dict[str, Any]:
        """Tag-type criteria (no wikidata_id notion of identity): delete-and-recreate."""
        if not tree_data:
            return {"created_count": 0, "updated_count": 0, "deleted_count": 0}

        criteria_type = self._get_criteria_type()
        model_has_side_field = self._model_has_side_field()
        new_instances: list[T] = []
        top_level_instances: list[T] = []
        pending_parent_refs: list[tuple[T, bool, list[str], list[str]]] = []

        def build(nodes, parent: T | None, root: T | None):
            for node in nodes:
                primary_refs, secondary_refs = self._node_parent_refs(node, allows_multiple_primary_parents)
                extra_kwargs = {Fields.SIDE: node.get(InputFields.SIDE)} if model_has_side_field else {}
                criteria = self.model(
                    user=user,
                    type=criteria_type,
                    parent=parent,
                    allows_multiple_primary_parents=allows_multiple_primary_parents,
                    **extra_kwargs,
                )
                pk = uuid.uuid4()
                criteria.uuid = pk
                criteria.pk = pk
                criteria._name = node.get(InputFields.NAME_PUBLIC)
                criteria.root = root if root is not None else criteria
                new_instances.append(criteria)
                if hasattr(criteria, "_validate_side"):
                    criteria._validate_side()
                if parent is None:
                    top_level_instances.append(criteria)
                pending_parent_refs.append((criteria, parent is None, primary_refs, secondary_refs))
                build(node.get(InputFields.CHILDREN) or [], criteria, root if root is not None else criteria)

        build(tree_data, None, None)
        try:
            bulk_create_mti(new_instances, using=self.db)
        except IntegrityError as e:
            self._raise_for_known_constraint(e)
        self._finish_import(user, new_instances, top_level_instances, pending_parent_refs, actor=actor)
        return {"created_count": len(new_instances), "updated_count": 0, "deleted_count": 0}

    def _raise_for_known_constraint(self, error: IntegrityError) -> None:
        error_message = str(error)
        if constraint_violated(model=self.model, error_message=error_message, constraint_name="non_empty_name"):
            raise AppValidationException(
                field_name=Fields.NAME_PUBLIC,
                message=_("Name cannot be empty"),
                field_validation_error_code=FieldValidationErrorCode.NAME_EMPTY,
            )
        if constraint_violated(model=self.model, error_message=error_message, constraint_name="unique_name_per_user"):
            raise AppValidationException(
                field_name=Fields.NAME_PUBLIC,
                message=_("A criteria name is already used"),
                field_validation_error_code=FieldValidationErrorCode.NAME_DUPLICATE,
            )
        # Let other database integrity errors propagate to be handled as system errors
        raise error

    def _import_tree_with_keys(
        self,
        user: Any,
        tree_data: list,
        actor: Any,
        force: bool,
        model_has_manual_edit_fields: bool,
        allows_multiple_primary_parents: bool,
    ) -> dict[str, Any]:
        from django.conf import settings

        from .children.genre.CriteriaSource import CriteriaSource
        from .import_run.ImportRun import ImportRun

        self._require_node_keys(tree_data)

        scoped_queryset = self.filter(user=user, allows_multiple_primary_parents=allows_multiple_primary_parents)
        existing_by_key: dict[str, T] = {
            criteria.wikidata_id: criteria for criteria in scoped_queryset if criteria.wikidata_id
        }
        # Rows imported before nodes carried a key: adopted by name, then keyed.
        legacy_by_name: dict[str, T] = {
            criteria.name.lower(): criteria
            for criteria in scoped_queryset.filter(
                wikidata_id__isnull=True, source=CriteriaSource.PIPELINE, is_manually_edited=False
            )
        }
        protected_keys: set[str] = set()
        if model_has_manual_edit_fields:
            protected_keys = {key for key, criteria in existing_by_key.items() if criteria.is_excluded}

        pipeline_count_before = scoped_queryset.filter(source=CriteriaSource.PIPELINE).count()

        run = ImportRun.objects.create(user=user)

        criteria_type = self._get_criteria_type()
        model_has_side_field = self._model_has_side_field()

        new_instances: list[T] = []
        matched_instances: list[T] = []
        processed_keys: set[str] = set()
        top_level_instances: list[T] = []
        pending_parent_refs: list[tuple[T, bool, list[str], list[str]]] = []

        def build(nodes, parent: T | None, root: T | None):
            for node in nodes:
                extra_kwargs = {Fields.SIDE: node.get(InputFields.SIDE)} if model_has_side_field else {}
                node_name = node.get(InputFields.NAME_PUBLIC)
                key = node[InputFields.ID]
                matched_criteria = existing_by_key.get(key)
                if matched_criteria is None:
                    matched_criteria = legacy_by_name.pop(node_name.lower(), None)
                    if matched_criteria is not None:
                        matched_criteria.wikidata_id = key

                if matched_criteria is not None and model_has_manual_edit_fields and matched_criteria.is_excluded:
                    # Admin-excluded: keep it (and its subtree) out of this import entirely.
                    continue

                processed_keys.add(key)
                primary_refs, secondary_refs = self._node_parent_refs(node, allows_multiple_primary_parents)
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
                        criteria.last_seen_run = run
                    matched_instances.append(criteria)
                else:
                    criteria = self.model(
                        user=user,
                        type=criteria_type,
                        parent=parent,
                        wikidata_id=key,
                        allows_multiple_primary_parents=allows_multiple_primary_parents,
                        **extra_kwargs,
                    )
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
                    criteria.source = CriteriaSource.PIPELINE
                    criteria.last_seen_run = run
                    new_instances.append(criteria)

                if hasattr(criteria, "_validate_side"):
                    criteria._validate_side()

                if parent is None:
                    top_level_instances.append(criteria)
                if not is_locked:
                    pending_parent_refs.append((criteria, parent is None, primary_refs, secondary_refs))

                children = node.get(InputFields.CHILDREN) or []
                if children:
                    # A locked row's own root wasn't touched above (it may not even match
                    # this branch's tree-walk root, if an admin moved it elsewhere) -- recurse
                    # using its real current root so descendants land under the right tree.
                    child_root = criteria.root if is_locked else (root if root is not None else criteria)
                    build(children, criteria, child_root)

        build(tree_data, None, None)

        stale_queryset = (
            scoped_queryset.filter(source=CriteriaSource.PIPELINE, is_manually_edited=False)
            .exclude(pk__in=[c.pk for c in matched_instances if c.last_seen_run_id == run.pk])
            .exclude(wikidata_id__in=protected_keys)
        )
        deleted_count = stale_queryset.count()

        if pipeline_count_before > 0 and not force:
            fraction = deleted_count / pipeline_count_before
            if fraction > settings.CRITERIA_TREE_IMPORT_STALE_DELETE_MAX_FRACTION:
                raise AppValidationException(
                    field_name=TreeImportFields.TREE,
                    message=_(
                        "This import would delete %(fraction)d%% of existing pipeline genres; pass force=true "
                        "to proceed"
                    )
                    % {"fraction": round(fraction * 100)},
                    field_validation_error_code=FieldValidationErrorCode.DEFAULT,
                )

        # Matched rows first, so an existing row keeps its name over a newly imported namesake.
        renamed_instances = [
            c for c in matched_instances if not (model_has_manual_edit_fields and c.is_manually_edited)
        ] + new_instances
        self._disambiguate_conflicting_names(
            user, renamed_instances, excluded_pks=set(stale_queryset.values_list("pk", flat=True))
        )

        if deleted_count:
            self._delete_stale_instances(stale_queryset, actor=actor)

        matched_update_fields = [Fields.NAME_INTERNAL, Fields.PARENT, Fields.ROOT, "last_seen_run", "wikidata_id"]
        if model_has_side_field:
            matched_update_fields.append(Fields.SIDE)
        if self._model_has_name_conflict_field():
            matched_update_fields.append("has_name_conflict")

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
            self._raise_for_known_constraint(e)

        self._finish_import(user, new_instances, top_level_instances, pending_parent_refs, actor=actor)

        actual_seen_count = self.filter(user=user, wikidata_id__in=processed_keys).count()
        if actual_seen_count != len(processed_keys):
            raise AppValidationException(
                field_name=TreeImportFields.TREE,
                message=_("Post-apply state does not match the imported payload"),
                field_validation_error_code=FieldValidationErrorCode.DEFAULT,
            )

        run.finished_at = timezone.now()
        run.status = ImportRun.Status.SUCCEEDED
        run.created_count = len(new_instances)
        run.updated_count = len(
            [c for c in matched_instances if not (model_has_manual_edit_fields and c.is_manually_edited)]
        )
        run.deleted_count = deleted_count
        run.save(update_fields=["finished_at", "status", "created_count", "updated_count", "deleted_count"])

        return {
            "created_count": run.created_count,
            "updated_count": run.updated_count,
            "deleted_count": run.deleted_count,
        }

    def _finish_import(
        self,
        user: Any,
        new_instances: list[T],
        top_level_instances: list[T],
        pending_parent_refs: list[tuple[T, bool, list[str], list[str]]],
        actor: Any,
    ) -> None:
        self._link_imported_parent_refs(user, pending_parent_refs)

        self._refresh_ascendants_of_instance_and_children(*top_level_instances)

        # Top-level nodes may have been attached under other rows (possibly new ones) above:
        # re-sync the in-memory roots and put parents first, as `_on_bulk_created` expects.
        root_id_by_pk = dict(self.filter(pk__in=[c.pk for c in new_instances]).values_list("pk", "root_id"))
        new_by_pk = {criteria.pk: criteria for criteria in new_instances}
        for criteria in new_instances:
            criteria.root_id = root_id_by_pk[criteria.pk]

        def depth(criteria: T) -> int:
            count = 0
            while criteria.parent_id in new_by_pk:
                criteria = new_by_pk[criteria.parent_id]
                count += 1
            return count

        new_instances.sort(key=depth)
        self._on_bulk_created(new_instances, actor=actor)

    def _link_imported_parent_refs(self, user: Any, pending: list[tuple[T, bool, list[str], list[str]]]) -> None:
        """Replaces the additional primary/secondary parents of the imported (unlocked) rows."""
        if not pending:
            return
        pending_pks = [criteria.pk for criteria, *_ in pending]
        for field_name in (Fields.ADDITIONAL_PRIMARY_PARENTS, Fields.SECONDARY_PARENTS):
            field = self.model._meta.get_field(field_name)
            field.remote_field.through.objects.filter(**{f"{field.m2m_field_name()}__in": pending_pks}).delete()

        by_name: dict[str, T] = {}
        by_wikidata_id: dict[str, T] = {}
        for criteria in self.filter(user=user):
            by_name[criteria.name] = criteria
            if getattr(criteria, Fields.WIKIDATA_ID, None):
                by_wikidata_id[criteria.wikidata_id] = criteria

        def resolve(ref: str) -> T:
            found = by_wikidata_id.get(ref) or by_name.get(ref)
            if found is None:
                raise AppValidationException(
                    field_name=TreeImportFields.TREE,
                    message=_("Unknown parent reference: %(ref)s") % {"ref": ref},
                    field_validation_error_code=FieldValidationErrorCode.REFERENCE_INVALID,
                )
            return found

        for criteria, is_top_level, primary_refs, secondary_refs in pending:
            if not primary_refs and not secondary_refs:
                continue
            primary = [resolve(ref) for ref in primary_refs]
            if is_top_level and primary:
                main_parent, *primary = primary
                main_parent.refresh_from_db(fields=[Fields.ROOT])
                criteria.parent = main_parent
                criteria.root = main_parent.root
                if hasattr(criteria, "_validate_side"):
                    criteria._validate_side()
                criteria.save(update_fields=[Fields.PARENT, Fields.ROOT])
                self.update_children_root(criteria, criteria.root)
            criteria.additional_primary_parents.add(*primary)
            criteria.secondary_parents.add(*(resolve(ref) for ref in secondary_refs))
            self._validate_parents(criteria)
