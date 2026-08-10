from django.conf import settings
from django.db import models

from the_music_tree_genre_kit.base.BaseModel import BaseModel


class PrivateModel(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)ss")

    class Meta:
        abstract = True
