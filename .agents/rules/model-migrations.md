# Model and migration review

This package contains both abstract models implemented by consumers and concrete models with package-owned tables. Inspect each model's `Meta` and the migration history before judging whether it requires a table or a consumer-owned subclass. Concrete examples include `CriteriaType`, `Track`, `TrackPlaylistRel`, `Playlist`, and `ImportRun`.

Both the package and fixture app have migration histories. After changing models, run `DJANGO_SETTINGS_MODULE=tests.settings PYTHONPATH=. uv run django-admin makemigrations fixture_app the_music_tree_genre_kit --check --dry-run`; review and include any migrations actually required. A change does not necessarily require edits to both histories. Review schema and data compatibility with consuming services.
