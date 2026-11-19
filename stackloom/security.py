"""Password hashing, tokens and secret redaction."""
from __future__ import annotations

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id with OWASP's recommended minimum (m=19 MiB, t=2, p=1). The library
# default uses 64 MiB, which the dashboard process keeps after the first sign-in
# because the allocator does not return it; this keeps idle memory low.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

MIN_PASSWORD_LENGTH = 10

_REDACT_RULES = [
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1***:***@"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PWD|API_KEY|APIKEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIALS?)[A-Z0-9_]*\s*[=:]\s*)\S+"), r"\1***"),
    (re.compile(r"(sk-|sk_live_|sk_test_|ghp_|gho_|github_pat_|xox[bap]-)[A-Za-z0-9_-]{8,}"), r"\1***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1***"),
    (re.compile(r"AKIA[0-9A-Z]{12,}"), "AKIA***"),
]

_SECRET_KEY_NAME = re.compile(r"(?i)(TOKEN|SECRET|PASSWORD|PASSWD|PWD|KEY|CREDENTIAL|DSN|DATABASE_URL|_URL$)")

LOOKS_LIKE_CREDENTIAL = re.compile(
    r"(sk-[A-Za-z0-9_-]{12,}|ghp_[A-Za-z0-9]{12,}|github_pat_[A-Za-z0-9_]{12,}|AKIA[0-9A-Z]{12,}"
    r"|://(?!\$\{)[^/\s:@\"]+:(?!\$\{)[^/\s@\"]+@)"
)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str, password: str) -> bool:
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    return _hasher.check_needs_rehash(stored)


def password_problems(password: str, username: str = "") -> list[str]:
    problems = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if username and username.lower() in password.lower():
        problems.append("Do not include the username.")
    if password == "1234567890@":
        problems.append("Choose a password other than the first-run password.")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def redact(text: str) -> str:
    for pattern, replacement in _REDACT_RULES:
        text = pattern.sub(replacement, text)
    return text


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_KEY_NAME.search(name))
