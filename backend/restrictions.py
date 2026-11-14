"""Schema subset enforcement.

Only String, Boolean, Int, object, interface and union types plus list and
non-null wrappers are supported. Anything else in the SDL (Float, ID, custom
scalars, enums, input objects, field arguments, custom directives, ...) makes
the request invalid.
"""

from __future__ import annotations

from graphql import (
    GraphQLSchema,
    is_enum_type,
    is_input_object_type,
    is_interface_type,
    is_object_type,
    is_scalar_type,
    is_union_type,
    specified_directives,
)

ALLOWED_SCALARS = frozenset({"String", "Boolean", "Int"})
ALLOWED_DIRECTIVES = frozenset(d.name for d in specified_directives)


def check_schema_restrictions(schema: GraphQLSchema) -> list[str]:
    """Return a list of restriction violations (empty means the schema is OK)."""
    errors: list[str] = []
    for name, type_ in sorted(schema.type_map.items()):
        if name.startswith("__"):  # introspection types are always present
            continue
        if is_scalar_type(type_):
            if name not in ALLOWED_SCALARS:
                errors.append(f"Scalar '{name}' is not supported.")
        elif is_enum_type(type_) or is_input_object_type(type_):
            errors.append(f"Type '{name}' is not supported.")
        elif is_object_type(type_) or is_interface_type(type_):
            for field_name, field in sorted(type_.fields.items()):
                if field.args:
                    errors.append(
                        f"Field '{name}.{field_name}' must not declare arguments."
                    )
        elif is_union_type(type_):
            pass
    for directive in schema.directives:
        if directive.name not in ALLOWED_DIRECTIVES:
            errors.append(f"Directive '@{directive.name}' is not supported.")
    if schema.query_type is None:
        errors.append("Schema must declare a query root type.")
    return errors
