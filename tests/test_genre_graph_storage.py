import json
from copy import deepcopy
from pathlib import Path

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from the_music_tree_genre_kit.genre_graph import GenreGraph, GraphValidationError
from the_music_tree_genre_kit.genre_graph.models import (
    GenreGraphAccess,
    GenreGraphAttribution,
    GenreGraphAttributionRevision,
    GenreGraphDataset,
    GenreGraphRevision,
)
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


def assign(dataset, track, *identities):
    replace_track_attributions(
        key=dataset.key,
        track_id=track.pk,
        attributions={ref(identity): provenance(identity) for identity in identities},
        expected_revision=dataset.revision,
    )


def tracks(*names):
    instances = [Track(title=name) for name in names]
    Track.objects.bulk_create(instances)
    return instances


def selected(identity, scope="all"):
    return set(
        select_tracks(Track.objects.all(), key="reference", identity=ref(identity), scope=scope).values_list(
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
    assign(dataset, french, "french-dub", "france", "dub")
    assign(dataset, british, "british-dub")
    assign(dataset, unknown_region, "dub")
    assert selected("dub", "canonical") == {"Jamaican", "French", "British", "Unknown region"}
    assert selected("france") == {"French"}
    assert selected("jamaica") == {"Jamaican"}
    assert selected("britain") == {"British"}
    assert selected("world") == {"Jamaican", "French", "British"}
    assert select_tracks(Track.objects.all(), key=dataset.key, identity=ref("world")).count() == 3
    assert set(Track.objects.values_list("pk", flat=True)) == {
        jamaican.pk,
        french.pk,
        british.pk,
        unknown_region.pk,
        unclassified.pk,
    }


def test_r06_r07_sql_normalization_precedes_refinement(dataset):
    inherited, independent, direct = tracks("Inherited", "Independent", "Direct")
    assign(dataset, inherited, "breton-rock", "brittany", "france")
    assign(dataset, independent, "breton-rock", "jamaica")
    assign(dataset, direct, "brittany")
    effective = effective_attributions(key=dataset.key)
    assert set(effective.filter(track=inherited).values_list("node__identity", flat=True)) == {ref("breton-rock")}
    assert set(tracks_needing_refinement(Track.objects.all(), key=dataset.key).values_list("title", flat=True)) == {
        "Independent",
        "Direct",
    }
    assert selected("france") == {"Inherited", "Independent", "Direct"}


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
    with pytest.raises(ProtectedError):
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
    with pytest.raises(GraphValidationError, match="provenance"):
        replace_track_attributions(
            key=dataset.key, track_id=song.pk, attributions={ref("dub"): {}}, expected_revision=dataset.revision
        )
    assert selected("france") == {"French"}
    assign(dataset, song)
    assert not GenreGraphAttribution.objects.exists()
    assert Track.objects.filter(pk=song.pk).exists()


def test_e02_missing_dataset_is_not_an_empty_configuration():
    with pytest.raises(GenreGraphDataset.DoesNotExist):
        select_tracks(Track.objects.all(), key="missing", identity=ref("dub"))


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
    with pytest.raises(GraphValidationError, match="provenance"):
        replace_track_attributions(
            key=dataset.key, track_id=song.pk, attributions={ref("dub"): bad}, expected_revision=dataset.revision
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
    assert set(
        select_tracks(Track.objects.all(), key=dataset.key, identity=ref("reggae"), include_descendants=False)
    ) == {parent}
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
                    [GenreGraphAttribution(track=song, node=node, provenance=provenance("bulk"))]
                )
            case "update":
                GenreGraphAttribution.objects.filter(track=song).update(provenance=provenance("updated"))
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
    archived = GenreGraphAttributionRevision.objects.get(attributions={ref("french-dub"): provenance("french-dub")})
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
        key=dataset.key, track_id=song.pk, revision=archived.revision, expected_revision=dataset.revision
    )
    assert selected("france") == {"French"}
    assert selected("jamaica") == set()
    assert dict(GenreGraphAttribution.objects.values_list("node__identity", "provenance")) == archived.attributions


def test_e03_assignment_restore_rejects_missing_identity_atomically(dataset, payload):
    (song,) = tracks("French")
    assign(dataset, song, "french-dub")
    archived = GenreGraphAttributionRevision.objects.get(attributions={ref("french-dub"): provenance("french-dub")})
    assign(dataset, song, "dub")
    payload["nodes"] = [node for node in payload["nodes"] if node["id"] != ref("french-dub")]
    payload["relations"] = [edge for edge in payload["relations"] if edge["childId"] != ref("french-dub")]
    updated = replace_graph(key=dataset.key, payload=payload, expected_revision=dataset.revision)
    before = GenreGraphAttributionRevision.objects.count()
    with pytest.raises(GraphValidationError, match="Unknown attribution"):
        restore_track_attributions(
            key=dataset.key, track_id=song.pk, revision=archived.revision, expected_revision=updated.revision
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
                    [GenreGraphAttribution(track=song, node=node, provenance=provenance("private"))]
                )
            else:
                Track.objects.filter(pk=song.pk).update(user=user)

    with pytest.raises(IntegrityError, match="ownerless"):
        invalid_change()
    assert GenreGraphAttribution.objects.filter(track=song).exists() == (operation == "transfer")
