from django.core.validators import URLValidator

HTTP_URL_VALIDATOR = URLValidator(schemes=["http", "https"])
