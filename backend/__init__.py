"""GraphQL partial-failure backend (October 2021 spec, sections 5.3.2 / 6.3 / 6.4).

graphql-core is used only for schema building, query parsing and the remaining
validation rules. Field-conflict checking, field collection, merging and value
completion are implemented here by hand. No executor is used.
"""

from .service import handle_request, run_request

__all__ = ["handle_request", "run_request"]
