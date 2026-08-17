from rest_framework.routers import DefaultRouter

from tests.fixture_app.viewset import CriteriaViewSet, GenreCriteriaViewSet

router = DefaultRouter()
router.register(r"criteria", CriteriaViewSet, basename="criteria")
router.register(r"genre-criteria", GenreCriteriaViewSet, basename="genre-criteria")

urlpatterns = router.urls
