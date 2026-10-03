from django.db import models


class YoutubeUnplayableReason(models.TextChoices):
    """Why a track's YouTube video can't be played in an embed; null on a track means playable."""

    NOT_FOUND = "not_found"
    NOT_EMBEDDABLE = "not_embeddable"
    PRIVATE = "private"
    NOT_PROCESSED = "not_processed"
    REGION_WHITELISTED = "region_whitelisted"
