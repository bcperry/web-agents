"""Failing-first tests for provider-neutral database request/SQL validation.

Covers the accepted SQL grammar, scalar/parameter boundaries, schema-override
narrowing, and unsafe-statement rejection from
``specs/015-sap-hana-private-connectivity/contracts/database-tools.md``.
"""

import pytest

from database import (
    INT64_MAX,
    INT64_MIN,
    MAX_PARAMETER_STRING_CHARS,
    MAX_PARAMETERS,
    MAX_PARAMETERS_CANONICAL_BYTES,
    MAX_SQL_CHARS,
    QueryRequest,
    QueryStatus,
    ValidationError,
    validate_identifier_filter,
    validate_parameters,
)
from database_sql import SqlGlotValidator, SqlValidator, default_sql_validator


@pytest.fixture
def validator() -> SqlValidator:
    return default_sql_validator()


# --------------------------------------------------------------------------
# Accepted grammar
# --------------------------------------------------------------------------

ACCEPTED = [
    "SELECT 1",
    "SELECT a, b FROM sales.orders WHERE a = ? ORDER BY a ASC",
    "SELECT * FROM sales.orders o JOIN sales.customers c ON o.cid = c.id",
    "SELECT COUNT(*) AS n, region FROM sales.orders GROUP BY region HAVING COUNT(*) > 1",
    'SELECT "Mixed Case" FROM sales."Orders"',
    "WITH recent AS (SELECT id FROM sales.orders) SELECT id FROM recent",
    "SELECT id FROM sales.a UNION ALL SELECT id FROM sales.b",
    "SELECT id FROM sales.orders WHERE name = 'not -- a comment'",
    "SELECT 1;",
    "  SELECT   1  ",
]


@pytest.mark.parametrize("sql", ACCEPTED)
def test_accepted_read_only_statements(validator: SqlValidator, sql: str):
    validated = validator.validate(sql)
    assert validated.normalized_sql
    assert validated.normalized_sql_hash


def test_default_validator_is_parser_backed(validator: SqlValidator):
    assert isinstance(validator, SqlGlotValidator)
    assert isinstance(validator, SqlValidator)


def test_normalized_hash_is_whitespace_and_case_stable(validator: SqlValidator):
    a = validator.validate("select a from sales.t order by a")
    b = validator.validate("SELECT   a\n  FROM sales.t\nORDER BY a")
    assert a.normalized_sql_hash == b.normalized_sql_hash


def test_normalized_hash_changes_with_semantics(validator: SqlValidator):
    a = validator.validate("SELECT a FROM sales.t")
    b = validator.validate("SELECT b FROM sales.t")
    assert a.normalized_sql_hash != b.normalized_sql_hash


def test_explicit_order_by_detected(validator: SqlValidator):
    assert validator.validate("SELECT a FROM sales.t ORDER BY a").has_explicit_order is True
    assert validator.validate("SELECT a FROM sales.t").has_explicit_order is False


# --------------------------------------------------------------------------
# Rejected grammar
# --------------------------------------------------------------------------

REJECTED = {
    "line_comment": "SELECT 1 -- leak",
    "leading_line_comment": "-- hidden\nSELECT 1",
    "block_comment": "SELECT /* hidden */ 1",
    "unterminated_block_comment": "SELECT 1 /* hidden",
    "multi_statement": "SELECT 1; SELECT 2",
    "trailing_delimiter_with_content": "SELECT 1; DROP TABLE sales.orders",
    "insert": "INSERT INTO sales.orders (id) VALUES (1)",
    "update": "UPDATE sales.orders SET id = 1",
    "delete": "DELETE FROM sales.orders",
    "merge": "MERGE INTO sales.orders USING sales.stage ON 1 = 1 WHEN MATCHED THEN UPDATE SET id = 1",
    "upsert": "UPSERT sales.orders VALUES (1)",
    "replace": "REPLACE INTO sales.orders VALUES (1)",
    "create": "CREATE TABLE sales.t (id INT)",
    "create_view": "CREATE VIEW sales.v AS SELECT 1",
    "drop": "DROP TABLE sales.orders",
    "alter": "ALTER TABLE sales.orders ADD c INT",
    "truncate": "TRUNCATE TABLE sales.orders",
    "grant": "GRANT SELECT ON sales.orders TO reader",
    "revoke": "REVOKE SELECT ON sales.orders FROM reader",
    "commit": "COMMIT",
    "rollback": "ROLLBACK",
    "begin_transaction": "BEGIN TRANSACTION",
    "set_session": "SET SCHEMA sales",
    "anonymous_block": "DO BEGIN SELECT 1 FROM DUMMY; END",
    "call_procedure": "CALL sales.do_thing()",
    "exec": "EXEC sales.do_thing",
    "execute": "EXECUTE sales.do_thing",
    "execute_immediate": "EXECUTE IMMEDIATE 'SELECT 1'",
    "select_into": "SELECT id INTO sales.copy FROM sales.orders",
    "import": "IMPORT FROM CSV FILE '/tmp/x' INTO sales.orders",
    "export": "EXPORT sales.orders AS CSV INTO '/tmp/x'",
    "alter_system": "ALTER SYSTEM CLEAR TRACES ('ALERT')",
    "unload": "UNLOAD sales.orders",
    "empty": "",
    "whitespace_only": "   \n\t ",
    "not_a_select": "VALUES (1)",
    "explain": "EXPLAIN PLAN FOR SELECT 1",
}


@pytest.mark.parametrize("sql", list(REJECTED.values()), ids=list(REJECTED))
def test_rejected_statements(validator: SqlValidator, sql: str):
    with pytest.raises(ValidationError) as exc:
        validator.validate(sql)
    assert exc.value.status is QueryStatus.VALIDATION_ERROR


def test_rejection_never_echoes_sql(validator: SqlValidator):
    secret = "SELECT 'p@ssw0rd-secret' AS x; DROP TABLE t"
    with pytest.raises(ValidationError) as exc:
        validator.validate(secret)
    assert "p@ssw0rd-secret" not in str(exc.value)


def test_cte_with_non_select_body_rejected(validator: SqlValidator):
    with pytest.raises(ValidationError):
        validator.validate(
            "WITH x AS (DELETE FROM sales.orders RETURNING id) SELECT id FROM x"
        )


def test_read_only_cte_chain_accepted(validator: SqlValidator):
    validated = validator.validate(
        "WITH a AS (SELECT id FROM sales.orders), b AS (SELECT id FROM a) SELECT id FROM b"
    )
    assert validated.referenced_schemas == frozenset({"sales"})


def test_sql_too_long_rejected(validator: SqlValidator):
    with pytest.raises(ValidationError):
        validator.validate("SELECT " + ("a" * (MAX_SQL_CHARS + 1)))


# --------------------------------------------------------------------------
# Table functions
# --------------------------------------------------------------------------


def test_table_function_denied_by_default(validator: SqlValidator):
    with pytest.raises(ValidationError):
        validator.validate("SELECT * FROM SERIES_GENERATE_INTEGER(1, 1, 10)")


def test_table_function_allowed_when_allowlisted(validator: SqlValidator):
    validated = validator.validate(
        "SELECT * FROM SYS.SERIES_GENERATE_INTEGER(1, 1, 10) s",
        allowed_table_functions=frozenset({"sys.series_generate_integer"}),
    )
    assert validated.referenced_table_functions == frozenset({"sys.series_generate_integer"})


def test_unqualified_table_function_not_matched_by_qualified_allowlist(validator: SqlValidator):
    with pytest.raises(ValidationError):
        validator.validate(
            "SELECT * FROM SERIES_GENERATE_INTEGER(1, 1, 10)",
            allowed_table_functions=frozenset({"sys.series_generate_integer"}),
        )


# --------------------------------------------------------------------------
# Approved-schema narrowing
# --------------------------------------------------------------------------


def test_schema_override_allows_approved_schema(validator: SqlValidator):
    validated = validator.validate(
        "SELECT a FROM Sales.Orders", approved_schemas=frozenset({"SALES"})
    )
    assert validated.referenced_schemas == frozenset({"sales"})


def test_schema_override_rejects_other_schema(validator: SqlValidator):
    with pytest.raises(ValidationError):
        validator.validate("SELECT a FROM other.t", approved_schemas=frozenset({"sales"}))


def test_schema_override_rejects_unqualified_table(validator: SqlValidator):
    with pytest.raises(ValidationError):
        validator.validate("SELECT a FROM orders", approved_schemas=frozenset({"sales"}))


def test_schema_override_ignores_cte_names(validator: SqlValidator):
    validated = validator.validate(
        "WITH orders AS (SELECT a FROM sales.raw) SELECT a FROM orders",
        approved_schemas=frozenset({"sales"}),
    )
    assert validated.referenced_schemas == frozenset({"sales"})


def test_no_override_permits_unqualified_table(validator: SqlValidator):
    assert validator.validate("SELECT a FROM orders").referenced_schemas == frozenset()


# --------------------------------------------------------------------------
# Identifier filters for schema discovery
# --------------------------------------------------------------------------


def test_identifier_filter_accepts_null_and_plain_names():
    assert validate_identifier_filter(None, field="schema") is None
    assert validate_identifier_filter("  SALES_1 ", field="schema") == "SALES_1"


@pytest.mark.parametrize(
    "value",
    ["", "   ", "a" * 128, "sales.orders", "sales%", "sa*es", 'sa"les', "sa'les", "sales;", "sa\x00les", "sa\nles"],
)
def test_identifier_filter_rejects_unsafe(value: str):
    with pytest.raises(ValidationError):
        validate_identifier_filter(value, field="schema")


# --------------------------------------------------------------------------
# Parameter scalars
# --------------------------------------------------------------------------


def test_parameters_none_allowed():
    assert validate_parameters(None) is None


def test_parameters_accepts_scalar_kinds():
    values = [None, True, False, 0, -1, INT64_MAX, INT64_MIN, 1.5, -0.0, "", "x" * MAX_PARAMETER_STRING_CHARS]
    assert validate_parameters(values) == tuple(values)


def test_parameters_at_limit_accepted():
    assert len(validate_parameters([1] * MAX_PARAMETERS)) == MAX_PARAMETERS


def test_parameters_over_limit_rejected():
    with pytest.raises(ValidationError):
        validate_parameters([1] * (MAX_PARAMETERS + 1))


@pytest.mark.parametrize(
    "value",
    [
        b"binary",
        bytearray(b"binary"),
        {"nested": 1},
        [1, 2],
        (1, 2),
        float("nan"),
        float("inf"),
        float("-inf"),
        INT64_MAX + 1,
        INT64_MIN - 1,
        "x" * (MAX_PARAMETER_STRING_CHARS + 1),
        object(),
    ],
)
def test_parameters_reject_unsupported_scalars(value):
    with pytest.raises(ValidationError):
        validate_parameters([value])


def test_parameters_must_be_a_sequence():
    with pytest.raises(ValidationError):
        validate_parameters({"a": 1})


def test_parameters_canonical_byte_budget_enforced():
    oversize = ["x" * MAX_PARAMETER_STRING_CHARS] * 5
    assert sum(len(v) for v in oversize) > MAX_PARAMETERS_CANONICAL_BYTES
    with pytest.raises(ValidationError):
        validate_parameters(oversize)


def test_parameter_strings_receive_no_type_inference():
    request = QueryRequest(sql="SELECT 1", parameters=["2024-01-01", "1.25"])
    assert request.parameters == ("2024-01-01", "1.25")
    assert request.canonical_parameters == b'["2024-01-01","1.25"]'


# --------------------------------------------------------------------------
# Query request assembly
# --------------------------------------------------------------------------


def test_query_request_rejects_blank_sql():
    with pytest.raises(ValidationError):
        QueryRequest(sql="   ")


def test_query_request_rejects_oversize_sql():
    with pytest.raises(ValidationError):
        QueryRequest(sql="s" * (MAX_SQL_CHARS + 1))


def test_query_request_exposes_stable_parameter_hash():
    a = QueryRequest(sql="SELECT 1", parameters=[1, "a", None, True])
    b = QueryRequest(sql="SELECT 1", parameters=[1, "a", None, True])
    c = QueryRequest(sql="SELECT 1", parameters=["1", "a", None, True])
    assert a.parameters_hash == b.parameters_hash
    assert a.parameters_hash != c.parameters_hash


def test_query_request_no_parameters_hash_is_distinct_from_empty_list():
    assert QueryRequest(sql="SELECT 1").parameters_hash != QueryRequest(
        sql="SELECT 1", parameters=[]
    ).parameters_hash
