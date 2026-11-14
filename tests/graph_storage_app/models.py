"""Minimal consumers for PostgreSQL storage tests, independent of SQLite fixtures."""

from uuid import uuid4

from django.db import models


class Criteria(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)


class Artist(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)


class Album(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid4)
