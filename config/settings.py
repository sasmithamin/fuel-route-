import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*" if DEBUG else "localhost").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "planner",
]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
}]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
STATIC_URL = "static/"

# The API is public and stateless: no sessions / auth, JSON only.
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

# Plan results are cached so a repeated trip costs 0 external calls.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                      "LOCATION": "fuelroute", "TIMEOUT": 60 * 60 * 24}}

# ---- Fuel planner configuration -------------------------------------------
FUEL = {
    "MAX_RANGE_MILES": 500,      # full-tank range
    "MPG": 10,
    "CORRIDOR_MILES": 10,        # a station counts as "on route" within this distance
    "RESAMPLE_STEP_MILES": 1.0,  # route is densified to this spacing for matching
    "OUTPUT_THIN_MILES": 0.25,   # geometry returned to the client is thinned to this spacing
    "MIN_SAVING_PER_GALLON": 0.0,# optional: minimum price difference ($/gal) to trigger a stop
}

# ---- External services (only the routing call is required) ----------------
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
HTTP_USER_AGENT = os.environ.get("HTTP_USER_AGENT", "fuelroute-assessment/1.0 (contact: blab67921@gmail.com)")
HTTP_TIMEOUT_SECONDS = 15