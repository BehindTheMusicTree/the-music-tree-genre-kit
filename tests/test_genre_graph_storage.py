import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from the_music_tree_genre_graph import GenreGraph, GraphValidationError

from the_music_tree_genre_kit.genre_graph import publication, storage
from the_music_tree_genre_kit.genre_graph.assignments import assignment_snapshot, register_evidence
from the_music_tree_genre_kit.genre_graph.models import (
    GenreGraphAccess,
    GenreGraphAssignmentState,
    GenreGraphAttribution,
    GenreGraphAttributionEvidence,
    GenreGraphAttributionRevision,
    GenreGraphDataset,
    GenreGraphEvidence,
    GenreGraphNode,
    GenreGraphRevision,
    GraphScope,
)
from the_music_tree_genre_kit.genre_graph.publication import publish_staged_attributions
from the_music_tree_genre_kit.genre_graph.storage import (
    GraphRevisionConflict,
    effective_attributions,
    graph_write_transaction,
    replace_graph,
    replace_track_attributions,
    restore_graph,
    restore_track_attributions,
    select_tracks,
    tracks_needing_refinement,
)
from the_music_tree_genre_kit.track.Track import Track

pytestmark = pytest.mark.django_db


@pytest.fixture
def payload():
    return json.loads((Path(__file__).parent / "fixtures/genre_graph/regional-v2.json").read_text())


@pytest.fixture
def dataset(payload):
    return replace_graph(key="reference", payload=payload, expected_revision=None)


def ref(name):
    return f"LOCAL:{name}"


def provenance(name):
    return {"decisionId": name, "source": "synthetic fixture", "rationale": "Controlled explicit attribution"}


def assignment_revision(dataset, song):
    return (
        GenreGraphAssignmentState.objects.filter(dataset=dataset, track=song).values_list("revision", flat=True).first()
    )


def assign(dataset, track, *identities):
    replace_track_attributions(
        key=dataset.key,
        track_id=track.pk,
        attributions={ref(identity): [provenance(identity)] for identity in identities},
        expected_revision=dataset.revision,
        expected_assignment_revision=assignment_revision(dataset, track),
    )


def tracks(*names):
    instances = [Track(title=name) for name in names]
    Track.objects.bulk_create(instances)
    return instances


def node_of(key, identity):
    return GenreGraphNode.objects.get(dataset_id=key, identity=ref(identity))


def selected(identity, scope="all"):
    return set(
        select_tracks(Track.objects.all(), node=node_of("reference", identity), scope=scope).values_list(
            "title", flat=True
        )
    )


def test_e03_idempotent_import_preserves_node_keys_and_assignments(dataset, payload):
    original = dict(dataset.nodes.values_list("identity", "pk"))
    (song,) = tracks("French dub")
    assign(dataset, song, "french-dub")
    repeated = replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    assert repeated.revision == dataset.revision
    assert dict(repeated.nodes.values_list("identity", "pk")) == original
    assert GenreGraphRevision.objects.count() == 1
    assert selected("dub") == {"French dub"}


def test_e03_bulk_write_context_rejects_stale_graph_revision(dataset, payload):
    changed = deepcopy(payload)
    changed["nodes"][0]["name"] = "Renamed"
    replace_graph(key=dataset.key, payload=changed, expected_revision=dataset.revision)
    with (
        pytest.raises(GraphRevisionConflict, match="reload before writing"),
        graph_write_transaction(key=dataset.key, expected_revision=dataset.revision),
    ):
        pytest.fail("A stale bulk writer must fail before mutation")


def test_m01_m03_e09_sql_exact_sets_distinct_counts_and_unclassified_tracks(dataset):
    jamaican, french, british, unknown_region, unclassified = tracks(
        "Jamaican", "French", "British", "Unknown region", "No genre"
    )
    assign(dataset, jamaican, "jamaican-dub")
    assign(dataset, french, "french-dub")
    assign(dataset, british, "british-dub")
    assign(dataset, unknown_region, "dub")
    assert selected("dub", "canonical") == {"Jamaican", "French", "British", "Unknown region"}
    assert selected("france") == {"French"}
    assert selected("jamaica") == {"Jamaican"}
    assert selected("britain") == {"British"}
    assert selected("world") == {"Jamaican", "French", "British"}
    assert select_tracks(Track.objects.all(), node=node_of(dataset.key, "world")).count() == 3
    assert set(Track.objects.values_list("pk", flat=True)) == {
        jamaican.pk,
        french.pk,
        british.pk,
        unknown_region.pk,
        unclassified.pk,
    }


def test_r06_r07_effective_attributions_are_active_and_umbrellas_need_refinement(dataset):
    inherited, independent, direct = tracks("Inherited", "Independent", "Direct")
    assign(dataset, inherited, "breton-rock")
    assign(dataset, independent, "jamaica")
    assign(dataset, direct, "brittany")
    effective = effective_attributions(key=dataset.key)
    assert set(effective.filter(track=inherited).values_list("node__identity", flat=True)) == {ref("breton-rock")}
    assert set(tracks_needing_refinement(Track.objects.all(), key=dataset.key).values_list("title", flat=True)) == {
        "Independent",
        "Direct",
    }
    assert selected("france") == {"Inherited", "Direct"}


def test_e02_invalid_import_leaves_dataset_and_assignments_usable(dataset, payload):
    before = list(GenreGraphAccess.objects.values_list("ancestor_id", "descendant_id"))
    payload["relations"][0]["parentId"] = "LOCAL:missing"
    with pytest.raises(GraphValidationError, match="Missing"):
        replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    dataset.refresh_from_db()
    assert list(GenreGraphAccess.objects.values_list("ancestor_id", "descendant_id")) == before
    assert GenreGraph(dataset.payload).node_ids
    assert GenreGraphRevision.objects.count() == 1


def test_e03_e04_removing_relation_replaces_closure_and_restore_retains_identity(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    original = dict(dataset.nodes.values_list("identity", "pk"))
    changed = deepcopy(payload)
    changed["relations"] = [
        edge
        for edge in changed["relations"]
        if not (edge["childId"] == ref("french-dub") and edge["type"] == "regional_membership")
    ]
    for node in changed["nodes"]:
        if node["id"] == ref("french-dub"):
            node.pop("displayParentId", None)
    updated = replace_graph(key=dataset.key, payload=changed, expected_revision=dataset.revision)
    assert updated.revision != dataset.revision
    assert selected("france") == set()
    assert selected("dub") == {"French"}
    restored = restore_graph(key=dataset.key, revision=dataset.revision, expected_revision=updated.revision)
    assert selected("france") == {"French"}
    assert dict(restored.nodes.values_list("identity", "pk")) == original
    assert GenreGraphRevision.objects.count() == 3


def test_e02_e03_removed_attributed_identity_requires_explicit_mapping(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    payload["nodes"] = [node for node in payload["nodes"] if node["id"] != ref("french-dub")]
    payload["relations"] = [edge for edge in payload["relations"] if edge["childId"] != ref("french-dub")]
    with pytest.raises(GraphValidationError, match="Retirements"):
        replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    dataset.refresh_from_db()
    assert selected("france") == {"French"}
    assert GenreGraphRevision.objects.count() == 1


def test_e03_e04_outer_transaction_rollback_restores_graph_and_assignments(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    original_revision = dataset.revision

    def abort_import():
        with transaction.atomic():
            payload["nodes"][0]["name"] = "Changed"
            updated = replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
            assign(updated, song, "jamaican-dub")
            assert selected("jamaica") == {"French"}
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        abort_import()
    dataset.refresh_from_db()
    assert dataset.revision == original_revision
    assert selected("france") == {"French"}
    assert selected("jamaica") == set()


def test_e02_revision_conflicts_never_overwrite(dataset, payload):
    with pytest.raises(GraphRevisionConflict):
        replace_graph(key=dataset.key, payload=payload, expected_revision=None)
    with pytest.raises(GraphRevisionConflict):
        replace_graph(key="missing", payload=payload, expected_revision=dataset.revision)
    (song,) = tracks("French")
    payload["nodes"][0]["name"] = "Changed"
    replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    with pytest.raises(GraphRevisionConflict):
        assign(dataset, song, "french-dub")
    assert not GenreGraphAttribution.objects.exists()


def test_e02_empty_attribution_is_explicit_and_bad_provenance_rolls_back(dataset):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    with pytest.raises(GraphValidationError, match=r"[Ee]vidence"):
        replace_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            attributions={ref("dub"): [{}]},
            expected_revision=dataset.revision,
            expected_assignment_revision=assignment_revision(dataset, song),
        )
    assert selected("france") == {"French"}
    assign(dataset, song)
    assert not GenreGraphAttribution.objects.exists()
    assert Track.objects.filter(pk=song.pk).exists()


def test_e02_inactive_node_selects_nothing(dataset):
    (song,) = tracks("Dub")
    assign(dataset, song, "dub")
    node = node_of(dataset.key, "dub")
    node.is_active = False
    assert not select_tracks(Track.objects.all(), node=node).exists()
    assert not select_tracks(Track.objects.all(), node=node, include_descendants=False).exists()


def test_e02_invalid_scope_is_rejected(dataset):
    with pytest.raises(GraphValidationError, match="Invalid selection scope"):
        select_tracks(Track.objects.all(), node=node_of(dataset.key, "dub"), scope="bogus")


def test_e02_scope_accepts_enum_and_string(dataset):
    (song,) = tracks("Dub")
    assign(dataset, song, "dub")
    node = node_of(dataset.key, "dub")
    for scope in (GraphScope.CANONICAL, "canonical"):
        assert list(select_tracks(Track.objects.all(), node=node, scope=scope)) == [song]


def test_e02_select_tracks_is_lazy(dataset, django_assert_num_queries):
    node = node_of(dataset.key, "dub")
    with django_assert_num_queries(0):
        queryset = select_tracks(Track.objects.all(), node=node)
    with django_assert_num_queries(1):
        list(queryset)


def test_e04_membership_revision_changes_only_for_committed_changes(dataset, payload):
    (song,) = tracks("French")
    original = dataset.membership_revision
    assign(dataset, song, "french-dub")
    dataset.refresh_from_db()
    assigned = dataset.membership_revision
    assert assigned != original
    assign(dataset, song, "french-dub")
    dataset.refresh_from_db()
    assert dataset.membership_revision == assigned

    def abort_assignment():
        with transaction.atomic():
            assign(dataset, song, "jamaican-dub")
            raise RuntimeError("rollback")

    with pytest.raises(RuntimeError):
        abort_assignment()
    dataset.refresh_from_db()
    assert dataset.membership_revision == assigned
    payload["nodes"][0]["name"] = "Renamed"
    updated = replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    assert updated.membership_revision != assigned


@pytest.mark.parametrize(
    "bad", [None, [], "source", {"decisionId": "x"}, {"decisionId": " ", "source": "x", "rationale": "x"}]
)
def test_e02_invalid_provenance_preserves_attributions_and_revision(dataset, bad):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    dataset.refresh_from_db()
    revision = dataset.membership_revision
    with pytest.raises(GraphValidationError, match=r"[Ee]vidence"):
        replace_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            attributions={ref("dub"): [bad]},
            expected_revision=dataset.revision,
            expected_assignment_revision=assignment_revision(dataset, song),
        )
    dataset.refresh_from_db()
    assert dataset.membership_revision == revision
    assert selected("france") == {"French"}


def test_e02_personal_tracks_cannot_enter_reference_graph(dataset, django_user_model):
    user = django_user_model.objects.create(username="personal")
    song = Track(title="Private", user=user)
    Track.objects.bulk_create([song])
    with pytest.raises(GraphValidationError, match="ownerless"):
        assign(dataset, song, "dub")
    assert not GenreGraphAttribution.objects.exists()


def test_e02_unknown_attribution_rejected_without_graph_revalidation(dataset, monkeypatch):
    (song,) = tracks("French")

    def unexpected_validation(*args, **kwargs):
        pytest.fail("An attribution must not revalidate the full graph")

    monkeypatch.setattr("the_music_tree_genre_kit.genre_graph.storage.GenreGraph", unexpected_validation)
    assign(dataset, song, "french-dub")
    with pytest.raises(GraphValidationError, match="Unknown attribution"):
        assign(dataset, song, "missing")
    assert selected("france") == {"French"}


def test_e07_sql_scopes_and_direct_coverage(dataset):
    parent, expression, exited = tracks("Parent", "Expression", "Exited")
    assign(dataset, parent, "reggae")
    assign(dataset, expression, "french-dub")
    assign(dataset, exited, "french-reggae-child")
    assert selected("reggae", "canonical") == {"Parent", "Expression"}
    assert selected("reggae", "regional") == {"Parent", "Expression", "Exited"}
    assert selected("reggae", "all") == {"Parent", "Expression", "Exited"}
    assert set(select_tracks(Track.objects.all(), node=node_of(dataset.key, "reggae"), include_descendants=False)) == {
        parent
    }
    with pytest.raises(GraphValidationError, match="Invalid selection scope"):
        selected("france", "canonical")


@pytest.mark.parametrize("mutation", ["bulk_create", "update", "bulk_update", "delete", "track_delete"])
def test_e04_database_invalidation_covers_bulk_writes_and_cascades(dataset, mutation):
    (song,) = tracks("French")
    node = dataset.nodes.get(identity=ref("french-dub"))
    if mutation != "bulk_create":
        assign(dataset, song, "french-dub")
    dataset.refresh_from_db()
    before = dataset.membership_revision
    track_pk = song.pk

    def change():
        match mutation:
            case "bulk_create":
                GenreGraphAttribution.objects.bulk_create(
                    [
                        GenreGraphAttribution(
                            track=song,
                            node=node,
                            dataset=dataset,
                        )
                    ]
                )
            case "update":
                GenreGraphAttribution.objects.get(track=song).evidence.add(
                    GenreGraphEvidence.objects.create(
                        dataset=dataset, decision_id="updated", source="fixture", rationale="test"
                    )
                )
            case "bulk_update":
                attribution = GenreGraphAttribution.objects.get(track=song)
                attribution.node = dataset.nodes.get(identity=ref("jamaican-dub"))
                GenreGraphAttribution.objects.bulk_update([attribution], ["node"])
            case "delete":
                GenreGraphAttribution.objects.filter(track=song).delete()
            case "track_delete":
                Track.objects.filter(pk=track_pk).delete()

    def abort_change():
        with transaction.atomic():
            change()
            dataset.refresh_from_db()
            assert dataset.membership_revision != before
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        abort_change()
    dataset.refresh_from_db()
    assert dataset.membership_revision == before
    change()
    dataset.refresh_from_db()
    assert dataset.membership_revision != before


def test_e03_assignment_history_restores_provenance_and_rolls_back_with_mutations(dataset):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    archived = GenreGraphAttributionRevision.objects.get(attributions={ref("french-dub"): [provenance("french-dub")]})
    initial = GenreGraphAttributionRevision.objects.count()

    def abort_change():
        with transaction.atomic():
            assign(dataset, song, "jamaican-dub")
            assert GenreGraphAttributionRevision.objects.count() > initial
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        abort_change()
    assert GenreGraphAttributionRevision.objects.count() == initial
    assign(dataset, song, "jamaican-dub")
    assert selected("jamaica") == {"French"}
    restore_track_attributions(
        key=dataset.key,
        track_id=song.pk,
        revision=archived.revision,
        expected_revision=dataset.revision,
        expected_assignment_revision=assignment_revision(dataset, song),
    )
    assert selected("france") == {"French"}
    assert selected("jamaica") == set()
    assert assignment_snapshot(dataset=dataset, track_id=song.pk) == archived.attributions


def test_e03_assignment_restore_rejects_missing_identity_atomically(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    archived = GenreGraphAttributionRevision.objects.get(attributions={ref("french-dub"): [provenance("french-dub")]})
    assign(dataset, song, "dub")
    payload["nodes"] = [node for node in payload["nodes"] if node["id"] != ref("french-dub")]
    payload["relations"] = [edge for edge in payload["relations"] if edge["childId"] != ref("french-dub")]
    updated = replace_graph(
        key=dataset.key,
        payload=payload,
        expected_revision=dataset.revision,
        retirements={ref("french-dub"): {"target": None, "provenance": provenance("retire-french-dub")}},
    )
    before = GenreGraphAttributionRevision.objects.count()
    with pytest.raises(GraphValidationError, match="Unknown attribution"):
        restore_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            revision=archived.revision,
            expected_revision=updated.revision,
            expected_assignment_revision=assignment_revision(dataset, song),
        )
    assert GenreGraphAttributionRevision.objects.count() == before
    assert selected("dub") == {"French"}


@pytest.mark.parametrize("operation", ["create", "transfer"])
def test_e02_database_rejects_private_track_attributions(dataset, django_user_model, operation):
    user = django_user_model.objects.create(username="personal")
    (song,) = tracks("Reference")
    node = dataset.nodes.get(identity=ref("dub"))
    if operation == "create":
        Track.objects.filter(pk=song.pk).update(user=user)
    else:
        assign(dataset, song, "dub")

    def invalid_change():
        with transaction.atomic():
            if operation == "create":
                GenreGraphAttribution.objects.bulk_create(
                    [
                        GenreGraphAttribution(
                            track=song,
                            node=node,
                            dataset=dataset,
                        )
                    ]
                )
            else:
                Track.objects.filter(pk=song.pk).update(user=user)

    with pytest.raises(IntegrityError, match="ownerless"):
        invalid_change()
    assert GenreGraphAttribution.objects.filter(track=song).exists() == (operation == "transfer")


def test_retirement_and_reactivation_reuse_permanent_node(dataset, payload):
    original = dataset.nodes.get(identity=ref("french-dub"))
    changed = deepcopy(payload)
    changed["nodes"] = [n for n in changed["nodes"] if n["id"] != original.identity]
    changed["relations"] = [r for r in changed["relations"] if r["childId"] != original.identity]
    decisions = {original.identity: {"target": None, "provenance": provenance("retire")}}
    updated = replace_graph(key=dataset.key, payload=changed, expected_revision=dataset.revision, retirements=decisions)
    original.refresh_from_db()
    assert not original.is_active
    assert GenreGraphRevision.objects.get(revision=updated.revision).retirements == decisions
    assert not GenreGraphAccess.objects.filter(ancestor=original).exists()
    restored = restore_graph(key=dataset.key, revision=dataset.revision, expected_revision=updated.revision)
    assert restored.nodes.get(identity=original.identity, is_active=True).pk == original.pk


def test_metadata_change_does_not_rewrite_closure_rows(dataset, payload):
    original = set(GenreGraphAccess.objects.values_list("pk", flat=True))
    payload["nodes"][0]["name"] = "Changed label"
    replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    assert set(GenreGraphAccess.objects.values_list("pk", flat=True)) == original


@pytest.mark.parametrize("endpoint", ["ancestor", "descendant"])
def test_database_rejects_cross_dataset_access(dataset, payload, endpoint):
    other = replace_graph(key="other", payload=payload, expected_revision=None)
    node = dataset.nodes.first()
    kwargs = {"dataset": dataset, "ancestor": node, "descendant": node, "scope": "all"}
    kwargs[endpoint] = other.nodes.first()
    with pytest.raises(IntegrityError), transaction.atomic():
        GenreGraphAccess.objects.create(**kwargs)


@pytest.mark.parametrize("field", ["identity", "dataset_id"])
def test_database_rejects_node_identity_mutation(dataset, payload, field):
    other = replace_graph(key="other", payload=payload, expected_revision=None)
    node = dataset.nodes.first()
    value = "LOCAL:stolen" if field == "identity" else other.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        dataset.nodes.filter(pk=node.pk).update(**{field: value})


def without_nodes(payload, *identities):
    changed = deepcopy(payload)
    removed = {ref(identity) for identity in identities}
    changed["nodes"] = [node for node in changed["nodes"] if node["id"] not in removed]
    changed["relations"] = [
        edge for edge in changed["relations"] if edge["childId"] not in removed and edge["parentId"] not in removed
    ]
    return changed


def test_retirement_merges_all_evidence_and_archives_complete_assignment_sets(dataset, payload):
    song, other = tracks("Shared dub", "Other dub")
    assign(dataset, song, "french-dub")
    assign(dataset, other, "jamaican-dub")
    before = assignment_snapshot(dataset=dataset, track_id=song.pk)
    reviewed = assignment_revision(dataset, song)
    updated = replace_graph(
        key=dataset.key,
        payload=without_nodes(payload, "french-dub", "jamaican-dub"),
        expected_revision=dataset.revision,
        retirements={
            ref(identity): {"target": ref("dub"), "provenance": provenance("retire-" + identity)}
            for identity in ("french-dub", "jamaican-dub")
        },
    )
    after = assignment_snapshot(dataset=updated, track_id=song.pk)
    assert set(after) == {ref("dub")}
    assert {value["decisionId"] for value in after[ref("dub")]} == {"french-dub", "retire-french-dub"}
    assert {value["decisionId"] for value in assignment_snapshot(dataset=updated, track_id=other.pk)[ref("dub")]} == {
        "jamaican-dub",
        "retire-jamaican-dub",
    }
    assert GenreGraphAttributionRevision.objects.get(revision=reviewed).attributions == before
    current = assignment_revision(updated, song)
    assert current != reviewed
    assert GenreGraphAttributionRevision.objects.get(revision=current).attributions == after
    with pytest.raises(GraphRevisionConflict, match="assignments changed"):
        replace_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            attributions={},
            expected_revision=updated.revision,
            expected_assignment_revision=reviewed,
        )


def test_null_retirement_archives_original_and_keeps_decision(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    reviewed = assignment_revision(dataset, song)
    decision = {"target": None, "provenance": provenance("explicit-clear")}
    updated = replace_graph(
        key=dataset.key,
        payload=without_nodes(payload, "french-dub"),
        expected_revision=dataset.revision,
        retirements={ref("french-dub"): decision},
    )
    assert assignment_snapshot(dataset=updated, track_id=song.pk) == {}
    assert GenreGraphAttributionRevision.objects.get(revision=reviewed).attributions == {
        ref("french-dub"): [provenance("french-dub")]
    }
    assert GenreGraphRevision.objects.get(revision=updated.revision).retirements[ref("french-dub")] == decision
    assert GenreGraphAttributionRevision.objects.get(revision=assignment_revision(updated, song)).attributions == {}


def test_assignment_cas_covers_empty_sets_and_sql_evidence_mutations(dataset):
    (song,) = tracks("French")
    assign(dataset, song, "dub")
    reviewed = assignment_revision(dataset, song)
    row = GenreGraphAttribution.objects.get(track=song)
    extra = GenreGraphEvidence.objects.create(dataset=dataset, decision_id="extra", source="test", rationale="test")
    GenreGraphAttributionEvidence.objects.create(attribution=row, evidence=extra)
    assert assignment_revision(dataset, song) != reviewed
    with pytest.raises(GraphRevisionConflict, match="assignments changed"):
        replace_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            attributions={},
            expected_revision=dataset.revision,
            expected_assignment_revision=reviewed,
        )
    assign(dataset, song)
    reviewed = assignment_revision(dataset, song)
    with pytest.raises(GraphRevisionConflict, match="assignments changed"):
        replace_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            attributions={},
            expected_revision=dataset.revision,
            expected_assignment_revision=None,
        )
    assert assignment_revision(dataset, song) == reviewed


def test_conflicting_decision_content_rolls_back_graph_retirement(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    before = assignment_snapshot(dataset=dataset, track_id=song.pk)
    with pytest.raises(GraphValidationError, match="Conflicting evidence"):
        replace_graph(
            key=dataset.key,
            payload=without_nodes(payload, "french-dub"),
            expected_revision=dataset.revision,
            retirements={
                ref("french-dub"): {
                    "target": ref("dub"),
                    "provenance": {**provenance("french-dub"), "rationale": "different"},
                }
            },
        )
    assert GenreGraphDataset.objects.get(pk=dataset.key).revision == dataset.revision
    assert assignment_snapshot(dataset=dataset, track_id=song.pk) == before


@pytest.mark.parametrize(
    "model,field,value",
    [
        (GenreGraphEvidence, "rationale", "rewritten"),
        (GenreGraphRevision, "retirements", {}),
        (GenreGraphAttributionRevision, "attributions", {}),
    ],
)
def test_database_rejects_evidence_and_audit_updates(dataset, model, field, value):
    (song,) = tracks("French")
    assign(dataset, song, "dub")
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic():
        model.objects.all().update(**{field: value})


def test_retired_nodes_reject_direct_sql_attribution(dataset, payload):
    (song,) = tracks("French")
    node = dataset.nodes.get(identity=ref("french-dub"))
    replace_graph(
        key=dataset.key,
        payload=without_nodes(payload, "french-dub"),
        expected_revision=dataset.revision,
        retirements={ref("french-dub"): {"target": None, "provenance": provenance("retire")}},
    )
    with pytest.raises(IntegrityError, match="active graph"), transaction.atomic():
        GenreGraphAttribution.objects.create(track=song, node=node)


def test_restore_never_recreates_deleted_track(dataset):
    (song,) = tracks("Deleted")
    assign(dataset, song, "dub")
    reviewed = assignment_revision(dataset, song)
    track_id = song.pk
    Track.objects.filter(pk=track_id).delete()
    with pytest.raises(Track.DoesNotExist):
        restore_track_attributions(
            key=dataset.key,
            track_id=track_id,
            revision=reviewed,
            expected_revision=dataset.revision,
            expected_assignment_revision=None,
        )
    assert not Track.objects.filter(pk=track_id).exists()


def test_retirement_failure_after_remap_restores_complete_database_state(dataset, payload, monkeypatch):
    (song,) = tracks("Shared dub")
    assign(dataset, song, "french-dub")
    models = (
        GenreGraphDataset,
        type(dataset.nodes.first()),
        GenreGraphAccess,
        GenreGraphAttribution,
        GenreGraphAttributionEvidence,
        GenreGraphEvidence,
        GenreGraphAssignmentState,
        GenreGraphRevision,
        GenreGraphAttributionRevision,
    )

    def snapshot():
        return {model: list(model.objects.order_by("pk").values()) for model in models}

    before = snapshot()

    def fail_after_remap(*args):
        assert assignment_snapshot(dataset=dataset, track_id=song.pk) != {ref("french-dub"): [provenance("french-dub")]}
        raise RuntimeError("publication failed after retirement")

    monkeypatch.setattr(storage, "replace_access", fail_after_remap)
    with pytest.raises(RuntimeError, match="after retirement"):
        replace_graph(
            key=dataset.key,
            payload=without_nodes(payload, "french-dub"),
            expected_revision=dataset.revision,
            retirements={ref("french-dub"): {"target": ref("dub"), "provenance": provenance("retire")}},
        )
    assert snapshot() == before


@pytest.mark.parametrize("mutation", ["link_insert", "link_update", "assignment_move"])
def test_database_rejects_cross_dataset_evidence(dataset, payload, mutation):
    other = replace_graph(key="other", payload=payload, expected_revision=None)
    (song,) = tracks("Dub")
    assign(dataset, song, "dub")
    assign(other, song, "dub")
    row = GenreGraphAttribution.objects.get(track=song, node__dataset=dataset)
    other_row = GenreGraphAttribution.objects.get(track=song, node__dataset=other)
    other_evidence = other_row.evidence.get()
    reviewed = assignment_revision(dataset, song)

    def corrupt():
        if mutation == "link_insert":
            GenreGraphAttributionEvidence.objects.create(attribution=row, evidence=other_evidence)
        elif mutation == "link_update":
            GenreGraphAttributionEvidence.objects.filter(attribution=row).update(evidence=other_evidence)
        else:
            other_row.delete()
            GenreGraphAttribution.objects.filter(pk=row.pk).update(node=other_row.node)

    with pytest.raises(IntegrityError, match="dataset"), transaction.atomic():
        corrupt()
    assert assignment_revision(dataset, song) == reviewed
    assert row.evidence.get().dataset_id == dataset.pk


@pytest.mark.parametrize("model", [GenreGraphEvidence, GenreGraphRevision, GenreGraphAttributionRevision])
def test_database_rejects_direct_sql_evidence_and_audit_deletion(dataset, model):
    (song,) = tracks("Dub")
    assign(dataset, song, "dub")
    before = model.objects.count()
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {connection.ops.quote_name(model._meta.db_table)}")
    assert model.objects.count() == before


@pytest.mark.parametrize("failure", [None, "node", "evidence", "population", "after_archive"])
def test_staged_publication_preserves_complete_sets_empty_tokens_and_reviewed_retries(dataset, monkeypatch, failure):
    first, empty, untouched = tracks("Changed", "Cleared", "Untouched")
    for song in (first, empty, untouched):
        assign(dataset, song, "reggae")
    untouched_revision = assignment_revision(dataset, untouched)
    previous = assignment_revision(dataset, first)
    cleared = assignment_revision(dataset, empty)
    expected = {ref("dub"): [provenance("one"), provenance("two"), provenance("zero")]}
    with graph_write_transaction(key=dataset.pk, expected_revision=dataset.revision) as locked:
        evidence = register_evidence(locked, expected[ref("dub")])
        population = "population_" + uuid4().hex
        desired = "desired_" + uuid4().hex
        quote = connection.ops.quote_name
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE TEMPORARY TABLE {quote(population)} (track_id char(32) PRIMARY KEY)"
                if connection.vendor == "sqlite"
                else f"CREATE TEMPORARY TABLE {quote(population)} (track_id uuid PRIMARY KEY)"
            )
            cursor.execute(
                f"CREATE TEMPORARY TABLE {quote(desired)} (track_id {'char(32)' if connection.vendor == 'sqlite' else 'uuid'}, node_id bigint, evidence_id bigint)"
            )
            prepared = [Track._meta.pk.get_db_prep_value(song.pk, connection) for song in (first, empty)]
            cursor.executemany(f"INSERT INTO {quote(population)} VALUES (%s)", [(pk,) for pk in prepared])
            cursor.executemany(
                f"INSERT INTO {quote(desired)} VALUES (%s, %s, %s)",
                [
                    (prepared[0], locked.nodes.get(identity=ref("dub")).pk, row.pk)
                    for row in reversed(evidence.values())
                ],
            )
            if failure:
                models = (
                    GenreGraphAttribution,
                    GenreGraphAttributionEvidence,
                    GenreGraphAssignmentState,
                    GenreGraphAttributionRevision,
                    GenreGraphDataset,
                )
                before = {model: list(model.objects.order_by("pk").values()) for model in models}
                if failure == "after_archive":
                    archive = publication.archive_population
                    archive_calls = 0

                    def fail_after_archive(*args, **kwargs):
                        nonlocal archive_calls
                        archive(*args, **kwargs)
                        archive_calls += 1
                        if archive_calls == 2:
                            raise RuntimeError("Interrupted publication")

                    monkeypatch.setattr(publication, "archive_population", fail_after_archive)
                elif failure == "population":
                    cursor.execute(f"DELETE FROM {quote(population)} WHERE track_id = %s", [prepared[0]])
                else:
                    cursor.execute(f"UPDATE {quote(desired)} SET {failure}_id = -1")
                error = RuntimeError if failure == "after_archive" else GraphValidationError
                with pytest.raises(error), transaction.atomic():
                    publish_staged_attributions(dataset=locked, population=population, assignments=desired)
                assert {model: list(model.objects.order_by("pk").values()) for model in models} == before
                cursor.execute(f"DROP TABLE {quote(desired)}")
                cursor.execute(f"DROP TABLE {quote(population)}")
                return
            publish_staged_attributions(dataset=locked, population=population, assignments=desired)
            first_token, empty_token = assignment_revision(locked, first), assignment_revision(locked, empty)
            assert first_token != previous
            assert empty_token != cleared
            assert assignment_snapshot(dataset=locked, track_id=first.pk) == expected
            assert assignment_snapshot(dataset=locked, track_id=empty.pk) == {}
            assert assignment_revision(locked, untouched) == untouched_revision
            assert GenreGraphAttributionRevision.objects.get(revision=previous).attributions == {
                ref("reggae"): [provenance("reggae")]
            }
            assert GenreGraphAttributionRevision.objects.get(revision=first_token).attributions == expected
            assert GenreGraphAttributionRevision.objects.get(revision=empty_token).attributions == {}
            membership = GenreGraphDataset.objects.get(pk=locked.pk).membership_revision
            publish_staged_attributions(dataset=locked, population=population, assignments=desired)
            assert assignment_revision(locked, first) == first_token
            assert assignment_revision(locked, empty) == empty_token
            assert GenreGraphDataset.objects.get(pk=locked.pk).membership_revision == membership
            cursor.execute(f"DROP TABLE {quote(desired)}")
            cursor.execute(f"DROP TABLE {quote(population)}")


@pytest.mark.parametrize("mutation", ["remove_evidence", "move_assignment"])
def test_direct_sql_assignment_mutations_invalidate_reviewed_tokens(dataset, mutation):
    (song,) = tracks("Direct SQL edit")
    assign(dataset, song, "dub")
    reviewed = assignment_revision(dataset, song)
    dataset.refresh_from_db()
    membership = dataset.membership_revision
    row = GenreGraphAttribution.objects.get(track=song, node__dataset=dataset)
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        if mutation == "remove_evidence":
            cursor.execute(
                f"DELETE FROM {quote(GenreGraphAttributionEvidence._meta.db_table)} WHERE attribution_id = %s",
                [row.pk],
            )
        else:
            cursor.execute(
                f"UPDATE {quote(GenreGraphAttribution._meta.db_table)} SET node_id = %s WHERE id = %s",
                [dataset.nodes.get(identity=ref("french-dub")).pk, row.pk],
            )
    assert assignment_revision(dataset, song) != reviewed
    dataset.refresh_from_db()
    assert dataset.membership_revision != membership
    with pytest.raises(GraphRevisionConflict, match="assignments changed"):
        replace_track_attributions(
            key=dataset.pk,
            track_id=song.pk,
            attributions={},
            expected_revision=dataset.revision,
            expected_assignment_revision=reviewed,
        )


def test_restore_older_revision_requires_explicit_retirement_for_added_identity(dataset, payload):
    added = deepcopy(payload)
    added["nodes"].append({"id": ref("added"), "name": "Added", "kind": "genre", "canonicalState": "before_entry"})
    updated = replace_graph(key=dataset.key, payload=added, expected_revision=dataset.revision)
    permanent = updated.nodes.get(identity=ref("added"))
    with pytest.raises(GraphValidationError, match="Retirements must name"):
        restore_graph(key=dataset.key, revision=dataset.revision, expected_revision=updated.revision)
    restored = restore_graph(
        key=dataset.key,
        revision=dataset.revision,
        expected_revision=updated.revision,
        retirements={permanent.identity: {"target": None, "provenance": provenance("restore-added")}},
    )
    permanent.refresh_from_db()
    assert not permanent.is_active
    reactivated = replace_graph(key=dataset.key, payload=added, expected_revision=restored.revision)
    assert reactivated.nodes.get(identity=permanent.identity).pk == permanent.pk


@pytest.mark.parametrize("retired", [False, True])
def test_permanent_nodes_cannot_be_deleted_and_recreated(dataset, payload, retired):
    node = dataset.nodes.get(identity=ref("french-dub"))
    if retired:
        replace_graph(
            key=dataset.key,
            payload=without_nodes(payload, "french-dub"),
            expected_revision=dataset.revision,
            retirements={node.identity: {"target": None, "provenance": provenance("delete-retired")}},
        )
    with pytest.raises(IntegrityError, match="immutable"), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {connection.ops.quote_name(node._meta.db_table)} WHERE id = %s", [node.pk])
    assert dataset.nodes.get(identity=node.identity).pk == node.pk


def test_retirement_preserves_single_assignment_constraint_and_evidence(dataset, payload):
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
    (song,) = tracks("Singular membership")
    assign(dataset, song, "french-dub")
    reviewed = assignment_revision(dataset, song)
    table = connection.ops.quote_name(GenreGraphAttribution._meta.db_table)
    # Model a consumer that enforces a single direct assignment independently of graph storage.
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE UNIQUE INDEX singular_consumer_assignment ON {table} (track_id)")
    try:
        updated = replace_graph(
            key=dataset.key,
            payload=without_nodes(payload, "french-dub"),
            expected_revision=dataset.revision,
            retirements={ref("french-dub"): {"target": ref("dub"), "provenance": provenance("retire")}},
        )
        assert assignment_snapshot(dataset=updated, track_id=song.pk) == {
            ref("dub"): [provenance("french-dub"), provenance("retire")]
        }
        assert GenreGraphAttributionRevision.objects.get(revision=reviewed).attributions == {
            ref("french-dub"): [provenance("french-dub")]
        }
        current = assignment_revision(updated, song)
        assert current != reviewed
        assert GenreGraphAttributionRevision.objects.get(revision=current).attributions == assignment_snapshot(
            dataset=updated, track_id=song.pk
        )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX singular_consumer_assignment")


def immediate_constraints():
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def test_assignment_api_rejects_several_nodes_per_track(dataset):
    (song,) = tracks("Two nodes")
    with pytest.raises(GraphValidationError, match="at most one node"):
        assign(dataset, song, "french-dub", "jamaican-dub")
    assert not GenreGraphAttribution.objects.exists()
    assign(dataset, song, "french-dub")
    archived = GenreGraphAttributionRevision.objects.get(revision=assignment_revision(dataset, song))
    archived.attributions = {ref("dub"): [provenance("a")], ref("reggae"): [provenance("b")]}
    with pytest.raises(GraphValidationError, match="at most one node"):
        replace_track_attributions(
            key=dataset.key,
            track_id=song.pk,
            attributions=archived.attributions,
            expected_revision=dataset.revision,
            expected_assignment_revision=assignment_revision(dataset, song),
        )


def test_assignments_are_scoped_per_dataset_and_denormalize_dataset(dataset, payload):
    other = replace_graph(key="other", payload=payload, expected_revision=None)
    (song,) = tracks("Both datasets")
    assign(dataset, song, "dub")
    assign(other, song, "reggae")
    assert set(GenreGraphAttribution.objects.filter(track=song).values_list("dataset_id", flat=True)) == {
        "reference",
        "other",
    }
    assert all(row.dataset_id == row.node.dataset_id for row in GenreGraphAttribution.objects.select_related("node"))


def test_database_rejects_second_node_for_a_track_and_dataset(dataset):
    (song,) = tracks("Direct SQL duplicate")
    assign(dataset, song, "dub")
    node = dataset.nodes.get(identity=ref("reggae"))
    with pytest.raises(IntegrityError), transaction.atomic():
        GenreGraphAttribution.objects.bulk_create([GenreGraphAttribution(track=song, node=node, dataset=dataset)])


def test_database_rejects_attribution_dataset_that_differs_from_node(dataset, payload):
    other = replace_graph(key="other", payload=payload, expected_revision=None)
    (song,) = tracks("Mismatched dataset")
    node = dataset.nodes.get(identity=ref("dub"))
    with transaction.atomic():
        immediate_constraints()
        with pytest.raises(IntegrityError):
            GenreGraphAttribution.objects.bulk_create([GenreGraphAttribution(track=song, node=node, dataset=other)])


def test_database_rejects_changing_attribution_dataset(dataset, payload):
    other = replace_graph(key="other", payload=payload, expected_revision=None)
    (song,) = tracks("Immutable dataset")
    assign(dataset, song, "dub")
    with transaction.atomic():
        immediate_constraints()
        with pytest.raises(IntegrityError):
            GenreGraphAttribution.objects.filter(track=song).update(dataset=other)


def test_staged_publication_rejects_several_nodes_per_track(dataset):
    (song,) = tracks("Staged duplicate")
    with graph_write_transaction(key=dataset.pk, expected_revision=dataset.revision) as locked:
        evidence = register_evidence(locked, [provenance("staged")])["staged"]
        population, desired = "population_" + uuid4().hex, "desired_" + uuid4().hex
        quote = connection.ops.quote_name
        uuid_type = "char(32)" if connection.vendor == "sqlite" else "uuid"
        pk = Track._meta.pk.get_db_prep_value(song.pk, connection)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE TEMPORARY TABLE {quote(population)} (track_id {uuid_type} PRIMARY KEY)")
            cursor.execute(
                f"CREATE TEMPORARY TABLE {quote(desired)} (track_id {uuid_type}, node_id bigint, evidence_id bigint)"
            )
            cursor.execute(f"INSERT INTO {quote(population)} VALUES (%s)", [pk])
            cursor.executemany(
                f"INSERT INTO {quote(desired)} VALUES (%s, %s, %s)",
                [(pk, locked.nodes.get(identity=ref(name)).pk, evidence.pk) for name in ("dub", "reggae")],
            )
            with pytest.raises(GraphValidationError, match="at most one node"), transaction.atomic():
                publish_staged_attributions(dataset=locked, population=population, assignments=desired)
            cursor.execute(f"DROP TABLE {quote(desired)}")
            cursor.execute(f"DROP TABLE {quote(population)}")
    assert not GenreGraphAttribution.objects.exists()
