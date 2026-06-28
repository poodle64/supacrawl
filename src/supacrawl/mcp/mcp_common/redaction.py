"""Unified credential and PII redaction for MCP server payloads.

Goal: replace credential-bearing values in tool responses BEFORE they reach
the LLM context. Built around three classification layers applied during
recursive walking:

1. **Regex-based key matcher** — the `DEFAULT_SECRET_KEYS_REGEX` pattern
   tests every dict key (after lowercase + alphanumeric-only normalisation)
   against a lexicon of credential nouns and PII identifiers. Compound
   forms (`smtp_password`, `master_password_hash`, `_admin_token`,
   `accessToken`) match via word-boundary alternation; the old exact-string
   matcher could not see them.
2. **Exclusion set** — `DEFAULT_NORMALISED_EXCLUDED_KEYS` carves out benign
   compound forms whose normalised name would otherwise match the regex
   (e.g. `signature_algorithm` contains `signature`; `country_code` ends
   in `code`). These pass through unmasked.
3. **Value-shape detector** — `_looks_like_high_entropy_token` catches
   credential-shaped string values (JWT, ``Bearer <opaque>``, long hex or
   base64) when they appear under a benign key. Defence-in-depth against
   key-name evasion.

Headers and URL query strings are handled by the same regex (header NAMES
flow through `is_sensitive_key`; URL query keys ditto). The full HTTP
header set (`Authorization`, `Cookie`, `Set-Cookie`, `X-Auth-Token`,
`Cf-Authorization`, etc.) is also held as `DEFAULT_SECRET_HEADER_NAMES`
for the headers-first path.

Sentinel format: ``<redacted, N chars>`` where N preserves the original
string length so the agent can confirm the field exists and roughly how
long the secret is (useful for rotation sanity-checking). Bytes are
reported with `bytes`; None with `null`; other scalars by type name.

Public surface:

    DEFAULT_SECRET_KEYS_REGEX     compiled re.Pattern (key-name lexicon)
    DEFAULT_NORMALISED_EXCLUDED_KEYS  frozenset[str] (benign compound forms)
    DEFAULT_SECRET_HEADER_NAMES   frozenset[str] (lowercased HTTP header names)
    DEFAULT_SECRET_KEYS           DEPRECATED frozenset[str] (use the regex)
    Redactor                      dataclass exposing redact_dict / redact_text /
                                  redact_html / redact_headers / redact_url
    make_redactor()               factory returning a Redactor instance
    make_masker()                 BACK-COMPAT shim returning a `mask(payload, reveal)`
    redact_secrets()              BACK-COMPAT free function
    is_sensitive_key()            single-key predicate
    looks_like_form_body()        sniffer for application/x-www-form-urlencoded

Usage::

    from .redaction import make_masker

    mask_secrets = make_masker({"vw_admin", "client_secret"})
    return mask_secrets(payload, reveal=reveal_secrets)
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


def _sentinel(value: Any) -> str:
    """Return a length-preserving redaction sentinel for ``value``.

    The agent must still be able to tell the field existed and roughly
    how much data was masked (useful for confirming rotations actually
    changed the underlying value).
    """
    if value is None:
        return "<redacted, null>"
    if isinstance(value, str):
        return f"<redacted, {len(value)} chars>"
    if isinstance(value, (bytes, bytearray)):
        return f"<redacted, {len(value)} bytes>"
    return f"<redacted, {type(value).__name__}>"


# ---------------------------------------------------------------------------
# Key lexicon
# ---------------------------------------------------------------------------

# Compiled regex matched against the normalised (lowercased, alphanumeric-only)
# dict key. Combines two strategies:
#
# 1. Bare nouns under \b...\b boundaries (the legacy form). Matches `password`
#    at word edges; does NOT match inside `passwords` plural.
# 2. Explicit compound forms listed without \b boundaries. Catches
#    `smtppassword` (from `smtp_password`), `accesstoken` (from `accessToken`)
#    and `masterpasswordhash` where the bare-noun form misses because the
#    normalised key has no boundary separator.
#
# The exclusion set guards against the few remaining false-positives
# (`signature_algorithm`, `country_code`).
_CREDENTIAL_KEYS_REGEX: re.Pattern[str] = re.compile(
    r"""(?xi)
    \b(
        password
      | passwd
      | pwd
      | secret
      | secrets
      | privatekey
      | apikey
      | token
      | bearer
      | authorization
      | credential
      | credentials
      | csrf
      | xsrf
      | sessionid
      | sessionkey
      | session
      | pin
      | otp
      | totp
      | mfa
      | mfacode
      | verifier
      | verificationcode
      | confirmationcode
      | securitycode
      | accesscode
      | devicefingerprint
      | fingerprint
      | authcode
      | jwt
      | assertion
      | nonce
      | signature
      | sig
      | mac
      | hmac
      | skey                       # Duo Security secret key
      | ikey                       # Duo Security integration key (pairs with skey)
      # ---- Bitwarden / encrypted-vault material (audit C-4, B-1, B-4)
      | admintoken
      | vwadmin
      | masterpassword
      | masterpasswordhash
      | masterpasswordhint
      | securitystamp
      | akey
      | recoverycode
      | recoverycodes
      | twofactorrecoverycode
      | kdfiterations
      | kdfmemory
      | kdfparallelism
      | keyencrypted
      # ---- Secure-content additions (audit B-3) -----------------------
      | seedphrase
      | mnemonic
      # ---- Compound forms with no internal separator after normalisation
      | accesstoken
      | refreshtoken
      | idtoken
      | sessiontoken
      | authtoken
      | apitoken
      | firebasetoken
      | tabsessionid
      | clientsecret
      | secretkey
      | codeverifier
      # ---- SMTP send credentials (Bitwarden admin config) -----------
      # The username is paired with smtp_password; losing it lets an
      # attacker bind a sender address to the same SMTP relay.
      | smtpusername
      | smtpuser
      # ---- Database DSN / connection strings --------------------------
      # Routinely embed `user:password@host` in a single string; treat
      # the whole value as a credential.
      | databaseurl
      | dsn
      | connectionstring
      | connectionurl
    )\b
    """
)


# PII / identifier matcher. Used by callers that opt into PII redaction
# (browser-driver, bitwarden). Conservative servers stay on the
# credential matcher alone.
_PII_KEYS_REGEX: re.Pattern[str] = re.compile(
    r"""(?xi)
    \b(
      # PII identifier keys (bare nouns)
        memberid
      | customerid
      | subscriberid
      | accountid
      | loyaltyid
      | policyid
      | bookingid
      | reservationid
      | pnr
      | frequentflyer
      | frequentflyernumber
      | frequentflyerid
      | employeeid
      | contactid
      | userid
      # Direct PII keys
      | email
      | emailaddress
      | phone
      | phonenumber
      | mobile
      | mobilenumber
      | dob
      | dateofbirth
      | birthdate
      | birthday
      | tfn
      | ssn
      | address
      | streetaddress
      | postcode
      | postalcode
      | zipcode
      | surname
      | lastname
      | firstname
      | givenname
      | middlename
      | fullname
      | familyname
      | preferredusername
      | username
      | nationalid
      | passport
      | passportnumber
      | medicare
      | medicarenumber
      | driverlicence
      | driverslicence
      | driverlicense
      | driverslicense
      | taxfilenumber
    )\b
    """
)


# Substring-match credential forms (no word boundaries): catches concatenated
# compounds like `hibpapikey` where the bare-noun `\b...\b` boundary fails
# because the original separator was dropped during normalisation. Listed
# without word boundaries; the compact form must contain one of these
# verbatim.
_COMPOUND_CREDENTIAL_SUBSTRING_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(apikey|accesstoken|refreshtoken|authtoken|idtoken|sessiontoken"
    r"|apitoken|firebasetoken|tabsessionid|clientsecret|secretkey|privatekey"
    r"|codeverifier|admintoken|masterpassword|securitystamp|recoverycode"
    r"|kdfiterations)"
)


# Tail-anchored match against the dotted (.) normalised form: the noun must
# be either the whole key or a trailing dotted segment. This catches
# `smtp.password` (->smtp_password) but NOT `credentials.risk.report` because
# `credentials` is a leading segment with non-credential trail.
_CREDENTIAL_TAIL_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(^|\.)("
    r"password|passwd|pwd|secret|secrets|privatekey|apikey|token|bearer"
    r"|authorization|credential|credentials|csrf|xsrf|sessionid|sessionkey"
    r"|session|pin|otp|totp|mfa|mfacode|verifier|verificationcode"
    r"|confirmationcode|securitycode|accesscode|devicefingerprint|fingerprint"
    r"|authcode|jwt|assertion|nonce|signature|sig|mac|hmac|skey|ikey|salt"
    r"|admintoken|vwadmin|masterpassword|masterpasswordhash|masterpasswordhint"
    r"|securitystamp|akey|recoverycode|recoverycodes|twofactorrecoverycode"
    r"|kdfiterations|kdfmemory|kdfparallelism|keyencrypted|seedphrase|mnemonic"
    r"|accesstoken|refreshtoken|idtoken|sessiontoken|authtoken|apitoken"
    r"|firebasetoken|tabsessionid|clientsecret|secretkey|codeverifier"
    r"|smtpusername|smtpuser|databaseurl|dsn|connectionstring|connectionurl"
    r")$"
)


_PII_TAIL_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(^|\.)("
    r"memberid|customerid|subscriberid|accountid|loyaltyid|policyid"
    r"|bookingid|reservationid|pnr|frequentflyer|frequentflyernumber"
    r"|frequentflyerid|employeeid|contactid|userid"
    r"|email|emailaddress|phone|phonenumber|mobile|mobilenumber|dob"
    r"|dateofbirth|birthdate|birthday|tfn|ssn|address|streetaddress"
    r"|postcode|postalcode|zipcode|surname|lastname|firstname|givenname"
    r"|middlename|fullname|familyname|preferredusername|username|nationalid"
    r"|passport|passportnumber|medicare|medicarenumber|driverlicence"
    r"|driverslicence|driverlicense|driverslicense|taxfilenumber"
    r"|id|number|ref|reference|no"
    r")$"
)


# Substring-match PII forms (no word boundaries): catches concatenated
# compound PII identifier forms.
_COMPOUND_PII_SUBSTRING_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(memberid|customerid|subscriberid|accountid|loyaltyid|policyid"
    r"|bookingid|reservationid|frequentflyer|employeeid|contactid|userid"
    r"|membernumber|customernumber|accountnumber|policynumber|policyno"
    r"|customerref|customerreference|memberref|accountref|loyaltyref|policyref"
    r"|reservationref|referenceid|referencenumber"
    r"|bookingref|bookingnumber|bookingreference|reservationnumber|reservationno"
    r"|loyaltynumber|frequentflyernumber"
    r"|emailaddress|phonenumber|dateofbirth|familyname|firstname|lastname"
    r"|surname|fullname|preferredusername|passportnumber|medicarenumber"
    r"|driverlicence|driverlicense|driverslicence|driverslicense"
    r"|nationalid|taxfilenumber)"
)


# Default regex used by ``is_sensitive_key`` for back-compat callers
# (credentials only - the conservative floor).
DEFAULT_SECRET_KEYS_REGEX: re.Pattern[str] = _CREDENTIAL_KEYS_REGEX


# Normalised key names that MUST NOT redact even though they substring-match
# the regex. These are benign compound forms where a credential or PII noun
# appears as part of an algorithm name, diagnostic identifier, or closed-set
# code (country/IATA/currency/...).
DEFAULT_NORMALISED_EXCLUDED_KEYS: frozenset[str] = frozenset(
    {
        # Closed-set codes (alpha codes, never credentials).
        "countrycode",
        "iatacode",
        "currencycode",
        "statuscode",
        "errorcode",
        "httpcode",
        "airportcode",
        "airlinecode",
        "langcode",
        "languagecode",
        "regioncode",
        "localecode",
        "timezonecode",
        "areacode",
        "zonecode",
        "unitcode",
        "categorycode",
        # Diagnostic identifiers (the operator needs to see these end-to-end).
        # sessionid covers trace-correlation session UUIDs (Langfuse, OTEL, etc.),
        # not HTTP session cookie headers (e.g. x-session-id stays in DEFAULT_SECRET_HEADER_NAMES).
        "correlationid",
        "requestid",
        "sessionid",
        "traceid",
        "spanid",
        "transactionid",
        # Algorithm / method names containing "signature" / "mac" as a noun.
        "signaturealgorithm",
        "signaturemethod",
        "macaddress",
        "nonceinterval",
        # NOTE: kdf_iterations is DELIBERATELY NOT excluded. Audit B-9
        # established that the KDF iteration count, paired with the master
        # password hash, enables offline brute-force; redacting it is the
        # right default. Future contributors: do not add `kdfiterations`,
        # `kdfmemory`, or `kdfparallelism` to this set.
    }
)


# HTTP header names (lowercased) that ALWAYS redact regardless of any other
# layer. Union of browser-driver's `SENSITIVE_HEADER_NAMES` and bitwarden's
# `_SECRET_HEADER_KEYS`. Vendor-specific headers (e.g. `X-Vault-Token`,
# `X-Stripe-Signature`, `X-Csrf-Token`) match through `is_sensitive_key`
# against the same regex; this set is the explicit floor.
DEFAULT_SECRET_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "x-auth-token",
        "x-api-key",
        "x-session-id",
        "x-csrf-token",
        "cf-authorization",
        "bearer",
        "proxy-authorization",
    }
)


# Header-name tail regex: catches vendor-convention headers whose final
# dotted segment is a bare credential noun ("X-Vendor-Auth" -> "x.vendor.auth"
# whose tail is "auth"). Bare "auth" is DELIBERATELY NOT in the dict-key
# regex above because dict keys often carry `auth_type`, `auth_method`, etc.
# that are not themselves credentials. Headers have a tighter convention:
# `Something-Auth` headers carry the actual credential value.
_HEADER_TAIL_REGEX: re.Pattern[str] = re.compile(
    r"(?i)(^|\.)("
    r"auth"
    r")$"
)


# URL query-parameter keys that redact in addition to the credential matcher.
# These are query-string-only because their bare form is too broad for the
# dict-key matcher. Membership is tested against the compact-normalised key
# (`_normalise_key_compact`), so separator and case variants all match.
#
# `code` covers the OAuth authorisation code: callback URLs land in network
# captures as `?code=AUTHCODE&state=...`. It is NOT added to the dict-key
# regex because that would over-redact diagnostic dict fields like
# `country_code`, `status_code`, `error_code` that legitimately appear in
# tool responses.
#
# `sessionid` covers HTTP session tokens carried in URL query strings
# (e.g. `?sessionId=abc`, `?session_id=abc`, `?SESSIONID=abc`). It must be
# overridden at THIS layer (and only here) because `is_sensitive_key`
# deliberately keeps `sessionid` in DEFAULT_NORMALISED_EXCLUDED_KEYS so that
# trace-correlation session UUIDs (Langfuse, OTEL, etc.) in JSON BODIES stay
# unredacted. That body-context exclusion fires BEFORE the extra_keys override
# can take effect, so extra_keys cannot re-enable it; the URL-query set is the
# only correct override point for the URL-credential case.
_URL_QUERY_CREDENTIAL_KEYS: frozenset[str] = frozenset({"code", "sessionid"})


# Deprecated. Retained as a frozenset of bare credential nouns so any caller
# grepping for keys still finds them. New code uses DEFAULT_SECRET_KEYS_REGEX.
DEFAULT_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "apikey",
        "access_token",
        "auth_token",
        "authorization",
        "bearer",
        "credential",
        "credentials",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_key",
        "token",
    }
)


# ---------------------------------------------------------------------------
# Key classification
# ---------------------------------------------------------------------------


_CAMEL_BOUNDARY_RE = re.compile(r"([a-z0-9])([A-Z])")


def _normalise_key(key: str) -> str:
    """Normalise ``key`` to a delimiter-rich lowercase form.

    Inserts a dot at camelCase transitions, then replaces every
    non-alphanumeric character with a dot, then lowercases. ``.`` is
    NOT a Python regex word character, so ``\\bpassword\\b`` correctly
    matches the bare noun across the dot boundary.

    ``access-token``, ``access_token`` and ``accessToken`` all
    normalise to ``access.token`` — one regex matches them all, while
    ``tokens`` (plural) does NOT match ``\\btoken\\b``.

    Returns:
        Lowercased string with non-alphanumerics and camelCase
        boundaries replaced by dots.
    """
    # Insert . at lowercase-then-uppercase boundaries: accessToken -> access.Token
    expanded = _CAMEL_BOUNDARY_RE.sub(r"\1.\2", key)
    expanded = expanded.lower()
    # Replace every non-alphanumeric with . so the word-boundary regex works.
    return re.sub(r"[^a-z0-9]+", ".", expanded).strip(".")


def _normalise_key_compact(key: str) -> str:
    """Lowercase + strip non-alphanumerics; used for exclusion-set lookup.

    The exclusion table is keyed on the old `mac_address` -> `macaddress`
    shape, so the compact form is still needed for that one lookup.
    """
    return "".join(c for c in key.lower() if c.isalnum())


def _matches(key: str, secret_keys: frozenset[str]) -> bool:
    """Back-compat shim: case- and separator-insensitive key membership test.

    Mirrors the legacy ``key.lower().replace("-", "_") in secret_keys`` check
    so existing servers (e.g. servarr) that import ``_matches`` directly
    continue to function. New callers should use :func:`is_sensitive_key`.
    """
    normalised = key.lower().replace("-", "_")
    return normalised in secret_keys


def is_sensitive_key(
    key: str,
    extra_keys: frozenset[str] | None = None,
    extra_exclusions: frozenset[str] | None = None,
    pii: bool = False,
) -> bool:
    """Return True if ``key`` names a credential or PII field.

    ``extra_keys`` are additional normalised key names (compact form, no
    separators) that must redact even if the regex misses them.
    ``extra_exclusions`` are additional compact-form keys that must NOT
    redact even if the regex matches. ``pii=True`` enables the broader
    PII identifier matcher (email, phone, member_id, etc.).
    """
    normalised = _normalise_key(key)
    compact = _normalise_key_compact(key)
    if not normalised:
        return False
    exclusions = DEFAULT_NORMALISED_EXCLUDED_KEYS
    if extra_exclusions:
        exclusions = exclusions | extra_exclusions
    if compact in exclusions:
        return False
    if extra_keys and compact in extra_keys:
        return True
    # Match against both forms: the dotted form catches separator-rich keys
    # like ``api_key`` -> ``api.key`` where the bare-noun \b...\b boundaries
    # work; the compact form catches concatenated forms like ``accessToken``
    # -> ``accesstoken`` where there is no separator.
    # Credential matcher operates against the dotted form so the noun must
    # appear as a discrete segment ("smtp.password" matches; the envelope
    # "credentials.risk.report" does not because the dotted form treats
    # credentials as an envelope prefix when it is followed by a non-
    # credential trail. The test runs against tail-anchored alternatives:
    # the noun must be the LAST dotted segment OR the entire key.
    if _CREDENTIAL_TAIL_REGEX.search(normalised):
        return True
    if _CREDENTIAL_KEYS_REGEX.search(compact):
        return True
    if _COMPOUND_CREDENTIAL_SUBSTRING_REGEX.search(compact):
        return True
    if pii and _PII_TAIL_REGEX.search(normalised):
        return True
    if pii and _PII_KEYS_REGEX.search(compact):
        return True
    if pii and _COMPOUND_PII_SUBSTRING_REGEX.search(compact):
        return True
    return False


# ---------------------------------------------------------------------------
# Value-shape detectors
# ---------------------------------------------------------------------------

_JWT_REGEX: re.Pattern[str] = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
_BEARER_PREFIX_REGEX: re.Pattern[str] = re.compile(r"^bearer\s+\S+$", re.IGNORECASE)
_BASE64_TOKEN_REGEX: re.Pattern[str] = re.compile(r"^[A-Za-z0-9+/=_\-]+$")
_HEX_TOKEN_REGEX: re.Pattern[str] = re.compile(r"^[a-f0-9]+$", re.IGNORECASE)


def _shannon_entropy(s: str) -> float:
    """Return the Shannon entropy (bits per character) of ``s``."""
    if not s:
        return 0.0
    counts = Counter(s)
    length = len(s)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _looks_like_high_entropy_token(value: str) -> bool:
    """Return True if ``value`` looks like a credential token by shape.

    Catches three concrete cases the key-name matcher cannot see:

    - JWT (``eyJ...``): the structure is unambiguous.
    - ``Bearer <opaque>`` prefix: a credential that wandered into a
      free-text field.
    - High-entropy long base64 or hex: at least 32 characters, mixed
      letters/digits, Shannon entropy above 4.0 bits/char.

    A short alphanumeric value (``AU``, ``BNE``, ``AUD``) does not trip
    the detector; it has too few characters and the entropy threshold
    rules it out.
    """
    if not value:
        return False
    if _JWT_REGEX.fullmatch(value):
        return True
    if _BEARER_PREFIX_REGEX.match(value):
        return True
    length = len(value)
    if length < 32:
        return False
    if _HEX_TOKEN_REGEX.match(value):
        return True
    if not _BASE64_TOKEN_REGEX.match(value):
        return False
    has_letter = any(c.isalpha() for c in value)
    has_digit = any(c.isdigit() for c in value)
    if not (has_letter and has_digit):
        return False
    if _shannon_entropy(value) < 4.0:
        return False
    return True


# Pattern for inline credentials embedded in text/HTML (snapshots, ARIA trees,
# script blocks). Matched independently of dict-key context.
_INLINE_JWT_REGEX: re.Pattern[str] = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_INLINE_BEARER_REGEX: re.Pattern[str] = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{20,}", re.IGNORECASE)
# Candidate substrings that may be high-entropy tokens. The candidate alphabet
# matches the base64-url and hex shapes the value-shape detector recognises;
# each match is gated by ``_looks_like_high_entropy_token`` so prose words and
# short alphanumeric tokens pass through unredacted.
_INLINE_HIGH_ENTROPY_REGEX: re.Pattern[str] = re.compile(r"[A-Za-z0-9+/=_\-]{32,}")


# Sniff for application/x-www-form-urlencoded bodies.
_FORM_BODY_REGEX: re.Pattern[str] = re.compile(
    r"^[A-Za-z0-9_.\-%+]+=[A-Za-z0-9_.\-%+]*(&[A-Za-z0-9_.\-%+]+=[A-Za-z0-9_.\-%+]*)*$"
)


def looks_like_form_body(text: str) -> bool:
    """Return True if ``text`` parses cleanly as form-encoded body."""
    if not text:
        return False
    return bool(_FORM_BODY_REGEX.match(text))


# ---------------------------------------------------------------------------
# Redactor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Redactor:
    """Encapsulates a redaction policy.

    ``extra_keys`` and ``extra_exclusions`` are normalised key names
    (lowercase, alphanumeric-only) that augment the default lexicon.
    ``extra_headers`` is a set of lowercased HTTP header names that
    always redact in addition to ``DEFAULT_SECRET_HEADER_NAMES``.
    ``pii=True`` activates the PII identifier matcher (email, phone,
    member_id, etc.) on top of the credential matcher.
    ``value_shape_exempt_keys`` is a frozenset of compact-normalised key
    names whose values are exempt from the value-entropy heuristic
    (``_looks_like_high_entropy_token``). The key-name lexicon still applies:
    a key in both the sensitive lexicon and this set is redacted by the
    key-name layer, not passed through. Has no effect on the text/HTML/form
    scanning paths (``redact_text``, ``redact_html``, ``redact_form_text``),
    which have no structured key context.

    The bypass applies only to the **immediate string value** of the named
    key in ``_walk``. List/tuple items under that key and nested dict keys
    beneath it are evaluated under their own names and remain subject to the
    value-shape detector.
    """

    extra_keys: frozenset[str] = field(default_factory=frozenset)
    extra_exclusions: frozenset[str] = field(default_factory=frozenset)
    extra_headers: frozenset[str] = field(default_factory=frozenset)
    pii: bool = False
    value_shape_exempt_keys: frozenset[str] = field(default_factory=frozenset)

    # ----- key classification -------------------------------------------------

    def is_sensitive_key(self, key: str) -> bool:
        return is_sensitive_key(key, self.extra_keys, self.extra_exclusions, pii=self.pii)

    def _is_sensitive_header_name(self, name: str) -> bool:
        lower = name.lower()
        if lower in DEFAULT_SECRET_HEADER_NAMES or lower in self.extra_headers:
            return True
        # Header NAMES also flow through the body regex so vendor headers
        # like X-Vault-Token, X-Stripe-Signature, X-Account-Key match.
        if self.is_sensitive_key(name):
            return True
        # Header-only tail check: vendor-convention `X-Foo-Auth: <token>`
        # carries a credential whose noun is bare `auth`. Bare `auth` is
        # not in the dict-key regex (too broad for `auth_type` etc.) but
        # is appropriate in a header-name context where the convention
        # tightens the meaning.
        normalised = _normalise_key(name)
        return bool(normalised and _HEADER_TAIL_REGEX.search(normalised))

    # ----- dict / list walker -------------------------------------------------

    def redact_dict(self, payload: Any, *, reveal: bool = False) -> Any:
        """Walk ``payload`` recursively and replace credential / PII values.

        Returns a new structure; the original is not mutated.
        """
        if reveal:
            return payload
        return self._walk(payload)

    def _walk(self, value: Any, parent_key: str | None = None) -> Any:
        if isinstance(value, dict):
            result: dict[Any, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and self.is_sensitive_key(k):
                    result[k] = _sentinel(v)
                else:
                    result[k] = self._walk(v, parent_key=k if isinstance(k, str) else None)
            return result
        if isinstance(value, list):
            # parent_key is intentionally reset to None for list/tuple items: the
            # exemption applies only to the IMMEDIATE string value of a named dict
            # key, not to items in a list or tuple under that key.
            return [self._walk(item, parent_key=None) for item in value]
        if isinstance(value, tuple):
            return tuple(self._walk(item, parent_key=None) for item in value)
        if isinstance(value, str):
            if (
                parent_key is not None
                and self.value_shape_exempt_keys
                and _normalise_key_compact(parent_key) in self.value_shape_exempt_keys
            ):
                # Bypasses ALL value-shape heuristics (currently
                # _looks_like_high_entropy_token; any future value-shape detector
                # added below this guard would also be skipped). The key-name lexicon
                # still fires before _walk reaches this branch, so sensitive key names
                # always win regardless of the exempt set.
                #
                # This bypass applies only to the immediate string value of the exempt
                # key, not to nested dicts or lists under it: when value is a dict, the
                # code enters the dict branch above and walks the nested keys under their
                # own names; when value is a list, parent_key is reset to None above.
                return value
            if _looks_like_high_entropy_token(value):
                return _sentinel(value)
        return value

    # ----- headers ------------------------------------------------------------

    def redact_headers(
        self,
        headers: dict[str, str] | list[tuple[str, str]] | list[dict[str, str]],
        *,
        reveal: bool = False,
    ) -> dict[str, str]:
        """Mask credential-carrying header values; preserve all keys.

        Accepts a ``{name: value}`` dict, a list of ``(name, value)`` pairs,
        or HAR-style ``[{"name": ..., "value": ...}, ...]``. Returns a flat
        ``{name: value}`` dict.
        """
        items: list[tuple[str, str]]
        if isinstance(headers, dict):
            items = list(headers.items())
        else:
            items = []
            for entry in headers:
                if isinstance(entry, dict):
                    items.append((entry["name"], entry["value"]))
                else:
                    items.append((entry[0], entry[1]))

        if reveal:
            return dict(items)

        result: dict[str, str] = {}
        for name, value in items:
            if self._is_sensitive_header_name(name):
                result[name] = _sentinel(value)
            else:
                result[name] = value
        return result

    # ----- URL ----------------------------------------------------------------

    def redact_url(self, url: str, *, reveal: bool = False) -> str:
        """Mask credential-bearing query parameter values in ``url``.

        URL query parameters named ``code`` are OAuth authorisation codes by
        convention and are redacted here even though ``code`` is not in the
        dict-key keyset (where it would over-redact diagnostic fields like
        ``country_code`` and ``status_code``). The ``sessionid`` key (and its
        separator/case variants ``session_id``, ``SESSION_ID``, ``sessionId``)
        is likewise a URL-credential case excluded from the body-context
        matcher deliberately. Both are matched via compact normalisation
        (``_normalise_key_compact``: strips separators, lowercases) so all
        separator and case variants are caught.
        """
        if reveal or not url:
            return url
        try:
            parsed = urlparse(url)
        except ValueError:
            return url
        if not parsed.query and not parsed.fragment:
            return url
        new_query = parsed.query
        if parsed.query:
            masked_pairs = [
                (
                    key,
                    _sentinel(value)
                    if (self.is_sensitive_key(key) or _normalise_key_compact(key) in _URL_QUERY_CREDENTIAL_KEYS)
                    else value,
                )
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            ]
            new_query = urlencode(masked_pairs, safe="*<>, ")
        # OAuth implicit-flow callbacks deliver tokens in the fragment
        # (e.g. #access_token=eyJ...). Apply the same key-based masking.
        new_fragment = parsed.fragment
        if parsed.fragment:
            frag_pairs = [
                (
                    key,
                    _sentinel(value)
                    if (self.is_sensitive_key(key) or _normalise_key_compact(key) in _URL_QUERY_CREDENTIAL_KEYS)
                    else value,
                )
                for key, value in parse_qsl(parsed.fragment, keep_blank_values=True)
            ]
            new_fragment = urlencode(frag_pairs, safe="*<>, ")
        return urlunparse(parsed._replace(query=new_query, fragment=new_fragment))

    # ----- text body (snapshot / ARIA / script payload) -----------------------

    def redact_text(self, text: str | None, *, reveal: bool = False) -> str | None:
        """Mask JWT, Bearer-prefixed, and high-entropy tokens inline.

        Used for snapshot text, accessibility-tree dumps, and any other
        free-form text where credentials may have leaked into prose.
        High-entropy candidates (32+ characters from the base64-url or
        hex alphabets) are gated by ``_looks_like_high_entropy_token`` so
        prose and short identifiers pass through unredacted; long hex runs
        and base64-url tokens are redacted by deliberate trade-off
        (credentials beat false-positive prose).
        """
        if reveal or text is None:
            return text
        out = _INLINE_JWT_REGEX.sub(lambda m: _sentinel(m.group(0)), text)
        out = _INLINE_BEARER_REGEX.sub(lambda m: _sentinel(m.group(0)), out)

        def _maybe_redact_high_entropy(match: re.Match[str]) -> str:
            candidate = match.group(0)
            if _looks_like_high_entropy_token(candidate):
                return _sentinel(candidate)
            return candidate

        out = _INLINE_HIGH_ENTROPY_REGEX.sub(_maybe_redact_high_entropy, out)
        return out

    # ----- HTML / script-block body -------------------------------------------

    def redact_html(self, text: str | None, *, reveal: bool = False) -> str | None:
        """Mask credentials inside HTML, including inline ``<script>`` blocks.

        Extracts ``window.X = {...}`` style script payloads, tries to
        JSON-parse them, runs the dict-walker, and substitutes the result
        back into the document. Falls through to :meth:`redact_text` for
        the surrounding HTML so JWT / Bearer tokens in attributes or text
        nodes still get masked.
        """
        if reveal or text is None:
            return text

        # Detect script-block payload assignments: window.X = { ... };
        # Greedy enough to capture nested braces in a small extracted block.
        script_pattern = re.compile(
            r"(<script[^>]*>.*?window\.\w+\s*=\s*)(\{.*?\})(\s*;?.*?</script>)",
            re.IGNORECASE | re.DOTALL,
        )

        def _sub_script(match: re.Match[str]) -> str:
            prefix, body, suffix = match.group(1), match.group(2), match.group(3)
            try:
                parsed = json.loads(body)
            except ValueError, TypeError:
                # Not strict JSON (often JS object literal). Fall back to
                # textual redaction on the body so JWT/Bearer still mask.
                return prefix + (self.redact_text(body) or body) + suffix
            redacted = self.redact_dict(parsed)
            return prefix + json.dumps(redacted) + suffix

        masked = script_pattern.sub(_sub_script, text)
        # Catch tokens outside script blocks too.
        return self.redact_text(masked) or masked

    # ----- body text (JSON / form-encoded) ------------------------------------

    def redact_body_text(self, body_text: str | None, *, reveal: bool = False) -> str | None:
        """Mask sensitive values inside a request or response body.

        JSON bodies (root ``{`` or ``[``) are parsed, walked, and
        re-serialised. ``application/x-www-form-urlencoded`` bodies are
        parsed pair-by-pair. Other text passes through unchanged.
        """
        if reveal or body_text is None:
            return body_text
        stripped = body_text.lstrip()
        if stripped and stripped[0] in ("{", "["):
            try:
                parsed = json.loads(body_text)
            except ValueError, TypeError:
                pass
            else:
                return json.dumps(self.redact_dict(parsed))
        if looks_like_form_body(body_text):
            return self.redact_form_text(body_text)
        return body_text

    def redact_form_text(self, text: str, *, reveal: bool = False) -> str:
        """Redact pairs in an ``application/x-www-form-urlencoded`` body."""
        if reveal:
            return text
        pairs = parse_qsl(text, keep_blank_values=True)
        redacted_pairs: list[tuple[str, str]] = []
        for key, value in pairs:
            if self.is_sensitive_key(key):
                redacted_pairs.append((key, _sentinel(value)))
            elif _looks_like_high_entropy_token(value):
                redacted_pairs.append((key, _sentinel(value)))
            else:
                redacted_pairs.append((key, value))
        return urlencode(redacted_pairs, safe="*<>, ")


# Default Redactor with no extras. Used by the back-compat shims.
_DEFAULT_REDACTOR: Redactor = Redactor()


# ---------------------------------------------------------------------------
# Factory and back-compat shims
# ---------------------------------------------------------------------------


def make_redactor(
    extra_keys: Iterable[str] = (),
    extra_exclusions: Iterable[str] = (),
    extra_headers: Iterable[str] = (),
    pii: bool = False,
    value_shape_exempt_keys: Iterable[str] = (),
) -> Redactor:
    """Build a :class:`Redactor` with server-specific extras.

    Args:
        extra_keys: Additional credential / PII key names. Strings are
            normalised (lowercase + alphanumeric-only) so callers can
            pass ``"x_passphrase"``, ``"X-Passphrase"``, or ``"xPassphrase"``
            interchangeably.
        extra_exclusions: Additional benign key names to pass through.
            Normalised the same way.
        extra_headers: Additional HTTP header names that always redact.
            Lowercased; pass with the canonical dashed form
            (``"x-vendor-token"``).
        pii: When True, the PII identifier matcher is enabled in
            addition to the credential matcher. Off by default so
            existing servers retain credentials-only behaviour.
        value_shape_exempt_keys: Key names whose values bypass the
            value-entropy heuristic (``_looks_like_high_entropy_token``).
            Normalised (lowercase, alphanumeric-only). The key-name lexicon
            still applies: a key matching both the sensitive lexicon and this
            list is redacted by the key-name layer. Has no effect on
            ``redact_text``, ``redact_html``, or ``redact_form_text``.

            The bypass applies only to the **immediate string value** of the
            named key in a dict walk. It does NOT extend to:

            * items inside a list or tuple under that key (the list branch
              resets ``parent_key`` to ``None`` before recursing, so list
              items are still evaluated by the value-shape detector);
            * keys inside a nested dict under that key (each nested key is
              evaluated under its own name, not the exempt parent's name).
    """
    return Redactor(
        extra_keys=frozenset(_normalise_key_compact(k) for k in extra_keys),
        extra_exclusions=frozenset(_normalise_key_compact(k) for k in extra_exclusions),
        extra_headers=frozenset(h.lower() for h in extra_headers),
        pii=pii,
        # Store-time normalisation (here) and lookup-time normalisation (in _walk)
        # are both intentional: the frozenset is built from normalised keys so
        # callers can pass "model_id", "ModelId", or "model-id" interchangeably,
        # and the lookup in _walk normalises the raw incoming key for the same
        # reason. The double application is not a bug; it is symmetric with how
        # extra_keys and extra_exclusions handle normalisation.
        value_shape_exempt_keys=frozenset(_normalise_key_compact(k) for k in value_shape_exempt_keys),
    )


def make_masker(
    extra_keys: Iterable[str] = (),
    extra_exclusions: Iterable[str] = (),
    pii: bool = False,
    value_shape_exempt_keys: Iterable[str] = (),
) -> Callable[[Any, bool], Any]:
    """Build a server-specific ``mask_secrets(payload, reveal)`` helper.

    Back-compat shim: existing servers call ``make_masker({...})`` and
    expect a callable that takes a payload plus a ``reveal`` keyword.
    Internally builds a :class:`Redactor` and binds its ``redact_dict``
    method.

    Args:
        extra_keys: Server-specific credential / PII field names. Normalised
            (lowercase, alphanumeric-only) so dashes, underscores, and
            camelCase all match through the same regex.
        extra_exclusions: Server-specific field names that must NOT redact
            even though the default regex would otherwise match them. Use
            for structural-ID fields (bitwarden documents ``id``,
            ``folder_id``, ``organization_id`` as structural primary keys
            that are preserved by deliberate trade-off; see the README).
        pii: When True, the PII identifier matcher is enabled in
            addition to the credential matcher. Off by default.
        value_shape_exempt_keys: Key names whose values bypass the
            value-entropy heuristic (``_looks_like_high_entropy_token``).
            Normalised (lowercase, alphanumeric-only). The key-name lexicon
            still applies: a key matching both the sensitive lexicon and this
            list is redacted by the key-name layer. Has no effect on
            ``redact_text``, ``redact_html``, or ``redact_form_text``.

            The bypass applies only to the **immediate string value** of the
            named key in a dict walk; list/tuple items and nested dict keys
            under an exempt key are not exempt.

    Returns:
        A callable ``mask(payload, reveal=False)`` that returns the
        payload unchanged when ``reveal=True`` and a redacted copy
        otherwise.
    """
    redactor = make_redactor(
        extra_keys=extra_keys,
        extra_exclusions=extra_exclusions,
        pii=pii,
        value_shape_exempt_keys=value_shape_exempt_keys,
    )

    def mask(payload: Any, reveal: bool = False) -> Any:
        return redactor.redact_dict(payload, reveal=reveal)

    return mask


def redact_secrets(
    data: Any,
    secret_keys: frozenset[str] | None = None,
) -> Any:
    """Redact secret-bearing fields from a payload (back-compat free function).

    Walks dicts and lists recursively. Uses the regex matcher plus the
    value-shape detector. ``secret_keys`` is accepted as an extra-keys
    set for callers that were passing a custom union of
    ``DEFAULT_SECRET_KEYS | {...}``; the extras are merged into the
    default regex-based policy.
    """
    extras: Iterable[str] = ()
    if secret_keys is not None:
        # Distinguish DEFAULT_SECRET_KEYS (the legacy frozenset) from a
        # caller-supplied superset by subtracting the legacy keys; the
        # remainder becomes per-call extras for the Redactor.
        extras = set(secret_keys) - DEFAULT_SECRET_KEYS
    redactor = make_redactor(extra_keys=extras)
    return redactor.redact_dict(data, reveal=False)
