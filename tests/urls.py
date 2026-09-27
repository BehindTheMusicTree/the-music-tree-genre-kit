from rest_framework.routers import DefaultRouter

from tests.fixture_app.viewset import CriteriaPlaylistViewSet, CriteriaViewSet, TrackViewSet

router = DefaultRouter()
router.register(r"criteria", CriteriaViewSet, basename="criteria")
router.register(r"tracks", TrackViewSet, basename="tracks")
router.register(r"criteria-playlists", CriteriaPlaylistViewSet, basename="criteria-playlists")

urlpatterns = router.urls
