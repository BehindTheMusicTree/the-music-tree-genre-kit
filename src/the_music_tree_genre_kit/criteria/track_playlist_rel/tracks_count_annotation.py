from django.db.models import Count, OuterRef, Subquery
from django.db.models.functions import Coalesce

from .Fields import Fields
from .TrackPlaylistRel import TrackPlaylistRel


def tracks_count_annotation() -> Coalesce:
    """
    Per-playlist track count for `.annotate(...)` on a Playlist queryset. Correlated, so only
    the page's rows are counted: a joined COUNT ... GROUP BY aggregates every playlist first.
    """
    count = (
        TrackPlaylistRel._default_manager.filter(**{Fields.PLAYLIST: OuterRef("pk")})
        .order_by()
        .values(Fields.PLAYLIST)
        .annotate(count=Count("pk"))
    )
    return Coalesce(Subquery(count.values("count")), 0)
