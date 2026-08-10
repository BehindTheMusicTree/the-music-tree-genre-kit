from django.apps import AppConfig


class FixtureAppConfig(AppConfig):
    name = "tests.fixture_app"
    label = "fixture_app"
    default_auto_field = "django.db.models.BigAutoField"
