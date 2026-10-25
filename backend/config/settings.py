"""
Django settings for the Weather-Aware Truck Routing API.

All secrets and deployment-specific values come from environment variables
(optionally loaded from backend/.env, which is git-ignored). See .env.example.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    # Local-development default only; production sets DJANGO_ALLOWED_HOSTS.
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGIN_REGEXES=(list, []),
    DJANGO_BEHIND_HTTPS_PROXY=(bool, False),
    DJANGO_SECURE_SSL_REDIRECT=(bool, False),
    DJANGO_SECURE_HSTS_SECONDS=(int, 0),
)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

DEBUG = env("DJANGO_DEBUG")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is not set. Copy .env.example to .env and set it.")

ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
# Render sets RENDER_EXTERNAL_HOSTNAME (e.g. my-api.onrender.com) automatically.
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# --- HTTPS behind a TLS-terminating proxy (Render, most PaaS) ------------------
# Opt-in: trusting X-Forwarded-Proto is only safe when a proxy always sets it,
# and SECURE_SSL_REDIRECT without it causes a redirect loop behind such a proxy.
if env("DJANGO_BEHIND_HTTPS_PROXY"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env("DJANGO_SECURE_SSL_REDIRECT")
SECURE_HSTS_SECONDS = env("DJANGO_SECURE_HSTS_SECONDS")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
# The API is stateless JSON: no cookies, sessions or authentication, so there is
# nothing for CSRF protection to protect (Django's deploy check W003).
SILENCED_SYSTEM_CHECKS = ["security.W003"]

# Third-party provider credentials. Server-side only: never returned in API
# responses and never sent to the frontend. Used from Phase 2 onwards.
TOMTOM_API_KEY = env("TOMTOM_API_KEY", default="")


INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # Plan responses carry route geometry plus 49 heatmap frames; JSON compresses ~8x.
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# The API is stateless: no models, sessions or user accounts.
DATABASES = {}

# Per-process cache for forecast responses (one entry per location and window)
# and throttle counters. The default 300-entry cap is too small for a trip's
# ~200-500 forecast locations.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "OPTIONS": {"MAX_ENTRIES": 10_000},
    }
}

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "EXCEPTION_HANDLER": "trips.api_errors.api_exception_handler",
    # Per-client limits protect the shared TomTom free-tier quota.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"geocode": "60/min", "trip_plan": "10/min"},
    # Proxies in front of the app that append to X-Forwarded-For. Unset (None):
    # DRF uses the whole header when present. Behind one appending proxy, 1 makes
    # DRF use the address that proxy added (clients cannot spoof it).
    "NUM_PROXIES": env.int("DJANGO_NUM_PROXIES", default=None),
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"trips": {"handlers": ["console"], "level": "INFO"}},
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
# Optional, e.g. for Vercel preview deployments: ^https://my-app-[a-z0-9-]+\.vercel\.app$
CORS_ALLOWED_ORIGIN_REGEXES = env("CORS_ALLOWED_ORIGIN_REGEXES")

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
