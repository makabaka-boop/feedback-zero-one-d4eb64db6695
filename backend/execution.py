"""Execution engine: self-written CollectFields, field merging at execution time
and value completion, following October 2021 spec sections 6.3 and 6.4.

Simplifications allowed by the request restrictions: no variables, no field
arguments, no custom directives, so directive handling at execution time is
limited to @skip/@include with boolean literals.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from graphql import (
    GraphQLSchema,
    is_abstract_type,
    is_list_type,
    is_non_null_type,
    is_object_type,
    is_scalar_type,
)
from graphql.language.ast import (
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    InlineFragmentNode,
    OperationDefinitionNode,
    SelectionSetNode,
)
from graphql.type.introspection import TypeNameMetaFieldDef


class FieldError(Exception):
    """A field error was raised; its (single, initial) path is already recorded."""


def _is_skipped(selection) -> bool:
    """@skip(if: true) / @include(if: false) with boolean literals only."""
    for directive in selection.directives or ():
        name = directive.name.value
        if name not in ("skip", "include"):
            continue
        argument = next(
            (a for a in directive.arguments or () if a.name.value == "if"), None
        )
        value = getattr(argument.value, "value", None) if argument is not None else None
        if name == "skip" and value is True:
            return True
        if name == "include" and value is False:
            return True
    return False


class Executor:
    def __init__(self, schema: GraphQLSchema, fragments: dict[str, FragmentDefinitionNode]):
        self.schema = schema
        self.fragments = fragments
        self.errors: list[list] = []

    # -- errors -------------------------------------------------------------
    def raise_field_error(self, path: list) -> None:
        # Only the initial path is recorded; bubbling records nothing more.
        self.errors.append(list(path))
        raise FieldError()

    # -- §6.3.1 CollectFields ------------------------------------------------
    def collect_fields(
        self, runtime_type, selection_sets: list[SelectionSetNode]
    ) -> dict[str, list[FieldNode]]:
        """Group fields by response key, in first-collected order.

        Fields sharing a key keep their nodes so sub-selections can be merged.
        A fresh visited-fragment set is used per call, as the spec requires.
        """
        grouped: dict[str, list[FieldNode]] = {}
        visited_fragments: set[str] = set()
        for selection_set in selection_sets:
            self._collect(runtime_type, selection_set, grouped, visited_fragments)
        return grouped

    def _collect(self, runtime_type, selection_set, grouped, visited_fragments) -> None:
        for selection in selection_set.selections:
            if _is_skipped(selection):
                continue
            if isinstance(selection, FieldNode):
                key = selection.alias.value if selection.alias else selection.name.value
                grouped.setdefault(key, []).append(selection)
            elif isinstance(selection, FragmentSpreadNode):
                name = selection.name.value
                if name in visited_fragments:
                    continue
                visited_fragments.add(name)
                fragment = self.fragments.get(name)
                if fragment is None:
                    continue
                if not self._fragment_applies(fragment.type_condition, runtime_type):
                    continue
                self._collect(runtime_type, fragment.selection_set, grouped, visited_fragments)
            elif isinstance(selection, InlineFragmentNode):
                condition = selection.type_condition
                if condition is not None and not self._fragment_applies(condition, runtime_type):
                    continue
                self._collect(runtime_type, selection.selection_set, grouped, visited_fragments)

    def _fragment_applies(self, type_condition, runtime_type) -> bool:
        condition_type = self.schema.get_type(type_condition.name.value)
        if condition_type is runtime_type:
            return True
        if is_abstract_type(condition_type):
            return runtime_type in self.schema.get_possible_types(condition_type)
        return False

    # -- §6.3.3/§6.3.4 field collection and execution over an object ---------
    def execute_selection_set(
        self, runtime_type, source: Mapping, selection_sets: list[SelectionSetNode], path: list
    ) -> dict:
        """Depth-first, in first-collected response-key order."""
        grouped = self.collect_fields(runtime_type, selection_sets)
        result: dict[str, Any] = {}
        for key, field_nodes in grouped.items():
            field_name = field_nodes[0].name.value
            field_type = self._field_type(runtime_type, field_name)
            if field_name == "__typename":
                raw = runtime_type.name  # meta field: runtime type name
            else:
                raw = source.get(field_name)  # original field name; missing == null
            try:
                completed = self.complete_value(field_type, field_nodes, raw, path + [key])
            except FieldError:
                if is_non_null_type(field_type):
                    # This object is revoked: stop evaluating its remaining fields.
                    raise
                completed = None
            result[key] = completed
        return result

    @staticmethod
    def _field_type(parent_type, field_name: str):
        if field_name == "__typename":
            return TypeNameMetaFieldDef.type  # String!
        return parent_type.fields[field_name].type

    # -- §6.4 value completion ------------------------------------------------
    def complete_value(self, field_type, field_nodes: list[FieldNode], value, path: list):
        # §6.4.1 Non-Null
        if is_non_null_type(field_type):
            completed = self.complete_value(field_type.of_type, field_nodes, value, path)
            if completed is None:
                self.raise_field_error(path)
            return completed
        # §6.4.2 null at a nullable position
        if value is None:
            return None
        # §6.4.3 List
        if is_list_type(field_type):
            if not isinstance(value, list):
                self.raise_field_error(path)  # shape mismatch
            item_type = field_type.of_type
            completed_items = []
            for index, item in enumerate(value):  # lists keep their original order
                try:
                    completed = self.complete_value(
                        item_type, field_nodes, item, path + [index]
                    )
                except FieldError:
                    if is_non_null_type(item_type):
                        # The list is revoked: stop evaluating remaining items.
                        raise
                    completed = None
                completed_items.append(completed)
            return completed_items
        # §6.4.4 leaf scalars (String / Boolean / Int only)
        if is_scalar_type(field_type):
            if not _scalar_matches(field_type.name, value):
                self.raise_field_error(path)  # shape/type mismatch
            return value
        # §6.4.5 object: concrete objects follow the declared type
        if is_object_type(field_type):
            if not isinstance(value, Mapping):
                self.raise_field_error(path)  # shape mismatch
            sub_sets = [n.selection_set for n in field_nodes if n.selection_set is not None]
            return self.execute_selection_set(field_type, value, sub_sets, path)
        # §6.4.5 abstract: source must carry a valid __typename
        if is_abstract_type(field_type):
            if not isinstance(value, Mapping):
                self.raise_field_error(path)  # shape mismatch
            typename = value.get("__typename")
            runtime_type = self.schema.get_type(typename) if isinstance(typename, str) else None
            if (
                runtime_type is None
                or not is_object_type(runtime_type)
                or runtime_type not in self.schema.get_possible_types(field_type)
            ):
                self.raise_field_error(path)
            sub_sets = [n.selection_set for n in field_nodes if n.selection_set is not None]
            return self.execute_selection_set(runtime_type, value, sub_sets, path)
        raise AssertionError(f"unexpected field type: {field_type!r}")


def _scalar_matches(name: str, value) -> bool:
    if isinstance(value, (dict, list)):
        return False
    if name == "String":
        return isinstance(value, str)
    if name == "Boolean":
        return isinstance(value, bool)
    if name == "Int":
        return isinstance(value, int) and not isinstance(value, bool)
    return False  # schema restrictions guarantee only these three scalars


def execute_request(schema: GraphQLSchema, document, root) -> dict:
    """§6.3 ExecuteRequest, simplified: no variables, single query operation."""
    operation = None
    fragments: dict[str, FragmentDefinitionNode] = {}
    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode):
            operation = definition
        elif isinstance(definition, FragmentDefinitionNode):
            fragments[definition.name.value] = definition
    executor = Executor(schema, fragments)
    source = root if isinstance(root, Mapping) else {}
    try:
        data = executor.execute_selection_set(
            schema.query_type, source, [operation.selection_set], []
        )
    except FieldError:
        data = None  # the root was revoked
    return {"data": data, "errors": executor.errors}
