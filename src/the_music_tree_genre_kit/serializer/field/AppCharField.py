from typing import Any

from rest_framework import serializers

from .AppField import AppField


class AppCharField(AppField, serializers.CharField):
    def to_internal_value(self, data: Any) -> str:
        if data is None:
            if not self.allow_null:
                self.fail("null")
            return None

        if not isinstance(data, str):
            self.fail("invalid")

        value = data.strip() if self.trim_whitespace else data

        if value == "" and not self.allow_blank:
            self.fail("blank")

        if self.max_length is not None and len(value) > self.max_length:
            self.fail("max_length", max_length=self.max_length)

        if self.min_length is not None and len(value) < self.min_length:
            self.fail("min_length", min_length=self.min_length)

        return value
