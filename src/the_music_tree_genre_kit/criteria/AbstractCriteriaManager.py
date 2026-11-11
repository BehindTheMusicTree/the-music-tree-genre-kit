import uuid
from collections import defaultdict
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar

from django.db import IntegrityError, models, transaction
from django.db.models import QuerySet
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.translation import gettext as _
from the_music_tree_api_kit.exception.validation.app.AppValidationException import AppValidationException
from the_music_tree_api_kit.exception.validation.FieldValidationErrorCode import FieldValidationErrorCode
from the_music_tree_api_kit.public_standard_resource.StandardResourceManager import StandardResourceManager

from the_music_tree_genre_kit.base.bulk_mti import bulk_create_mti
from the_music_tree_genre_kit.base.constraint_violation import constraint_violated
from the_music_tree_genre_kit.serializer.model.criteria.input.Fields import Fields as InputFields
from the_music_tree_genre_kit.serializer.model.criteria.input.tree_import.Fields import Fields as TreeImportFields
from the_music_tree_genre_kit.track.Fields import Fields as TrackFields

from .AbstractCriteria import AbstractCriteria
from .children.genre.CriteriaScene import CriteriaScene
from .CriteriaSide import CriteriaSide
from .CriteriaTreeName import CriteriaTreeName
from .Fields import Fields
from .type.CriteriaType import CriteriaType

T = TypeVar("T", bound=AbstractCriteria)


class AbstractCriteriaManager(StandardResourceManager[T]):
    """
    Owns the pure tree-structure logic for criteria (ascendant refresh, root
    propagation, primary-parent track moves), plus the criteria-playlist
    orchestration around deletion (direct-track transfer to the criteria-less
    playlist) built on the sibling
    AbstractCriteriaPlaylistManager reached via `instance.criteria_playlist`.
    Side effects outside that (playlists, file metadata, etc.) are left to
    subclasses via the `_on_created`/`_on_parent_changed`/`_on_renamed`/
    `_on_tracks_genre_moved`/`_on_before_delete_many` hooks.

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

    def _load_primary_graph(self, user_id: Any) -> tuple[dict[Any, Any], dict[Any, Any], dict[Any, list[Any]]]:
        """One load of the owner's primary-parent graph: `(parent_by_pk, root_by_pk, parents_by_pk)`, where
        `parents_by_pk` lists each row's main parent first, then its additional primary parents."""
        parent_by_pk: dict[Any, Any] = {}
        root_by_pk: dict[Any, Any] = {}
        for pk, parent_id, root_id in self.filter(user_id=user_id).values_list("pk", Fields.PARENT, Fields.ROOT):
            parent_by_pk[pk] = parent_id
            root_by_pk[pk] = root_id
        parents_by_pk: dict[Any, list[Any]] = {
            pk: [parent_id] if parent_id else [] for pk, parent_id in parent_by_pk.items()
        }
        through, child_col, parent_col = self._through_columns(Fields.ADDITIONAL_PRIMARY_PARENTS)
        for child_pk, parent_pk in (
            through.objects.filter(**{f"{child_col}__user_id": user_id})
            .order_by("pk")
            .values_list(child_col, parent_col)
        ):
            parents_by_pk[child_pk].append(parent_pk)
        return parent_by_pk, root_by_pk, parents_by_pk

    def _through_columns(self, field_name: str) -> tuple[type[models.Model], str, str]:
        """The auto-created through model of a self-referential M2M field, with its child and parent FK names."""
        field = self.model._meta.get_field(field_name)
        return field.remote_field.through, field.m2m_field_name(), field.m2m_reverse_field_name()

    def _refresh_ascendants_of_instance_and_children(self, *instances: T) -> None:
        """`_refresh_ascendants_of_instance` for `instances` and every primary descendant, computed
        in memory from one load of the owner's primary-parent graph: one delete and one bulk insert
        instead of per-row queries (a full tree import touches every row)."""
        if not instances:
            return
        user_id = instances[0].user_id
        _parent_by_pk, _root_by_pk, parents_by_pk = self._load_primary_graph(user_id)

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
                Fields.TREE_NAME,
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
        tracks = list(playlist_manager.get_direct_tracks(instance.criteria_playlist).select_related("genre"))

        for ascendant_id in gained_ids:
            playlist_manager._bulk_prepend_track_rels(
                user=instance.user, playlist=new_ascendants[ascendant_id].criteria_playlist, tracks=tracks
            )

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

    def _model_has_field(self, name: str) -> bool:
        return any(field.name == name for field in self.model._meta.get_fields())

    def _disambiguate_conflicting_names(self, user: Any, instances: list[T], excluded_pks: set[Any]) -> None:
        """
        Renames each of `instances` whose name (case-insensitively) is already taken by another
        of the user's criteria -- or by an earlier one of `instances` -- to `"<name> (<wikidata_id>)"`,
        flagging it `has_name_conflict` for admin review instead of failing the whole import on the
        unique-name constraint. `excluded_pks` are rows about to be deleted, whose names are free.
        """
        has_flag = self._model_has_field("has_name_conflict")
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

    def _node_keys(self, nodes: list[dict]) -> set[str]:
        keys: set[str] = set()
        for node in nodes:
            keys.add(node[InputFields.ID])
            keys |= self._node_keys(node.get(InputFields.CHILDREN) or [])
        return keys

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

    def _on_tracks_genre_moved(self, moves: dict[Any, Any], *, actor: Any = None) -> None:
        """
        Hook: react to the tracks of deleted criteria being re-pointed, by `delete_instances`. `moves` maps every
        deleted criteria's pk to the pk of its nearest surviving ancestor along `parent`, or `None` when none
        survives (the tracks become genreless). Runs before the tracks are updated, so they still point at the
        deleted rows and can be counted or listed. No-op by default.
        """

    def _get_direct_tracks(self, instance: T) -> QuerySet:
        """
        Tracks directly attached to `instance`'s own playlist (not via a
        descendant's ascendant-propagated `TrackPlaylistRel` row). Default is
        generic (TrackPlaylistRel-based); override for criteria types whose
        leaf FK propagates rows to ancestor playlists (e.g. Genre).
        """
        playlist_manager = type(instance.criteria_playlist).objects
        return playlist_manager.get_direct_tracks(instance.criteria_playlist)

    def _on_before_delete_many(self, instances: list[T], *, actor: Any = None) -> None:
        """
        Hook: react to `instances` about to be deleted by `delete_instances`. The surviving tree and the tracks and
        playlist rels are already reassigned, the rows themselves are still present. No-op by default.
        """

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

    def delete_instance(self, instance: T, actor: Any = None) -> None:
        """Delete one criteria; see `delete_instances`."""
        self.delete_instances([instance], actor=actor)

    def delete_instances(self, instances: Iterable[T], actor: Any = None) -> None:
        """
        Delete criteria and handle tree relationships, as one set-based operation per owner.

        Each deleted criteria is spliced out of the primary graph: every surviving primary child (main or
        additional) gets the deleted criteria's primary parents in its place, across chains of deleted
        criteria. A child left without a main parent promotes its first additional primary parent, or becomes a
        root criteria when it has none. A deleted criteria's tracks move to its nearest surviving ancestor along
        `parent` (or become genreless), and leave the playlists of the ancestors they no longer reach. The
        number of queries depends on the number of criteria, never on the number of tracks.

        Non-tree side effects are left to `_on_tracks_genre_moved` and `_on_before_delete_many`.
        """
        by_user: dict[Any, dict[Any, T]] = defaultdict(dict)
        for instance in instances:
            by_user[instance.user_id][instance.pk] = instance
        with transaction.atomic():
            for user_id, stale_by_pk in by_user.items():
                self._delete_user_instances(user_id, stale_by_pk, actor=actor)

    def _delete_user_instances(self, user_id: Any, stale_by_pk: dict[Any, T], actor: Any = None) -> None:
        stale = set(stale_by_pk)
        parent_by_pk, root_by_pk, parents_by_pk = self._load_primary_graph(user_id)

        new_parents = self._splice_stale_out(stale, parents_by_pk)
        self._write_spliced_tree(stale, parent_by_pk, root_by_pk, new_parents)

        playlist_model = self.model._meta.get_field("criteria_playlist").related_model
        playlist_manager = playlist_model.objects
        track_model = playlist_manager.track_model
        # `genre` lives on the shared base table: updating through a concrete child would first select every id.
        base_track_model = track_model._meta.get_field(TrackFields.GENRE).model

        target_by_stale: dict[Any, Any] = {}
        stale_root_by_stale: dict[Any, Any] = {}
        for pk in stale:
            current = pk
            while True:
                parent_pk = parent_by_pk[current]
                if parent_pk is None:
                    target_by_stale[pk], stale_root_by_stale[pk] = None, current
                    break
                if parent_pk not in stale:
                    target_by_stale[pk], stale_root_by_stale[pk] = parent_pk, None
                    break
                current = parent_pk

        tagged = set(
            base_track_model._base_manager.filter(genre__in=stale)
            .order_by()
            .values_list(TrackFields.GENRE, flat=True)
            .distinct()
        )

        ascendants_cache: dict[Any, set[Any]] = {}

        def ascendants_of(pk: Any) -> set[Any]:
            if pk not in ascendants_cache:
                found: set[Any] = set()
                frontier = [pk]
                while frontier:
                    frontier = [p for node in frontier for p in parents_by_pk[node] if p not in found]
                    found.update(frontier)
                ascendants_cache[pk] = found
            return ascendants_cache[pk]

        # Tracks moved to the target keep only the playlists of the target and its ascendants.
        stales_by_lost: dict[Any, list[Any]] = defaultdict(list)
        for pk in tagged:
            target = target_by_stale[pk]
            kept = {target, *ascendants_of(target)} if target else set()
            for lost_pk in ascendants_of(pk) - stale - kept:
                stales_by_lost[lost_pk].append(pk)
        if stales_by_lost:
            rel_model = playlist_manager.track_playlist_rel_model
            for playlist in playlist_model.objects.filter(criteria_id__in=list(stales_by_lost)).select_related("user"):
                removed = rel_model.objects.filter(
                    playlist=playlist, track__genre__in=stales_by_lost[playlist.criteria_id]
                ).delete()[0]
                if removed:
                    rel_model.objects.update_positions_to_fill_deleted_ones(playlist)

        for root_pk in {pk for pk in stale_root_by_stale.values() if pk is not None}:
            root = stale_by_pk[root_pk]
            moved_pks = [pk for pk, stale_root in stale_root_by_stale.items() if stale_root == root_pk]
            playlist_manager.transfer_direct_tracks_to_criterialess_playlist(
                direct_tracks=track_model.objects.filter(
                    models.Q(genre__in=moved_pks) | models.Q(pk__in=self._get_direct_tracks(root))
                ),
                criteria_playlist=root.criteria_playlist,
            )

        self._on_tracks_genre_moved(target_by_stale, actor=actor)
        pks_by_target: dict[Any, list[Any]] = defaultdict(list)
        for pk in tagged:
            pks_by_target[target_by_stale[pk]].append(pk)
        for target, pks in pks_by_target.items():
            base_track_model._base_manager.filter(genre__in=pks).update(genre_id=target, updated_on=Now())

        # Model-level tree state is updated before this hook runs: subclass hooks (e.g. playlist maintenance)
        # may re-derive fields from the criteria's current parent/root, so they need the post-reassignment state.
        self._on_before_delete_many(list(stale_by_pk.values()), actor=actor)

        self.filter(pk__in=stale).delete()

    @staticmethod
    def _splice_stale_out(stale: set[Any], parents_by_pk: dict[Any, list[Any]]) -> dict[Any, list[Any]]:
        """New primary parents (main first) of every surviving row that had a deleted primary parent."""
        replacement: dict[Any, list[Any]] = {}

        def surviving_parents_of(pk: Any) -> list[Any]:
            if pk not in replacement:
                replacement[pk] = list(dict.fromkeys(expand(parents_by_pk[pk])))
            return replacement[pk]

        def expand(parent_pks: list[Any]) -> Iterator[Any]:
            for parent_pk in parent_pks:
                if parent_pk in stale:
                    yield from surviving_parents_of(parent_pk)
                else:
                    yield parent_pk

        return {
            pk: list(dict.fromkeys(expand(parent_pks)))
            for pk, parent_pks in parents_by_pk.items()
            if pk not in stale and not stale.isdisjoint(parent_pks)
        }

    def _write_spliced_tree(
        self,
        stale: set[Any],
        parent_by_pk: dict[Any, Any],
        root_by_pk: dict[Any, Any],
        new_parents: dict[Any, list[Any]],
    ) -> None:
        """Persist `new_parents`: parent/root columns, additional primary parents, secondary parents and lineage."""
        if not new_parents:
            return
        new_parent_by_pk = {
            pk: (new_parents[pk][0] if new_parents[pk] else None) if pk in new_parents else parent
            for pk, parent in parent_by_pk.items()
            if pk not in stale
        }
        new_root_by_pk: dict[Any, Any] = {}
        for start in new_parent_by_pk:
            path, current = [], start
            while current not in new_root_by_pk:
                parent_pk = new_parent_by_pk[current]
                if parent_pk is None:
                    new_root_by_pk[current] = current
                    break
                path.append(current)
                current = parent_pk
            for node in path:
                new_root_by_pk[node] = new_root_by_pk[current]

        changed = {
            pk
            for pk in new_parent_by_pk
            if new_parent_by_pk[pk] != parent_by_pk[pk] or new_root_by_pk[pk] != root_by_pk[pk]
        }
        rows = list(self.filter(pk__in=changed | new_parents.keys()))
        now = timezone.now()
        for row in rows:
            row.parent_id, row.root_id, row.updated_on = new_parent_by_pk[row.pk], new_root_by_pk[row.pk], now
        self.bulk_update(
            [row for row in rows if row.pk in changed], [Fields.PARENT, Fields.ROOT, Fields.UPDATED_ON], batch_size=500
        )

        through, child_col, parent_col = self._through_columns(Fields.ADDITIONAL_PRIMARY_PARENTS)
        child_attname = through._meta.get_field(child_col).attname
        parent_attname = through._meta.get_field(parent_col).attname
        through.objects.filter(**{f"{child_col}__in": list(new_parents)}).delete()
        through.objects.bulk_create(
            [
                through(**{child_attname: pk, parent_attname: parent_pk})
                for pk, parent_pks in new_parents.items()
                for parent_pk in parent_pks[1:]
            ],
            batch_size=1000,
        )

        secondary_through, secondary_child_col, secondary_parent_col = self._through_columns(Fields.SECONDARY_PARENTS)
        redundant = [
            pk
            for pk, child_pk, parent_pk in secondary_through.objects.filter(
                **{f"{secondary_child_col}__in": list(new_parents)}
            ).values_list(
                "pk",
                secondary_through._meta.get_field(secondary_child_col).attname,
                secondary_through._meta.get_field(secondary_parent_col).attname,
            )
            if parent_pk in new_parents[child_pk]
        ]
        secondary_through.objects.filter(pk__in=redundant).delete()

        self._refresh_ascendants_of_instance_and_children(*(row for row in rows if row.pk in new_parents))

    def _delete_stale_instances(self, queryset: QuerySet[T], actor: Any = None) -> None:
        """
        Delete instances dropped from an imported tree through `delete_instances`, not a raw bulk `.delete()`:
        `Track.genre` is `on_delete=DO_NOTHING`, so a track still pointing at a deleted row would raise an
        unhandled `IntegrityError`. The tracks end up on the nearest surviving ancestor, or on the criteria-less
        playlist once a stale root is reached, exactly as repeated one-off deletes would leave them.
        """
        self.delete_instances(list(queryset), actor=actor)

    def get_roots(self, user: Any) -> QuerySet[T]:
        return self.filter(user=user, parent__isnull=True)

    def update_children_root(self, criteria: T, new_root: T):
        children = criteria.children.all()
        if children.exists():
            children.update(root=new_root)
            for child in children:
                self.update_children_root(child, new_root)

    def build_criteria_tree(self, user: Any, *, tree_name: str) -> list[dict]:
        """
        Builds a tree structure of the user's criteria in the given `tree_name`. Nesting follows `parent`; a node whose
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
            self.filter(user=user, tree_name=tree_name).prefetch_related(
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

        `data["tree_name"]` is required: the import only matches, stamps and stale-deletes
        rows of that tree, so the two trees import independently (canonical first, since
        the regional one, which allows multiple primary parents, references it). Node
        `primary_parents`/`secondary_parents` are refs (wikidata id, else name) to any of the
        user's rows, resolved after all rows exist; a top-level node's first primary ref
        becomes its `parent`. `data["cross_tree_secondary_parents"]` (optional) lists rows of the other tree, as
        `{"id": ref, "secondary_parents": [refs]}`, with their secondary parents in this one, see `_link_cross_tree_secondary_parents`.

        A node whose name is already taken (case-insensitively) by another of the user's
        criteria is imported as `"<name> (<id>)"` with `has_name_conflict=True` instead of
        failing the run -- see `_disambiguate_conflicting_names`.

        A node whose key is held only by an unlocked pipeline row of the other tree moved between the
        trees: that row is moved into this tree rather than duplicated, so it keeps its pk and name.

        Returns `{"created_count", "updated_count", "deleted_count", "dry_run"}`.
        """
        empty_result = {"created_count": 0, "updated_count": 0, "deleted_count": 0, "dry_run": dry_run}
        if not data:
            return empty_result

        tree_name: str = data[TreeImportFields.TREE_NAME]
        tree_data = data[TreeImportFields.TREE]

        model_has_wikidata_id_field = self._model_has_wikidata_id_field()
        model_has_manual_edit_fields = self._model_has_manual_edit_fields()

        if not model_has_wikidata_id_field:
            self._delete_stale_instances(self.filter(user=user, tree_name=tree_name), actor=actor)
            result = self._import_tree_without_keys(
                user=user,
                tree_data=tree_data,
                actor=actor,
                tree_name=tree_name,
            )
        else:
            result = self._import_tree_with_keys(
                user=user,
                tree_data=tree_data,
                actor=actor,
                force=force,
                model_has_manual_edit_fields=model_has_manual_edit_fields,
                tree_name=tree_name,
            )

        cross_tree_secondary_parents = data.get(TreeImportFields.CROSS_TREE_SECONDARY_PARENTS) or []
        if cross_tree_secondary_parents:
            self._link_cross_tree_secondary_parents(user, tree_name, cross_tree_secondary_parents)

        result["dry_run"] = dry_run
        if dry_run:
            transaction.set_rollback(True)
        return result

    def _link_cross_tree_secondary_parents(self, user: Any, tree_name: str, links: list[dict]) -> None:
        """Replaces, for each row of another tree listed in `links`, its secondary parents in `tree_name` by the listed
        refs. Its own tree's import cannot set them when it runs first, as these rows may not exist yet. That import
        replaces all its rows' secondary parents, so this tree's import must follow it. Locked or excluded rows are
        left untouched, as in their own tree's import. A list rather than a ref-keyed map, as request middleware
        rewrites nested keys to snake case."""

        def index(queryset) -> tuple[dict[str, T], dict[str, T]]:
            by_wikidata_id: dict[str, T] = {}
            by_name: dict[str, T] = {}
            for criteria in queryset:
                by_name[criteria.name] = criteria
                if getattr(criteria, Fields.WIKIDATA_ID, None):
                    by_wikidata_id[criteria.wikidata_id] = criteria
            return by_wikidata_id, by_name

        def resolve(by_ref: tuple[dict[str, T], dict[str, T]], ref: str) -> T:
            by_wikidata_id, by_name = by_ref
            found = by_wikidata_id.get(ref) or by_name.get(ref)
            if found is None:
                raise AppValidationException(
                    field_name=TreeImportFields.CROSS_TREE_SECONDARY_PARENTS,
                    message=_("Unknown cross-tree reference: %(ref)s") % {"ref": ref},
                    field_validation_error_code=FieldValidationErrorCode.REFERENCE_INVALID,
                )
            return found

        children_by_ref = index(self.filter(user=user).exclude(tree_name=tree_name))
        parents_by_ref = index(self.filter(user=user, tree_name=tree_name))
        field = self.model._meta.get_field(Fields.SECONDARY_PARENTS)
        child_col, parent_col = field.m2m_field_name(), field.m2m_reverse_field_name()
        has_manual_edit_fields = self._model_has_manual_edit_fields()
        for link in links:
            child = resolve(children_by_ref, link[InputFields.ID])
            parents = [resolve(parents_by_ref, ref) for ref in link[InputFields.SECONDARY_PARENTS]]
            if has_manual_edit_fields and (child.is_manually_edited or child.is_excluded):
                continue
            field.remote_field.through.objects.filter(
                **{child_col: child.pk, f"{parent_col}__tree_name": tree_name}
            ).delete()
            child.secondary_parents.add(*parents)
            self._validate_parents(child)

    def _node_parent_refs(self, node: dict, tree_name: str) -> tuple[list[str], list[str]]:
        primary_refs = node.get(InputFields.PRIMARY_PARENTS) or []
        if primary_refs and tree_name != CriteriaTreeName.REGIONAL:
            raise AppValidationException(
                field_name=TreeImportFields.PRIMARY_PARENTS,
                message=_("Only a tree allowing multiple primary parents can list primary parents"),
                field_validation_error_code=FieldValidationErrorCode.DEPENDENCY_MISSING,
            )
        return primary_refs, node.get(InputFields.SECONDARY_PARENTS) or []

    def _import_tree_without_keys(self, user: Any, tree_data: list, actor: Any, tree_name: str) -> dict[str, Any]:
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
                primary_refs, secondary_refs = self._node_parent_refs(node, tree_name)
                extra_kwargs = {Fields.SIDE: node.get(InputFields.SIDE)} if model_has_side_field else {}
                criteria = self.model(
                    user=user,
                    type=criteria_type,
                    parent=parent,
                    tree_name=tree_name,
                    **extra_kwargs,
                )
                pk = uuid.uuid4()
                criteria.uuid = pk
                criteria.pk = pk
                criteria._name = node.get(InputFields.NAME_PUBLIC)
                criteria.root = root if root is not None else criteria
                new_instances.append(criteria)
                if hasattr(criteria, "_validate_side_placement"):
                    criteria._validate_side_placement()
                if parent is None:
                    top_level_instances.append(criteria)
                pending_parent_refs.append((criteria, parent is None, primary_refs, secondary_refs))
                build(node.get(InputFields.CHILDREN) or [], criteria, root if root is not None else criteria)

        build(tree_data, None, None)
        self._validate_scene_split(tree_data)
        self._validate_single_pop_child_per_root(new_instances)
        try:
            bulk_create_mti(new_instances, using=self.db)
        except IntegrityError as e:
            self._raise_for_known_constraint(e)
        self._finish_import(user, new_instances, top_level_instances, pending_parent_refs, actor=actor)
        return {"created_count": len(new_instances), "updated_count": 0, "deleted_count": 0}

    def _validate_scene_split(self, tree_data: list[dict]) -> None:
        """A node with a scene child holds exactly two children: one commercial and one underground.

        Walks the imported tree itself rather than the planned instances: parents are only resolved
        afterwards, and a locked row keeps its stored parent whatever the tree says.
        """
        if not self._model_has_field(Fields.SCENE):
            return

        def check(nodes: list[dict], parent_name: str) -> None:
            scenes = [node.get(InputFields.SCENE) for node in nodes]
            if any(scenes) and sorted(scene or "" for scene in scenes) != [
                CriteriaScene.COMMERCIAL,
                CriteriaScene.UNDERGROUND,
            ]:
                names = ", ".join(str(node.get(InputFields.NAME_PUBLIC)) for node in nodes)
                raise self.model.scene_split_exception(parent_name, names)  # type: ignore[attr-defined]
            for node in nodes:
                check(node.get(InputFields.CHILDREN) or [], str(node.get(InputFields.NAME_PUBLIC)))

        check(tree_data, "the tree root")

    def _validate_single_pop_child_per_root(self, planned_instances: list[T]) -> None:
        if not self._model_has_side_field():
            return
        roots_with_pop_child: set[Any] = set()
        for criteria in planned_instances:
            if getattr(criteria, Fields.SIDE) != CriteriaSide.POP:
                continue
            if criteria.root_id in roots_with_pop_child:
                raise self.model.second_pop_child_exception()  # type: ignore[attr-defined]
            roots_with_pop_child.add(criteria.root_id)

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
        tree_name: str,
    ) -> dict[str, Any]:
        from django.conf import settings

        from .children.genre.CriteriaSource import CriteriaSource
        from .import_run.ImportRun import ImportRun

        self._require_node_keys(tree_data)

        scoped_queryset = self.filter(user=user, tree_name=tree_name)
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
        # A key held by an unlocked pipeline row of the other tree moved between trees: that row is adopted, keeping
        # its pk (and what references it) and freeing its name, which a namesake created here would otherwise have
        # to suffix until the other tree's next import deletes the old row.
        movable_candidates = list(
            self.filter(
                user=user,
                wikidata_id__in=self._node_keys(tree_data) - existing_by_key.keys(),
                source=CriteriaSource.PIPELINE,
                is_manually_edited=False,
                is_excluded=False,
            ).exclude(tree_name=tree_name)
        )
        # Locked descendants are skipped by their tree's imports, so only the old row's delete (which splices them
        # onto its parents and re-roots them) can repair their parent/root: such a row is left to that path.
        candidate_pks = [criteria.pk for criteria in movable_candidates]
        locked_pks = self.filter(user=user, is_manually_edited=True).values("pk")
        ancestors_of_locked = set(
            self.lineage_rel_model.objects.filter(
                ascendant_id__in=candidate_pks, descendant_id__in=locked_pks
            ).values_list("ascendant_id", flat=True)
        ) | set(self.filter(root_id__in=candidate_pks, pk__in=locked_pks).values_list(Fields.ROOT, flat=True))
        movable_by_key: dict[str, T] = {
            criteria.wikidata_id: criteria for criteria in movable_candidates if criteria.pk not in ancestors_of_locked
        }
        protected_keys: set[str] = set()
        if model_has_manual_edit_fields:
            protected_keys = {key for key, criteria in existing_by_key.items() if criteria.is_excluded}

        pipeline_count_before = scoped_queryset.filter(source=CriteriaSource.PIPELINE).count()

        run = ImportRun.objects.create(user=user)

        criteria_type = self._get_criteria_type()
        model_has_side_field = self._model_has_side_field()
        model_has_unaccepted_root_field = self._model_has_field(Fields.IS_UNACCEPTED_ROOT)
        model_has_umbrella_field = self._model_has_field(Fields.IS_UMBRELLA)
        model_has_scene_field = self._model_has_field(Fields.SCENE)
        model_has_description_fields = self._model_has_field(Fields.DESCRIPTION)

        locked_umbrella_by_pk: dict[Any, bool] = {}
        locked_scene_by_pk: dict[Any, str | None] = {}
        new_instances: list[T] = []
        matched_instances: list[T] = []
        processed_keys: set[str] = set()
        top_level_instances: list[T] = []
        pending_parent_refs: list[tuple[T, bool, list[str], list[str]]] = []

        def build(nodes, parent: T | None, root: T | None):
            for node in nodes:
                extra_kwargs = {Fields.SIDE: node.get(InputFields.SIDE)} if model_has_side_field else {}
                if model_has_unaccepted_root_field:
                    extra_kwargs[Fields.IS_UNACCEPTED_ROOT] = bool(node.get(InputFields.IS_UNACCEPTED_ROOT))
                if model_has_umbrella_field:
                    extra_kwargs[Fields.IS_UMBRELLA] = bool(node.get(InputFields.IS_UMBRELLA))
                if model_has_scene_field:
                    extra_kwargs[Fields.SCENE] = node.get(InputFields.SCENE)
                if model_has_description_fields:
                    for field_name in (Fields.SUMMARY, Fields.DESCRIPTION, Fields.SUMMARY_SOURCE_URL):
                        extra_kwargs[field_name] = node.get(field_name) or None
                node_name = node.get(InputFields.NAME_PUBLIC)
                key = node[InputFields.ID]
                matched_criteria = existing_by_key.get(key)
                if matched_criteria is None:
                    matched_criteria = legacy_by_name.pop(node_name.lower(), None)
                    if matched_criteria is not None:
                        matched_criteria.wikidata_id = key
                if matched_criteria is None:
                    matched_criteria = movable_by_key.pop(key, None)
                    if matched_criteria is not None:
                        matched_criteria.tree_name = tree_name

                if matched_criteria is not None and model_has_manual_edit_fields and matched_criteria.is_excluded:
                    # Admin-excluded: keep it (and its subtree) out of this import entirely.
                    continue

                processed_keys.add(key)
                primary_refs, secondary_refs = self._node_parent_refs(node, tree_name)
                is_locked = False
                if matched_criteria is not None:
                    criteria: T = matched_criteria
                    is_locked = model_has_manual_edit_fields and criteria.is_manually_edited
                    if is_locked and model_has_umbrella_field:
                        locked_umbrella_by_pk[criteria.pk] = extra_kwargs[Fields.IS_UMBRELLA]
                    if is_locked and model_has_scene_field:
                        locked_scene_by_pk[criteria.pk] = extra_kwargs[Fields.SCENE]
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
                        tree_name=tree_name,
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

                if hasattr(criteria, "_validate_side_placement"):
                    criteria._validate_side_placement()

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
        self._validate_scene_split(tree_data)
        self._validate_single_pop_child_per_root(matched_instances + new_instances)

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

        matched_update_fields = [
            Fields.NAME_INTERNAL,
            Fields.PARENT,
            Fields.ROOT,
            Fields.TREE_NAME,
            "last_seen_run",
            "wikidata_id",
        ]
        if model_has_side_field:
            matched_update_fields.append(Fields.SIDE)
        if self._model_has_field("has_name_conflict"):
            matched_update_fields.append("has_name_conflict")
        if model_has_unaccepted_root_field:
            matched_update_fields.append(Fields.IS_UNACCEPTED_ROOT)
        if model_has_umbrella_field:
            matched_update_fields.append(Fields.IS_UMBRELLA)
        if model_has_scene_field:
            matched_update_fields.append(Fields.SCENE)
        if model_has_description_fields:
            matched_update_fields.extend([Fields.SUMMARY, Fields.DESCRIPTION, Fields.SUMMARY_SOURCE_URL])

        try:
            bulk_create_mti(new_instances, using=self.db)
            # Pop rows last: a pop child moving to core must be saved before its successor's
            # save-time uniqueness check sees the DB.
            for criteria in sorted(matched_instances, key=lambda c: getattr(c, Fields.SIDE, None) == CriteriaSide.POP):
                if model_has_manual_edit_fields and criteria.is_manually_edited:
                    continue  # locked: nothing was mutated above, nothing to persist
                criteria.save(update_fields=matched_update_fields)
            # is_umbrella mirrors the curation list, not an admin edit, so a locked row still follows it.
            for is_umbrella in (True, False):
                locked_pks = [pk for pk, value in locked_umbrella_by_pk.items() if value is is_umbrella]
                if locked_pks:
                    self.filter(pk__in=locked_pks).update(is_umbrella=is_umbrella)
            # Same for scene: it mirrors the curation list, so a locked row follows it too.
            for scene in set(locked_scene_by_pk.values()):
                locked_pks = [pk for pk, value in locked_scene_by_pk.items() if value == scene]
                self.filter(pk__in=locked_pks).update(scene=scene)
        except IntegrityError as e:
            self._raise_for_known_constraint(e)

        self._finish_import(user, new_instances, top_level_instances, pending_parent_refs, actor=actor)

        actual_seen_count = scoped_queryset.filter(wikidata_id__in=processed_keys).count()
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
