"""Request pipeline: input shape -> schema -> parse -> validate -> execute.

Output contract:
  {"data": ..., "errors": [...]}
  - errors are paths (field = response key/alias, list index = zero-based int)
    in order of occurrence; empty when nothing went wrong.
  - invalid requests are rejected with a single top-level entry: the top-level
    field of the error, or "$" for syntax errors and unattributable errors.
"""

from __future__ import annotations

from graphql import GraphQLError, build_schema, parse

from .execution import execute_request
from .restrictions import check_schema_restrictions
from .validation import top_level_key_for_error, validate_request


def _syntax_rejection():
    return {"data": None, "errors": [["$"]]}, False


def run_request(payload) -> tuple[dict, bool]:
    """Process one request payload; return (output, accepted)."""
    if not isinstance(payload, dict):
        return _syntax_rejection()
    try:
        sdl = payload["schema"]
        query = payload["query"]
        root = payload["root"]
    except KeyError:
        return _syntax_rejection()
    if not isinstance(sdl, str) or not isinstance(query, str):
        return _syntax_rejection()

    try:
        schema = build_schema(sdl)
    except (GraphQLError, TypeError):
        return _syntax_rejection()
    if check_schema_restrictions(schema):
        return _syntax_rejection()

    try:
        document = parse(query)
    except GraphQLError:
        return _syntax_rejection()

    errors = validate_request(schema, document)
    if errors:
        key = top_level_key_for_error(document, errors[0])
        return {"data": None, "errors": [[key]]}, False

    return execute_request(schema, document, root), True


def handle_request(payload) -> dict:
    """Process one request payload; return the {data, errors} output."""
    return run_request(payload)[0]
