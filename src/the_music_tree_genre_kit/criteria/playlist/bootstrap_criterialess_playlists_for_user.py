from typing import Any

from the_music_tree_genre_kit.criteria.type.CriteriaType import CriteriaType
from the_music_tree_genre_kit.criteria.type.CriteriaTypePks import CriteriaTypePks

from .AbstractCriteriaPlaylist import AbstractCriteriaPlaylist


def bootstrap_criterialess_playlists_for_user(
    *, user: Any, criteria_playlist_model: type[AbstractCriteriaPlaylist]
) -> None:
    """
    Idempotently ensure the Genreless/Tagless catch-all CriteriaPlaylist rows
    exist for `user`. Track-touching code (e.g. transfer_direct_tracks_to_criterialess_playlist)
    assumes these rows already exist per (user, type) — safe to call from both
    a post_save signal on new users and a one-off backfill for existing ones.
    """
    for criteria_type_pk in [CriteriaTypePks.GENRE, CriteriaTypePks.TAG]:
        criteria_type = CriteriaType.objects.get(pk=int(criteria_type_pk))
        criteria_playlist_model.objects.get_or_create(user=user, type=criteria_type, criteria=None)
