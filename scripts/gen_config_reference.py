"""Generate docs/CONFIGURATION.md — every environment variable the backend reads.

    venv/bin/python scripts/gen_config_reference.py          # rewrite the file
    venv/bin/python scripts/gen_config_reference.py --check  # exit 1 if stale

Application settings are read from `src/core/config.py` itself: the name, the
helper it is read with (required or optional, its type) and its default come
from the code, and the description is the comment written above it there, so
there is one place to explain a setting. Variables read outside config.py — by
the container's entrypoint, by run.py, by a job — are listed in OUTSIDE below,
and a test fails if the code starts reading one this file does not know.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "src" / "core" / "config.py"
OUT = ROOT / "docs" / "CONFIGURATION.md"

# name -> (where, description). Read by something other than core/config.py.
OUTSIDE = {
    "APP_ENV": ("config.py, entrypoint.sh", "Which `.secrets.toml` section Dynaconf loads: `dev`, `alembic` or `prod`. **Defaults to `prod`** — unset or misspelled silently targets production."),
    "BIND_HOST": ("run.py", "Address uvicorn binds. Default `127.0.0.1` (behind nginx, the only peer), `0.0.0.0` when `DEBUG` is on. Dev compose sets it so a published port reaches the app."),
    "TLS_MODE": ("entrypoint.sh", "`alb` (default: plain :80 behind a load balancer) or `container` (nginx terminates TLS; the live instance). Picks the nginx server template."),
    "TRUSTED_PROXY_CIDRS": ("entrypoint.sh", "Required with `TLS_MODE=alb`: the CIDRs allowed to set `X-Forwarded-For` (the VPC range). Anything wider hands the header back to the caller."),
    "PUBLIC_HOSTNAMES": ("entrypoint.sh", "Comma-separated host names nginx answers on :443 (and redirects from :80); any other `Host` gets 444. Unset answers every host. Only with `TLS_MODE=container`."),
    "RUN_MIGRATIONS": ("entrypoint.sh", "`true` runs `alembic upgrade head` before serving. Default `false`: migrations are a separate step (`<image> migrate`) so several instances never race the same upgrade."),
    "DATABASE_PORT": ("entrypoint.sh", "Port used when the entrypoint composes `DATABASE_URL` from parts. Default 5432."),
    "DATABASE_SSLMODE": ("entrypoint.sh", "Appended to the composed database URLs as `sslmode=` when set (RDS)."),
    "DATABASE_HOST_UNPOOLED": ("entrypoint.sh", "Host for the composed `DATABASE_URL_UNPOOLED` (migrations), when it differs from `DATABASE_HOST` (a pooler in front). Defaults to `DATABASE_HOST`."),
    "FIREBASE_AUTH_EMULATOR_HOST": ("firebase-admin, entrypoint.sh", "**Test and dev only.** Makes firebase-admin skip ID-token signature checks — anyone can authenticate as anyone. The production entrypoint refuses to start with it set."),
    "DATABASE_ENCRYPTION_KEY_OLD": ("jobs/rotateEncryptionKey.py", "Only for `rotate-encryption-key`: the key being rotated away from. See `operations.md`, \"Rotating the column encryption key\"."),
}

# Settings config.py reads without a comment above them.
BASIC = {
    "ENCRYPTION_KEY": "Key for the Fernet helpers in security/encryption.py. No column is encrypted with it (columns use DATABASE_ENCRYPTION_KEY).",
    "DATABASE_URL": "Connection URL the app uses — as `noharm_app`, the NOSUPERUSER/NOBYPASSRLS role, so RLS applies. The entrypoint composes it from the parts below when unset.",
    "DATABASE_HOST": "Database host, used by the entrypoint to compose the URLs.",
    "DATABASE_NAME": "Database name.",
    "DATABASE_USER": "The owner role (superuser in the live compose): migrations, dumps and `rotate-encryption-key` connect as it. Never the app's role.",
    "DATABASE_PASSWORD": "Password of DATABASE_USER.",
    "DATABASE_ENCRYPTION_KEY": "AES-GCM key for every encrypted column (StringEncryptedType). Losing it makes them unreadable; rotate with `rotate-encryption-key`. Must differ from BLIND_INDEX_KEY.",
    "DATABASE_URL_UNPOOLED": "Connection URL as the owner role, unpooled — Alembic and the jobs that must bypass RLS. pgBouncer cannot run DDL, hence unpooled.",
    "EXEC_MODE": "`dev` turns on development behaviour (tracebacks in 500s, DEBUG allowed); anything else — `prod`, `test` — is treated as not dev.",
    "DEBUG": "Development mode. **Refused at startup unless EXEC_MODE=dev**: Starlette serves its traceback page before any handler when it is on.",
    "PORT": "Port uvicorn listens on (8080 behind nginx).",
    "STATUS_CODES": "The shared status table, JSON: disabled 0, enabled 1, deleted 2, blocked 3, pending 4, accepted 5, ignored 6, unread 7, read 8, banned 9. The front end mirrors it as VITE_STATUS_CONSTANTS.",
    "JWT_SECRET_KEY": "Signing key for access tokens (15 min). Must differ from JWT_REFRESH_SECRET_KEY, or a refresh token passes as an access token.",
    "JWT_REFRESH_SECRET_KEY": "Signing key for refresh tokens (7 days).",
    "JWT_ALGORITHM": "JWT algorithm, `HS256`.",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "Access-token lifetime in minutes (15).",
    "REFRESH_TOKEN_EXPIRE_DAYS": "Refresh-token lifetime in days (7). Also how long a 'log out everywhere' cutoff is kept.",
    "ALLOWED_ORIGINS": "CORS allow-list, JSON. The web build is same-origin; the Capacitor apps need `capacitor://localhost` (iOS) and `https://localhost` (Android, plus `http://localhost` for older builds).",
    "REDIS_URL": "Redis: token blacklist and log-out-everywhere cutoffs, rate limits, quotas, socket presence and connection sets, the admin board cache.",
    "FIREBASE_SERVICE_ACCOUNT": "The Firebase service-account JSON as one string — verifies ID tokens, sends FCM pushes, deletes Firebase users on purge.",
    "FIREBASE_SERVICE_ACCOUNT_PATH": "Alternative to FIREBASE_SERVICE_ACCOUNT: a path to the JSON file.",
}

_ASSIGN = re.compile(
    r'self\.(?P<attr>[A-Z_]+)\s*:[^=]+=\s*(?P<call>_require(?:_int|_bool|_json)?|_optional(?:_int|_json)?|os\.environ\.get)\(\s*"(?P<name>[A-Z_0-9]+)"(?:\s*,\s*(?P<default>[^)]*))?\)'
)
_KIND = {
    "_require": ("required", "text"), "_require_int": ("required", "integer"),
    "_require_bool": ("required", "boolean"), "_require_json": ("required", "JSON"),
    "_optional": ("optional", "text"), "_optional_int": ("optional", "integer"),
    "_optional_json": ("optional", "JSON"), "os.environ.get": ("optional", "text"),
}


def _comment_above(lines, index):
    """The contiguous `#` block right above `index`, joined into prose.

    Section rules such as `# ── consent ──────` are decoration, not prose.
    """
    block = []
    i = index - 1
    while i >= 0 and lines[i].strip().startswith("#"):
        text = lines[i].strip().lstrip("#").strip()
        if not text.startswith("──"):
            block.insert(0, text)
        i -= 1
    return " ".join(b for b in block if b)


def _first_sentences(text, limit=320):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("; "))
    return (cut[: end + 1] if end > 80 else cut.rstrip() + "…")


def app_settings():
    lines = CONFIG.read_text().splitlines()
    rows, group_comment = [], ""
    for i, line in enumerate(lines):
        m = _ASSIGN.search(line)
        if not m:
            group_comment = ""
            continue
        above = _comment_above(lines, i)
        # Settings written on consecutive lines under one comment share it;
        # a blank line or any other statement ends the group.
        inherited = group_comment if i and _ASSIGN.search(lines[i - 1]) else ""
        # An explicit description wins over a comment merely inherited from
        # the setting above: the core block is written without blank lines.
        comment = above or BASIC.get(m["name"]) or inherited
        group_comment = above or inherited
        need, kind = _KIND[m["call"]]
        default = (m["default"] or "").strip()
        if need == "optional" and not default:
            default = "unset"
        rows.append((m["name"], need, kind, default, _first_sentences(comment)))
    return rows


def build():
    rows = app_settings()
    out = [
        "# Configuration reference",
        "",
        "<!-- Generated by scripts/gen_config_reference.py — do not edit by hand. -->",
        "",
        "Every environment variable the backend reads. Regenerate with",
        "`venv/bin/python scripts/gen_config_reference.py`;",
        "`tests/unit/core/test_configReference.py` fails while this file is stale.",
        "",
        "Locally the values come from `.secrets.toml` (section chosen by `APP_ENV`);",
        "in the container from `docker/prod.env`, whose commented template is",
        "`docker/prod.env.example`. Secrets are marked **secret**: never commit them,",
        "never log them.",
        "",
        f"## Application settings ({len(rows)}) — `src/core/config.py`",
        "",
        "The description is the comment above the setting in `config.py`; read it",
        "there for the full reasoning.",
        "",
        "| Variable | Required | Type | Default | What it is |",
        "|---|---|---|---|---|",
    ]
    secrets = {"ENCRYPTION_KEY", "DATABASE_ENCRYPTION_KEY", "BLIND_INDEX_KEY", "DATABASE_PASSWORD",
               "DATABASE_URL", "DATABASE_URL_UNPOOLED", "JWT_SECRET_KEY", "JWT_REFRESH_SECRET_KEY",
               "FIREBASE_SERVICE_ACCOUNT"}
    for name, need, kind, default, desc in rows:
        tag = " **secret**" if name in secrets else ""
        desc = desc.replace("|", "\\|") or "—"
        out.append(f"| `{name}`{tag} | {need} | {kind} | `{default}` | {desc} |" if default else
                   f"| `{name}`{tag} | {need} | {kind} | — | {desc} |")
    out += [
        "",
        f"## Read outside config.py ({len(OUTSIDE)})",
        "",
        "| Variable | Read by | What it is |",
        "|---|---|---|",
    ]
    for name, (where, desc) in sorted(OUTSIDE.items()):
        out.append(f"| `{name}` | {where} | {desc} |")
    out += [
        "",
        "## Front-end build variables",
        "",
        "The `VITE_*` values are the front end's, inlined into the bundle at build",
        "time; they are listed in `noHarm/README.md`, \"Environment variables\", and",
        "passed as build args by `docker/Dockerfile`, `docker/deploy-host.sh` and",
        "`.github/workflows/deploy.yml`.",
        "",
    ]
    return "\n".join(out)


def main():
    content = build()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text() != content:
            print("docs/CONFIGURATION.md is stale — run: venv/bin/python scripts/gen_config_reference.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(content)
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
