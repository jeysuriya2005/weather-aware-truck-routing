"""
Production configuration (Render): settings are read once at import, so each
case runs in a fresh interpreter with production-like environment variables.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

PRODUCTION_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings",
    "DJANGO_SECRET_KEY": "test-only-not-a-real-secret-0123456789abcdefghijklmnop",
    "DJANGO_DEBUG": "False",
    "DJANGO_ALLOWED_HOSTS": "api.example.com",
    "RENDER_EXTERNAL_HOSTNAME": "my-api.onrender.com",
    "DJANGO_BEHIND_HTTPS_PROXY": "True",
    "DJANGO_SECURE_SSL_REDIRECT": "True",
    "DJANGO_SECURE_HSTS_SECONDS": "3600",
    "CORS_ALLOWED_ORIGINS": "https://my-app.vercel.app",
    "CORS_ALLOWED_ORIGIN_REGEXES": r"^https://my-app-[a-z0-9-]+\.vercel\.app$",
    "DJANGO_NUM_PROXIES": "1",
    "TOMTOM_API_KEY": "",
}

PROBE = r"""
import json, django
django.setup()
from django.conf import settings
from django.test import Client
c = Client()
out = {
    "debug": settings.DEBUG,
    "allowed_hosts": settings.ALLOWED_HOSTS,
    "proxy_header": list(getattr(settings, "SECURE_PROXY_SSL_HEADER", []) or []),
    "ssl_redirect": settings.SECURE_SSL_REDIRECT,
    "hsts": settings.SECURE_HSTS_SECONDS,
    "cors": settings.CORS_ALLOWED_ORIGINS,
    "cors_regexes": settings.CORS_ALLOWED_ORIGIN_REGEXES,
    "num_proxies": settings.REST_FRAMEWORK["NUM_PROXIES"],
    "health_https_via_proxy": c.get("/api/health/", HTTP_HOST="my-api.onrender.com",
                                   HTTP_X_FORWARDED_PROTO="https").status_code,
    "health_body": c.get("/api/health/", HTTP_HOST="my-api.onrender.com",
                         HTTP_X_FORWARDED_PROTO="https").json(),
    "health_plain_http": c.get("/api/health/", HTTP_HOST="my-api.onrender.com").status_code,
    "health_bad_host": c.get("/api/health/", HTTP_HOST="evil.example.org",
                             HTTP_X_FORWARDED_PROTO="https").status_code,
    "cors_header": c.get("/api/health/", HTTP_HOST="my-api.onrender.com", HTTP_X_FORWARDED_PROTO="https",
                         HTTP_ORIGIN="https://my-app.vercel.app").headers.get("access-control-allow-origin"),
    "cors_other_origin": c.get("/api/health/", HTTP_HOST="my-api.onrender.com", HTTP_X_FORWARDED_PROTO="https",
                               HTTP_ORIGIN="https://attacker.example").headers.get("access-control-allow-origin"),
}
print(json.dumps(out))
"""


def run(env_overrides, code=PROBE):
    # Start from a clean environment so backend/.env values cannot leak in for
    # any variable set here (django-environ never overrides existing variables).
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "CORS_", "TOMTOM_", "RENDER"))}
    env.update(env_overrides)
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60)


def test_production_settings_and_health_with_debug_off():
    result = run(PRODUCTION_ENV)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["debug"] is False
    assert out["allowed_hosts"] == ["api.example.com", "my-api.onrender.com"]
    assert out["proxy_header"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert out["ssl_redirect"] is True and out["hsts"] == 3600
    assert out["cors"] == ["https://my-app.vercel.app"]
    assert out["cors_regexes"] == [r"^https://my-app-[a-z0-9-]+\.vercel\.app$"]
    assert out["num_proxies"] == 1
    assert out["health_https_via_proxy"] == 200
    assert out["health_body"] == {"status": "ok", "service": "weather-aware-truck-routing"}
    assert out["health_plain_http"] == 301  # redirected to HTTPS
    assert out["health_bad_host"] == 400  # DisallowedHost
    assert out["cors_header"] == "https://my-app.vercel.app"
    assert out["cors_other_origin"] is None


def test_missing_secret_key_refuses_to_start():
    env = dict(PRODUCTION_ENV, DJANGO_SECRET_KEY="")
    result = run(env, "import django; django.setup()")
    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY is not set" in result.stderr


def test_wsgi_application_loads_in_production_mode():
    result = run(PRODUCTION_ENV, "from config.wsgi import application; print(type(application).__name__)")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "WSGIHandler"


def test_deploy_check_has_only_the_documented_hsts_advisories():
    # W005 (HSTS includeSubDomains) and W021 (HSTS preload) are deliberately left off:
    # on a *.onrender.com hostname you do not control the parent domain, and preload
    # is a permanent browser-list commitment for a domain you own. Anything else fails.
    result = run(PRODUCTION_ENV, "from django.core.management import execute_from_command_line; "
                                 "execute_from_command_line(['manage.py', 'check', '--deploy'])")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    issues = {line.split(")")[0].split("(")[-1] for line in output.splitlines() if line.startswith("?: (")}
    assert issues <= {"security.W005", "security.W021"}, output
    assert "ERRORS" not in output
