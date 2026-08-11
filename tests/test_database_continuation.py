"""Failing-first tests for RFC 8785 hashing and signed keyset continuation."""

import base64
import json

import pytest

from database import (
    CONTINUATION_VERSION,
    ContinuationBinding,
    ContinuationCodec,
    ContinuationSigner,
    ContinuationToken,
    Environment,
    HmacContinuationSigner,
    KeyColumn,
    NullOrdering,
    ProviderId,
    QueryStatus,
    SortDirection,
    ValidationError,
    canonicalize_json,
    sha256_hex,
)


SECRET = b"unit-test-signing-key"


class FrozenClock:
    def __init__(self, now: float = 1_800_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_binding(**overrides) -> ContinuationBinding:
    base = dict(
        provider=ProviderId.HANA,
        environment=Environment.DEVELOPMENT,
        sql_hash=sha256_hex(b"SELECT id FROM sales.orders ORDER BY id ASC"),
        parameters_hash=sha256_hex(canonicalize_json([1, "a"])),
        key_columns=(KeyColumn("id", SortDirection.ASC, NullOrdering.NULLS_LAST),),
        max_rows=100,
        max_result_chars=12000,
        max_cell_chars=1200,
        config_fingerprint="fingerprint-a",
    )
    base.update(overrides)
    return ContinuationBinding(**base)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock()


@pytest.fixture
def codec(clock: FrozenClock) -> ContinuationCodec:
    return ContinuationCodec(HmacContinuationSigner(SECRET), ttl_seconds=300, clock=clock)


def decode_claims(token: ContinuationToken) -> dict:
    payload, _, _signature = token.token.partition(".")
    padded = payload + "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def retoken(codec: ContinuationCodec, claims: dict) -> dict:
    payload = canonicalize_json(claims)
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = codec.signer.sign(payload)
    return {
        "version": claims.get("version", CONTINUATION_VERSION),
        "token": f"{encoded}.{signature}",
        "expires_at": "2026-01-01T00:00:00+00:00",
        "guidance": "resend unchanged",
    }


# --------------------------------------------------------------------------
# RFC 8785 canonicalization
# --------------------------------------------------------------------------


def test_canonicalization_is_stable_regardless_of_key_order():
    assert canonicalize_json({"b": 1, "a": 2}) == canonicalize_json({"a": 2, "b": 1})
    assert canonicalize_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_canonicalization_sorts_keys_by_utf16_code_units():
    assert canonicalize_json({"\u00e9": 1, "Z": 2, "a": 3}) == b'{"Z":2,"a":3,"\xc3\xa9":1}'


def test_canonicalization_has_no_insignificant_whitespace():
    assert canonicalize_json([1, 2, {"a": "b"}]) == b'[1,2,{"a":"b"}]'


def test_canonicalization_preserves_scalar_types():
    assert canonicalize_json([1, "1", True, None]) == b'[1,"1",true,null]'
    assert canonicalize_json(["1"]) != canonicalize_json([1])
    assert canonicalize_json([True]) != canonicalize_json([1])


def test_canonicalization_number_formatting():
    assert canonicalize_json([1.0]) == b"[1]"
    assert canonicalize_json([-0.0]) == b"[0]"
    assert canonicalize_json([1.5, 1e21, 1e-7]) == b"[1.5,1e+21,1e-7]"


def test_canonicalization_escapes_control_characters_minimally():
    assert canonicalize_json(["a\nb\"c\\d\u0001"]) == b'["a\\nb\\"c\\\\d\\u0001"]'


def test_canonicalization_rejects_non_finite_and_unsupported_types():
    for bad in (float("nan"), float("inf"), b"bytes", object()):
        with pytest.raises(ValidationError):
            canonicalize_json([bad])


def test_parameter_hash_is_stable_and_type_sensitive():
    assert sha256_hex(canonicalize_json([1, "a"])) == sha256_hex(canonicalize_json([1, "a"]))
    assert sha256_hex(canonicalize_json([1, "a"])) != sha256_hex(canonicalize_json(["1", "a"]))


# --------------------------------------------------------------------------
# Signer interface
# --------------------------------------------------------------------------


def test_hmac_signer_satisfies_signer_protocol():
    signer = HmacContinuationSigner(SECRET)
    assert isinstance(signer, ContinuationSigner)
    signature = signer.sign(b"payload")
    assert signer.verify(b"payload", signature) is True
    assert signer.verify(b"payload2", signature) is False


def test_signer_is_injected_not_hardcoded(clock: FrozenClock):
    codec_a = ContinuationCodec(HmacContinuationSigner(b"key-a"), clock=clock)
    codec_b = ContinuationCodec(HmacContinuationSigner(b"key-b"), clock=clock)
    binding = make_binding()
    token = codec_a.issue(binding, last_key_values=[10])
    with pytest.raises(ValidationError):
        codec_b.decode(token.to_dict(), binding)


# --------------------------------------------------------------------------
# Issue / decode round trip
# --------------------------------------------------------------------------


def test_round_trip_returns_last_key_values(codec: ContinuationCodec):
    binding = make_binding()
    token = codec.issue(binding, last_key_values=[10])
    assert token.version == CONTINUATION_VERSION
    assert token.guidance
    claims = codec.decode(token.to_dict(), binding)
    assert claims.last_key_values == (10,)
    assert claims.key_columns == binding.key_columns


def test_token_is_opaque_and_never_contains_sql_or_parameters(codec: ContinuationCodec):
    binding = make_binding()
    token = codec.issue(binding, last_key_values=["customer-42"])
    assert "SELECT" not in token.token
    assert "sales.orders" not in token.token
    claims = decode_claims(token)
    assert "sql" not in claims
    assert claims["sh"] == binding.sql_hash


def test_token_accepts_its_own_dataclass_form(codec: ContinuationCodec):
    binding = make_binding()
    token = codec.issue(binding, last_key_values=[1])
    assert codec.decode(token, binding).last_key_values == (1,)


def test_composite_keys_and_mixed_directions_round_trip(codec: ContinuationCodec):
    binding = make_binding(
        key_columns=(
            KeyColumn("region", SortDirection.ASC, NullOrdering.NULLS_FIRST),
            KeyColumn("created_at", SortDirection.DESC, NullOrdering.NULLS_LAST),
            KeyColumn("id", SortDirection.ASC, NullOrdering.NULLS_LAST),
        )
    )
    token = codec.issue(binding, last_key_values=["emea", "2026-01-01T00:00:00+00:00", 9])
    claims = codec.decode(token.to_dict(), binding)
    assert claims.last_key_values == ("emea", "2026-01-01T00:00:00+00:00", 9)
    assert [c.direction for c in claims.key_columns] == [
        SortDirection.ASC,
        SortDirection.DESC,
        SortDirection.ASC,
    ]


def test_key_ordering_is_significant(codec: ContinuationCodec):
    binding = make_binding(
        key_columns=(
            KeyColumn("a", SortDirection.ASC, NullOrdering.NULLS_LAST),
            KeyColumn("b", SortDirection.ASC, NullOrdering.NULLS_LAST),
        )
    )
    swapped = make_binding(
        key_columns=(
            KeyColumn("b", SortDirection.ASC, NullOrdering.NULLS_LAST),
            KeyColumn("a", SortDirection.ASC, NullOrdering.NULLS_LAST),
        )
    )
    token = codec.issue(binding, last_key_values=[1, 2])
    with pytest.raises(ValidationError):
        codec.decode(token.to_dict(), swapped)


def test_direction_change_invalidates_token(codec: ContinuationCodec):
    binding = make_binding()
    flipped = make_binding(
        key_columns=(KeyColumn("id", SortDirection.DESC, NullOrdering.NULLS_LAST),)
    )
    token = codec.issue(binding, last_key_values=[1])
    with pytest.raises(ValidationError):
        codec.decode(token.to_dict(), flipped)


def test_null_ordering_change_invalidates_token(codec: ContinuationCodec):
    binding = make_binding()
    other = make_binding(
        key_columns=(KeyColumn("id", SortDirection.ASC, NullOrdering.NULLS_FIRST),)
    )
    token = codec.issue(binding, last_key_values=[1])
    with pytest.raises(ValidationError):
        codec.decode(token.to_dict(), other)


def test_null_ordering_must_be_explicit():
    with pytest.raises(ValidationError):
        KeyColumn("id", SortDirection.ASC, None)


def test_key_columns_required(codec: ContinuationCodec):
    with pytest.raises(ValidationError):
        codec.issue(make_binding(key_columns=()), last_key_values=[])


def test_null_last_key_value_rejected(codec: ContinuationCodec):
    with pytest.raises(ValidationError):
        codec.issue(make_binding(), last_key_values=[None])


def test_last_key_arity_must_match_key_columns(codec: ContinuationCodec):
    binding = make_binding(
        key_columns=(
            KeyColumn("a", SortDirection.ASC, NullOrdering.NULLS_LAST),
            KeyColumn("b", SortDirection.ASC, NullOrdering.NULLS_LAST),
        )
    )
    with pytest.raises(ValidationError):
        codec.issue(binding, last_key_values=[1])


# --------------------------------------------------------------------------
# Binding, replay, tamper
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"provider": ProviderId.SYNAPSE},
        {"environment": Environment.PRODUCTION},
        {"sql_hash": sha256_hex(b"SELECT other")},
        {"parameters_hash": sha256_hex(canonicalize_json([2, "a"]))},
        {"max_rows": 50},
        {"max_result_chars": 6000},
        {"max_cell_chars": 600},
        {"config_fingerprint": "fingerprint-b"},
    ],
    ids=[
        "provider",
        "environment",
        "sql",
        "parameters",
        "max_rows",
        "max_result_chars",
        "max_cell_chars",
        "config_fingerprint",
    ],
)
def test_rebinding_is_rejected(codec: ContinuationCodec, override):
    token = codec.issue(make_binding(), last_key_values=[1])
    with pytest.raises(ValidationError) as exc:
        codec.decode(token.to_dict(), make_binding(**override))
    assert exc.value.status is QueryStatus.VALIDATION_ERROR


def test_failure_never_silently_restarts_at_page_one(codec: ContinuationCodec):
    token = codec.issue(make_binding(), last_key_values=[1])
    try:
        result = codec.decode(token.to_dict(), make_binding(config_fingerprint="other"))
    except ValidationError:
        return
    pytest.fail(f"expected rejection, got a fresh start: {result}")


def test_tampered_signature_rejected(codec: ContinuationCodec):
    payload = codec.issue(make_binding(), last_key_values=[1]).to_dict()
    body, _, signature = payload["token"].partition(".")
    payload["token"] = f"{body}.{'a' * len(signature)}"
    with pytest.raises(ValidationError):
        codec.decode(payload, make_binding())


def test_tampered_claims_rejected(codec: ContinuationCodec):
    token = codec.issue(make_binding(), last_key_values=[1])
    claims = decode_claims(token)
    claims["lk"] = [9999]
    payload = token.to_dict()
    encoded = base64.urlsafe_b64encode(canonicalize_json(claims)).decode().rstrip("=")
    payload["token"] = f"{encoded}.{payload['token'].partition('.')[2]}"
    with pytest.raises(ValidationError):
        codec.decode(payload, make_binding())


def test_noncanonical_payload_rejected(codec: ContinuationCodec):
    token = codec.issue(make_binding(), last_key_values=[1])
    claims = decode_claims(token)
    spaced = json.dumps(claims, separators=(", ", ": ")).encode()
    encoded = base64.urlsafe_b64encode(spaced).decode().rstrip("=")
    signature = codec.signer.sign(spaced)
    with pytest.raises(ValidationError):
        codec.decode(
            {**token.to_dict(), "token": f"{encoded}.{signature}"}, make_binding()
        )


def test_expired_token_rejected(codec: ContinuationCodec, clock: FrozenClock):
    token = codec.issue(make_binding(), last_key_values=[1])
    clock.now += 301
    with pytest.raises(ValidationError):
        codec.decode(token.to_dict(), make_binding())


def test_token_valid_inside_ttl(codec: ContinuationCodec, clock: FrozenClock):
    token = codec.issue(make_binding(), last_key_values=[1])
    clock.now += 299
    assert codec.decode(token.to_dict(), make_binding()).last_key_values == (1,)


def test_future_issued_token_rejected(codec: ContinuationCodec, clock: FrozenClock):
    token = codec.issue(make_binding(), last_key_values=[1])
    clock.now -= 3600
    with pytest.raises(ValidationError):
        codec.decode(token.to_dict(), make_binding())


def test_unsupported_version_rejected(codec: ContinuationCodec):
    token = codec.issue(make_binding(), last_key_values=[1])
    payload = token.to_dict()
    payload["version"] = CONTINUATION_VERSION + 1
    with pytest.raises(ValidationError):
        codec.decode(payload, make_binding())


def test_unsupported_claim_version_rejected(codec: ContinuationCodec):
    claims = decode_claims(codec.issue(make_binding(), last_key_values=[1]))
    claims["v"] = CONTINUATION_VERSION + 1
    with pytest.raises(ValidationError):
        codec.decode(retoken(codec, claims), make_binding())


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "not-a-dict",
        {},
        {"version": CONTINUATION_VERSION},
        {"version": CONTINUATION_VERSION, "token": ""},
        {"version": CONTINUATION_VERSION, "token": "no-separator"},
        {"version": CONTINUATION_VERSION, "token": "!!!.!!!"},
        {"version": CONTINUATION_VERSION, "token": "e30.abc"},
        {"version": "1", "token": "e30.abc"},
    ],
    ids=[
        "none",
        "string",
        "empty",
        "missing_token",
        "blank_token",
        "no_separator",
        "bad_base64",
        "unsigned_empty_claims",
        "string_version",
    ],
)
def test_malformed_continuation_rejected(codec: ContinuationCodec, payload):
    with pytest.raises(ValidationError):
        codec.decode(payload, make_binding())


@pytest.mark.parametrize("missing", ["v", "p", "e", "sh", "ph", "kc", "lk", "lim", "cf", "iat", "exp"])
def test_missing_claim_rejected(codec: ContinuationCodec, missing: str):
    claims = decode_claims(codec.issue(make_binding(), last_key_values=[1]))
    claims.pop(missing)
    with pytest.raises(ValidationError):
        codec.decode(retoken(codec, claims), make_binding())


def test_null_key_claim_rejected(codec: ContinuationCodec):
    claims = decode_claims(codec.issue(make_binding(), last_key_values=[1]))
    claims["lk"] = [None]
    with pytest.raises(ValidationError):
        codec.decode(retoken(codec, claims), make_binding())


def test_malformed_composite_key_claim_rejected(codec: ContinuationCodec):
    claims = decode_claims(codec.issue(make_binding(), last_key_values=[1]))
    claims["lk"] = [1, 2]
    with pytest.raises(ValidationError):
        codec.decode(retoken(codec, claims), make_binding())


def test_nested_key_claim_rejected(codec: ContinuationCodec):
    claims = decode_claims(codec.issue(make_binding(), last_key_values=[1]))
    claims["lk"] = [{"a": 1}]
    with pytest.raises(ValidationError):
        codec.decode(retoken(codec, claims), make_binding())


# --------------------------------------------------------------------------
# Advancement
# --------------------------------------------------------------------------


def test_advance_issues_next_page_token(codec: ContinuationCodec):
    binding = make_binding()
    first = codec.issue(binding, last_key_values=[10])
    second = codec.advance(first.to_dict(), binding, last_key_values=[20])
    assert codec.decode(second.to_dict(), binding).last_key_values == (20,)
    assert second.token != first.token


def test_advance_rejects_non_advancing_key(codec: ContinuationCodec):
    binding = make_binding()
    first = codec.issue(binding, last_key_values=[10])
    with pytest.raises(ValidationError):
        codec.advance(first.to_dict(), binding, last_key_values=[10])


def test_advance_validates_the_previous_token(codec: ContinuationCodec):
    binding = make_binding()
    first = codec.issue(binding, last_key_values=[10])
    with pytest.raises(ValidationError):
        codec.advance(first.to_dict(), make_binding(config_fingerprint="other"), last_key_values=[20])


def test_issue_never_logs_parameter_values(codec: ContinuationCodec, caplog):
    caplog.set_level("DEBUG")
    binding = make_binding()
    token = codec.issue(binding, last_key_values=["super-secret-key-value"])
    codec.decode(token.to_dict(), binding)
    assert "super-secret-key-value" not in caplog.text
