import pytest
from django.contrib.auth import get_user_model

from tests.fixture_app.models import Album, Artist, Criteria, CriteriaPlaylist, Track, TrackPlaylistRel
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
def genre_tree(user, genre_type, tag_type):
    bootstrap_criterialess_playlists_for_user(user=user, criteria_playlist_model=CriteriaPlaylist)

    root = Criteria(user=user, type=genre_type)
    root._name = "Electronic"
    root.save()
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=root)

    child = Criteria(user=user, type=genre_type, parent=root)
    child._name = "House"
    child.save()
    CriteriaPlaylist.objects.create(user=user, type=genre_type, criteria=child)

    return root, child


@pytest.mark.django_db
def test_create_track_with_genre_adds_to_genre_and_ascendant_playlists(user, genre_tree):
    root, child = genre_tree

    track = Track.objects.create(user=user, genre=child)

    assert TrackPlaylistRel.objects.filter(playlist=child.criteria_playlist, track=track).exists()
    assert TrackPlaylistRel.objects.filter(playlist=root.criteria_playlist, track=track).exists()


@pytest.mark.django_db
def test_create_track_without_genre_adds_to_genreless_playlist(user, genre_type, genre_tree):
    track = Track.objects.create(user=user)

    genreless = CriteriaPlaylist.objects.get(user=user, criteria=None, type=genre_type)
    assert TrackPlaylistRel.objects.filter(playlist=genreless, track=track).exists()


@pytest.mark.django_db
def test_create_track_with_artists_sets_them(user, genre_tree):
    artist = Artist.objects.create(user=user, name="Daft Punk")

    track = Track.objects.create(user=user, artists=[artist])

    assert list(track.artists.all()) == [artist]


@pytest.mark.django_db
def test_update_instance_moves_track_between_genre_playlists(user, genre_tree):
    root, child = genre_tree
    track = Track.objects.create(user=user, genre=child)

    updated = Track.objects.update_instance(track, genre=root)

    assert not TrackPlaylistRel.objects.filter(playlist=child.criteria_playlist, track=updated).exists()
    assert TrackPlaylistRel.objects.filter(playlist=root.criteria_playlist, track=updated).exists()


@pytest.mark.django_db
def test_update_instance_swapping_album_deletes_orphaned_old_album_and_artists(user, genre_tree):
    old_artist = Artist.objects.create(user=user, name="Solo Artist")
    old_album = Album.objects.create(user=user, name="Solo Album")
    old_album.album_artists.set([old_artist])
    new_album = Album.objects.create(user=user, name="New Album")

    track = Track.objects.create(user=user, album=old_album, artists=[old_artist])

    Track.objects.update_instance(track, album=new_album, artists=[])

    assert not Album.objects.filter(pk=old_album.pk).exists()
    assert not Artist.objects.filter(pk=old_artist.pk).exists()
    assert Album.objects.filter(pk=new_album.pk).exists()


@pytest.mark.django_db
def test_update_instance_archiving_and_unarchiving_track_updates_rel_positions(user, genre_tree):
    _root, child = genre_tree
    track_a = Track.objects.create(user=user, genre=child)
    track_b = Track.objects.create(user=user, genre=child)

    Track.objects.update_instance(track_a, archived=True)

    rel_a = TrackPlaylistRel.objects.get(playlist=child.criteria_playlist, track=track_a)
    rel_b = TrackPlaylistRel.objects.get(playlist=child.criteria_playlist, track=track_b)
    assert rel_a.position is None
    assert rel_b.position == 1

    Track.objects.update_instance(track_a, archived=False)
    rel_a.refresh_from_db()
    assert rel_a.position == 1


@pytest.mark.django_db
def test_delete_instance_with_checking_album_and_artists_removes_orphaned_album_and_artists(user, genre_tree):
    # `delete_instance` itself reads `instance.playlists_with_positions`, which no
    # attached model/mixin in this stack actually defines, so calling it always raises
    # AttributeError. We exercise the underlying helper it delegates deletion to instead.
    artist = Artist.objects.create(user=user, name="Solo Artist")
    album = Album.objects.create(user=user, name="Solo Album")
    album.album_artists.set([artist])
    track = Track.objects.create(user=user, album=album, artists=[artist])

    Track.objects.delete_instance_with_checking_album_and_artists_potential_deletion(track)

    assert not Track.objects.filter(pk=track.pk).exists()
    assert not Album.objects.filter(pk=album.pk).exists()
    assert not Artist.objects.filter(pk=artist.pk).exists()


@pytest.mark.django_db
def test_delete_instance_with_checking_album_and_artists_keeps_album_linked_to_other_tracks(user, genre_tree):
    album = Album.objects.create(user=user, name="Shared Album")
    track_a = Track.objects.create(user=user, album=album)
    Track.objects.create(user=user, album=album)

    Track.objects.delete_instance_with_checking_album_and_artists_potential_deletion(track_a)

    assert Album.objects.filter(pk=album.pk).exists()


@pytest.mark.django_db
def test_delete_instance_raises_because_playlists_with_positions_is_undefined(user, genre_tree):
    _root, child = genre_tree
    track = Track.objects.create(user=user, genre=child)

    with pytest.raises(AttributeError, match="playlists_with_positions"):
        Track.objects.delete_instance(track)
