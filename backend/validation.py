"""Request validation.

Standard rules come from graphql-core, except the field-merging rule which is
implemented here by hand (October 2021 spec §5.3.2). Extra rules enforce the
request restrictions: a single query operation, no variables, no field
arguments, only @skip/@include, and no introspection besides __typename.

The whole query is validated up front: fields under @skip/@include(if: false)
are still checked, and the response-shape check (SameResponseShape) also
applies to fields on mutually exclusive object types.
"""

from __future__ import annotations

from graphql import (
    GraphQLError,
    GraphQLSchema,
    is_interface_type,
    is_leaf_type,
    is_list_type,
    is_non_null_type,
    is_object_type,
    specified_rules,
    validate,
)
from graphql.language.ast import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    Node,
    OperationDefinitionNode,
    OperationType,
)
from graphql.type.introspection import TypeNameMetaFieldDef
from graphql.validation import ValidationRule
from graphql.validation.rules.overlapping_fields_can_be_merged import (
    OverlappingFieldsCanBeMergedRule,
)


# ---------------------------------------------------------------------------
# Restriction rules (run together with the remaining standard rules)
# ---------------------------------------------------------------------------
class SingleQueryOperationRule(ValidationRule):
    """Exactly one operation per document, and it must be a query."""

    def __init__(self, context):
        super().__init__(context)
        self._count = 0

    def enter_operation_definition(self, node, *_args):
        self._count += 1
        if self._count > 1:
            self.report_error(
                GraphQLError("Must provide exactly one operation.", [node])
            )
        elif node.operation is not OperationType.QUERY:
            self.report_error(
                GraphQLError("Only query operations are supported.", [node])
            )

    def leave_document(self, _node, *_args):
        if self._count == 0:
            self.report_error(GraphQLError("Must provide exactly one operation."))


class NoVariablesRule(ValidationRule):
    def enter_variable_definition(self, node, *_args):
        self.report_error(GraphQLError("Variables are not supported.", [node]))

    def enter_variable(self, node, *_args):
        self.report_error(GraphQLError("Variables are not supported.", [node]))


class NoFieldArgumentsRule(ValidationRule):
    def enter_field(self, node, *_args):
        if node.arguments:
            self.report_error(
                GraphQLError("Field arguments are not supported.", [node])
            )


class OnlySkipIncludeDirectivesRule(ValidationRule):
    def enter_directive(self, node, *_args):
        if node.name.value not in ("skip", "include"):
            self.report_error(
                GraphQLError(
                    "Only @skip and @include directives are supported.", [node]
                )
            )


class NoIntrospectionRule(ValidationRule):
    def enter_field(self, node, *_args):
        name = node.name.value
        if name.startswith("__") and name != "__typename":
            self.report_error(
                GraphQLError("Introspection is not supported.", [node])
            )


RULES = tuple(
    rule for rule in specified_rules if rule is not OverlappingFieldsCanBeMergedRule
) + (
    SingleQueryOperationRule,
    NoVariablesRule,
    NoFieldArgumentsRule,
    OnlySkipIncludeDirectivesRule,
    NoIntrospectionRule,
)


def validate_request(schema: GraphQLSchema, document) -> list[GraphQLError]:
    """Pre-validate the whole query; nothing is exempted by @skip/@include."""
    errors = list(validate(schema, document, RULES))
    if not errors:
        errors = check_field_merging(schema, document)
    return errors


# ---------------------------------------------------------------------------
# §5.3.2 field merging (self-written)
# ---------------------------------------------------------------------------
def _field_type(schema: GraphQLSchema, parent_type, field_name: str):
    if field_name == "__typename__":
        return TypeNameMetaFieldDef.type
    if parent_type is not None and (
        is_object_type(parent_type) or is_interface_type(parent_type)
    ):
        field = parent_type.fields.get(field_name)
        if field is not None:
            return field.type
    return None


def _named_type(type_):
    while is_non_null_type(type_) or is_list_type(type_):
        type_ = type_.of_type
    return type_


def _collect_pairs(schema, fragments, selection_set, parent_type, out, frag_stack):
    """Collect (parent type, field node) pairs, expanding every fragment.

    Directives are ignored on purpose: skipped fields are still validated.
    The fragment stack only guards against cycles (reported separately by
    NoFragmentCyclesRule); acyclic fragments are expanded at every site.
    """
    for selection in selection_set.selections:
        if isinstance(selection, FieldNode):
            out.append((parent_type, selection))
            if selection.selection_set is not None:
                field_type = _field_type(schema, parent_type, selection.name.value)
                if field_type is not None:
                    _collect_pairs(
                        schema,
                        fragments,
                        selection.selection_set,
                        _named_type(field_type),
                        out,
                        frag_stack,
                    )
        elif isinstance(selection, FragmentSpreadNode):
            name = selection.name.value
            if name in frag_stack:
                continue
            fragment = fragments.get(name)
            if fragment is None:
                continue
            condition = schema.get_type(fragment.type_condition.name.value)
            if condition is None:
                continue
            _collect_pairs(
                schema,
                fragments,
                fragment.selection_set,
                condition,
                out,
                frag_stack | {name},
            )
        elif isinstance(selection, InlineFragmentNode):
            condition = parent_type
            if selection.type_condition is not None:
                condition = schema.get_type(selection.type_condition.name.value)
                if condition is None:
                    continue
            _collect_pairs(
                schema, fragments, selection.selection_set, condition, out, frag_stack
            )


def _same_response_shape(type_a, type_b) -> bool:
    """Spec SameResponseShape: checked even for mutually exclusive parents."""
    while is_non_null_type(type_a) or is_non_null_type(type_b):
        if not (is_non_null_type(type_a) and is_non_null_type(type_b)):
            return False
        type_a, type_b = type_a.of_type, type_b.of_type
    while is_list_type(type_a) or is_list_type(type_b):
        if not (is_list_type(type_a) and is_list_type(type_b)):
            return False
        type_a, type_b = type_a.of_type, type_b.of_type
    if is_leaf_type(type_a) or is_leaf_type(type_b):
        return type_a is type_b
    return True  # both composite: sub-selections are compared separately


def check_field_merging(schema: GraphQLSchema, document) -> list[GraphQLError]:
    fragments = {
        definition.name.value: definition
        for definition in document.definitions
        if isinstance(definition, FragmentDefinitionNode)
    }
    errors: list[GraphQLError] = []
    memo: set = set()
    for definition in document.definitions:
        if not isinstance(definition, OperationDefinitionNode):
            continue
        if definition.operation is OperationType.QUERY:
            root_type = schema.query_type
        elif definition.operation is OperationType.MUTATION:
            root_type = schema.mutation_type
        else:
            root_type = schema.subscription_type
        if root_type is None:
            continue
        pairs: list = []
        _collect_pairs(
            schema, fragments, definition.selection_set, root_type, pairs, frozenset()
        )
        seen: set = set()
        unique_pairs = []
        for parent_type, node in pairs:
            marker = (id(parent_type), id(node))
            if marker not in seen:
                seen.add(marker)
                unique_pairs.append((parent_type, node))
        _fields_in_set_can_merge(schema, fragments, unique_pairs, errors, memo)
    return errors


def _fields_in_set_can_merge(schema, fragments, pairs, errors, memo) -> bool:
    by_key: dict[str, list] = {}
    for parent_type, node in pairs:
        key = node.alias.value if node.alias else node.name.value
        by_key.setdefault(key, []).append((parent_type, node))
    ok = True
    for group in by_key.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                parent_a, node_a = group[i]
                parent_b, node_b = group[j]
                if not _pair_can_merge(
                    schema, fragments, parent_a, node_a, parent_b, node_b, errors, memo
                ):
                    ok = False
    return ok


def _pair_can_merge(
    schema, fragments, parent_a, node_a, parent_b, node_b, errors, memo
) -> bool:
    if parent_a is parent_b and node_a is node_b:
        return True
    marker = (id(parent_a), id(node_a), id(parent_b), id(node_b))
    if marker in memo:
        return True
    memo.add(marker)
    type_a = _field_type(schema, parent_a, node_a.name.value)
    type_b = _field_type(schema, parent_b, node_b.name.value)
    if type_a is None or type_b is None:
        return True  # unknown fields are reported by the standard rules
    key = node_a.alias.value if node_a.alias else node_a.name.value
    # The response-shape check applies even to mutually exclusive types.
    if not _same_response_shape(type_a, type_b):
        errors.append(
            GraphQLError(
                f"Fields '{key}' conflict: they return conflicting shapes.",
                [node_a, node_b],
            )
        )
        return False
    # Name/argument equality is required unless the parent types are two
    # different object types (then the fields can never apply at once).
    mutually_exclusive = (
        is_object_type(parent_a)
        and is_object_type(parent_b)
        and parent_a is not parent_b
    )
    if not mutually_exclusive and node_a.name.value != node_b.name.value:
        errors.append(
            GraphQLError(
                f"Fields '{key}' conflict: different underlying fields.",
                [node_a, node_b],
            )
        )
        return False
    if node_a.selection_set is not None and node_b.selection_set is not None:
        sub_pairs: list = []
        _collect_pairs(
            schema, fragments, node_a.selection_set, _named_type(type_a), sub_pairs,
            frozenset(),
        )
        _collect_pairs(
            schema, fragments, node_b.selection_set, _named_type(type_b), sub_pairs,
            frozenset(),
        )
        return _fields_in_set_can_merge(schema, fragments, sub_pairs, errors, memo)
    return True


# ---------------------------------------------------------------------------
# Error attribution: map a validation error to its top-level response key
# ---------------------------------------------------------------------------
def top_level_key_for_error(document, error: GraphQLError) -> str:
    """The top-level field (response key) of an error, or '$' if unattributable."""
    nodes = getattr(error, "nodes", None) or ()
    if not nodes:
        return "$"
    mapping = _node_to_top_level_key(document)
    for node in nodes:
        key = mapping.get(id(node))
        if key is not None:
            return key
    return "$"


def _node_to_top_level_key(document) -> dict[int, str]:
    fragments = {
        definition.name.value: definition
        for definition in document.definitions
        if isinstance(definition, FragmentDefinitionNode)
    }
    mapping: dict[int, str] = {}

    def walk(node: Node, key: str, seen: set) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        mapping.setdefault(id(node), key)
        if isinstance(node, FragmentSpreadNode):
            fragment = fragments.get(node.name.value)
            if fragment is not None:
                walk(fragment, key, seen)
        for attr in node.keys:
            child = getattr(node, attr)
            if isinstance(child, Node):
                walk(child, key, seen)
            elif isinstance(child, (list, tuple)):
                for item in child:
                    if isinstance(item, Node):
                        walk(item, key, seen)

    def walk_top(selection_set, frag_stack) -> None:
        for selection in selection_set.selections:
            if isinstance(selection, FieldNode):
                key = selection.alias.value if selection.alias else selection.name.value
                walk(selection, key, set())
            elif isinstance(selection, InlineFragmentNode):
                walk_top(selection.selection_set, frag_stack)
            elif isinstance(selection, FragmentSpreadNode):
                name = selection.name.value
                fragment = fragments.get(name)
                if fragment is not None and name not in frag_stack:
                    walk_top(fragment.selection_set, frag_stack | {name})

    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode):
            walk_top(definition.selection_set, frozenset())
    return mapping
