from rest_framework.routers import DefaultRouter

from tests.fixture_app.viewset import CriteriaViewSet

router = DefaultRouter()
router.register(r"criteria", CriteriaViewSet, basename="criteria")

urlpatterns = router.urls
