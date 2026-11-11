import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from tests.fixture_app.manager import CriteriaManager
from tests.fixture_app.models import Criteria, CriteriaPlaylist, Genre, Track, TrackPlaylistRel
from the_music_tree_genre_kit.criteria.playlist.bootstrap_criterialess_playlists_for_user import (
    bootstrap_criterialess_playlists_for_user,
)
from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks


@pytest.fixture
def user():
    return get_user_model().objects.create(username="fixture-user")


@pytest.fixture
def genre_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.GENRE), label="genre")


@pytest.fixture
def tag_type():
    return CriteriaType.objects.create(pk=int(CriteriaTypePks.TAG), label="tag")


@pytest.fixture
def make(genre_type, tag_type):
    def make(owner, name, parent=None, **kwargs):
        bootstrap_criterialess_playlists_for_user(user=owner, criteria_playlist_model=CriteriaPlaylist)
        criteria = Criteria.objects.create(user=owner, _name=name, parent=parent, **kwargs)
        CriteriaPlaylist.objects.create(user=owner, type=genre_type, criteria=criteria)
        return criteria

    return make


def playlist_has(criteria, track):
    return TrackPlaylistRel.objects.filter(playlist=criteria.criteria_playlist, track=track).exists()


def genreless_has(owner, genre_type, track):
    playlist = CriteriaPlaylist.objects.get(user=owner, criteria=None, type=genre_type)
    return TrackPlaylistRel.objects.filter(playlist=playlist, track=track).exists()


def tree_state(owner):
    """Everything the delete is supposed to maintain, keyed by names so two owners' trees compare equal."""
    names = dict(Criteria.objects.filter(user=owner).values_list("pk", "_name"))
    criteria = {
        row.pk: (
            names[row.parent_id] if row.parent_id else None,
            names[row.root_id],
            frozenset(names[pk] for pk in row.additional_primary_parents.values_list("pk", flat=True)),
            frozenset(names[pk] for pk in row.secondary_parents.values_list("pk", flat=True)),
            frozenset(row.ascendants.values_list("_name", flat=True)),
        )
        for row in Criteria.objects.filter(user=owner)
    }
    criteria_of_playlist = dict(CriteriaPlaylist.objects.filter(user=owner).values_list("pk", "criteria_id"))
    tracks = {}
    for track in Track.objects.filter(user=owner):
        playlists = frozenset(
            (names.get(criteria_of_playlist[rel.playlist_id]), rel.position)
            for rel in TrackPlaylistRel.objects.filter(track=track)
        )
        tracks[track.title] = (names.get(track.genre_id), playlists)
    return {names[pk]: state for pk, state in criteria.items()}, tracks


@pytest.mark.django_db
def test_chain_of_deleted_parents_splices_children_and_moves_tracks_to_nearest_survivor(user, genre_type, make):
    root = make(user, "Root")
    a = make(user, "A", root)
    b = make(user, "B", a)
    c = make(user, "C", b)
    on_root, on_a, on_b, on_c = (Track.objects.create(user=user, genre=g, title=g._name) for g in (root, a, b, c))

    Criteria.objects.delete_instances([a, b])

    c.refresh_from_db()
    assert c.parent == root and c.root == root
    assert set(c.ascendants.values_list("_name", flat=True)) == {"Root"}
    for track in (on_root, on_a, on_b):
        track.refresh_from_db()
        assert track.genre == root
        assert playlist_has(root, track)
    on_c.refresh_from_db()
    assert on_c.genre == c and playlist_has(c, on_c) and playlist_has(root, on_c)
    assert not Criteria.objects.filter(pk__in=[a.pk, b.pk]).exists()
    assert not CriteriaPlaylist.objects.filter(criteria__in=[a.pk, b.pk]).exists()


@pytest.mark.django_db
def test_stale_root_sends_its_tracks_to_the_genreless_playlist_and_promotes_children(user, genre_type, make):
    root = make(user, "Root")
    a = make(user, "A", root)
    c = make(user, "C", a)
    on_root = Track.objects.create(user=user, genre=root, title="on_root")
    on_a = Track.objects.create(user=user, genre=a, title="on_a")
    on_c = Track.objects.create(user=user, genre=c, title="on_c")

    Criteria.objects.delete_instances([root, a])

    c.refresh_from_db()
    assert c.parent is None and c.root == c
    for track in (on_root, on_a):
        track.refresh_from_db()
        assert track.genre is None
        assert genreless_has(user, genre_type, track)
    # Whether on_c also reaches the genreless playlist depends on the app's `_get_direct_tracks` override.
    on_c.refresh_from_db()
    assert on_c.genre == c and playlist_has(c, on_c)


@pytest.mark.django_db
def test_deleting_a_multi_parent_node_keeps_children_under_both_primary_branches(user, make):
    rock, jazz = make(user, "Rock"), make(user, "Jazz")
    fusion = make(user, "Fusion", rock, tree_name="regional", additional_primary_parents=[jazz])
    sub = make(user, "Sub", fusion, tree_name="regional")
    on_fusion = Track.objects.create(user=user, genre=fusion, title="on_fusion")
    on_sub = Track.objects.create(user=user, genre=sub, title="on_sub")

    Criteria.objects.delete_instances([fusion])

    sub.refresh_from_db()
    assert sub.parent == rock and sub.root == rock
    assert list(sub.additional_primary_parents.all()) == [jazz]
    assert set(sub.ascendants.values_list("_name", flat=True)) == {"Rock", "Jazz"}
    assert playlist_has(sub, on_sub) and playlist_has(rock, on_sub) and playlist_has(jazz, on_sub)
    on_fusion.refresh_from_db()
    assert on_fusion.genre == rock
    assert playlist_has(rock, on_fusion) and not playlist_has(jazz, on_fusion)


@pytest.mark.django_db
def test_lost_playlists_close_their_position_gaps(user, make):
    rock, jazz = make(user, "Rock"), make(user, "Jazz")
    fusion = make(user, "Fusion", rock, tree_name="regional", additional_primary_parents=[jazz])
    keep_first = Track.objects.create(user=user, genre=jazz, title="keep_first")
    moved = Track.objects.create(user=user, genre=fusion, title="moved")
    keep_last = Track.objects.create(user=user, genre=jazz, title="keep_last")
    jazz_playlist = jazz.criteria_playlist
    for position, track in enumerate((keep_first, moved, keep_last), 1):
        TrackPlaylistRel.objects.filter(playlist=jazz_playlist, track=track).update(position=position)

    Criteria.objects.delete_instances([fusion])

    assert not playlist_has(jazz, moved)
    positions = TrackPlaylistRel.objects.filter(playlist=jazz_playlist).order_by("position")
    assert [(rel.track_id, rel.position) for rel in positions] == [(keep_first.pk, 1), (keep_last.pk, 2)]


@pytest.mark.django_db
def test_locked_descendant_of_a_deleted_genre_is_reparented(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    def genre(name, parent=None):
        row = Genre.objects.create(user=user, _name=name, parent=parent)
        CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=row)
        return row

    root = genre("Root")
    stale = genre("Stale", root)
    locked = genre("Locked", stale)
    Genre.objects.filter(pk=locked.pk).update(is_manually_edited=True)

    Genre.objects.delete_instances([stale])

    locked.refresh_from_db()
    assert locked.parent_id == root.pk and locked.is_manually_edited


@pytest.mark.django_db
def test_batch_delete_leaves_the_same_state_as_sequential_leaves_first_deletes(genre_type, make):
    def build(owner):
        root, other = make(owner, "Root"), make(owner, "Other")
        a = make(owner, "A", root)
        b = make(owner, "B", a)
        c = make(owner, "C", b)
        d = make(owner, "D", root)
        e = make(owner, "E", d)
        fusion = make(owner, "Fusion", a, tree_name="regional", additional_primary_parents=[other])
        deep = make(owner, "Deep", fusion, tree_name="regional", additional_primary_parents=[e])
        lone = make(owner, "Lone")
        sub = make(owner, "Sub", lone)
        make(owner, "Tagged", e, secondary_parents=[b, fusion])
        for criteria in (root, other, a, b, c, d, e, fusion, deep, lone, sub):
            for index in range(2):
                Track.objects.create(user=owner, genre=criteria, title=f"{criteria._name}{index}")
        return {criteria._name: criteria for criteria in Criteria.objects.filter(user=owner)}

    batch_owner = get_user_model().objects.create(username="batch")
    sequential_owner = get_user_model().objects.create(username="sequential")
    batch = build(batch_owner)
    sequential = build(sequential_owner)
    stale_names = ["A", "B", "Fusion", "E", "Lone"]

    Criteria.objects.delete_instances([batch[name] for name in stale_names])
    # Leaves first: the deepest (most ascendants) deleted before the ancestors it hangs from.
    for name in sorted(stale_names, key=lambda n: -sequential[n].ascendants.count()):
        Criteria.objects.delete_instance(Criteria.objects.get(pk=sequential[name].pk))

    assert tree_state(batch_owner) == tree_state(sequential_owner)


@pytest.mark.django_db
def test_batch_hooks_receive_the_moves_and_the_deleted_instances(user, make, monkeypatch):
    root = make(user, "Root")
    a = make(user, "A", root)
    b = make(user, "B", a)
    Track.objects.create(user=user, genre=b, title="on_b")
    calls = []
    monkeypatch.setattr(
        CriteriaManager, "_on_tracks_genre_moved", lambda self, moves, actor=None: calls.append(("moved", dict(moves)))
    )
    monkeypatch.setattr(
        CriteriaManager,
        "_on_before_delete_many",
        lambda self, instances, actor=None: calls.append(("delete", sorted(i._name for i in instances))),
    )

    Criteria.objects.delete_instances([a, b])

    assert calls == [("moved", {a.pk: root.pk, b.pk: root.pk}), ("delete", ["A", "B"])]


@pytest.mark.django_db
def test_delete_instances_query_count_is_independent_of_track_count(genre_type, make):
    def count_queries(track_count):
        owner = get_user_model().objects.create(username=f"owner{track_count}")
        root = make(owner, "Root")
        stale = [make(owner, "A", root)]
        stale.append(make(owner, "B", stale[0]))
        for index in range(track_count):
            Track.objects.create(user=owner, genre=stale[index % 2], title=f"t{index}")
        with CaptureQueriesContext(connection) as queries:
            Criteria.objects.delete_instances(stale)
        return len(queries.captured_queries)

    assert count_queries(2) == count_queries(40)


@pytest.mark.django_db
def test_track_leaving_a_stale_additional_parent_root_keeps_its_genre_and_stays_out_of_genreless(
    user, genre_type, make
):
    kept_parent, stale_root = make(user, "P"), make(user, "E")
    stale = make(user, "X", kept_parent, tree_name="regional", additional_primary_parents=[stale_root])
    track = Track.objects.create(user=user, genre=stale, title="t")

    Criteria.objects.delete_instances([stale_root, stale])

    track.refresh_from_db()
    assert track.genre == kept_parent
    assert playlist_has(kept_parent, track) and not genreless_has(user, genre_type, track)


@pytest.mark.django_db
def test_deleting_an_instance_already_gone_is_a_no_op(user, make):
    root = make(user, "Root")
    gone = make(user, "Gone", root)
    stale_copy = Criteria.objects.get(pk=gone.pk)
    Criteria.objects.delete_instances([gone])

    Criteria.objects.delete_instances([stale_copy])

    assert list(Criteria.objects.filter(user=user)) == [root]
