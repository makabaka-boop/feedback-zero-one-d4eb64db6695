"""Seeded differential fuzz: random valid queries and random roots over a
fixed rich schema, all inside the legal intersection (valid scalars, valid
shapes). Deterministic via a fixed seed.
"""

import random

from graphql import (
    build_schema,
    get_named_type,
    is_abstract_type,
    is_composite_type,
    is_interface_type,
    is_list_type,
    is_non_null_type,
    is_object_type,
    is_scalar_type,
)

FUZZ_SCHEMA_SDL = """
interface Node { id: String! }
type User implements Node {
  id: String!  name: String  age: Int  vip: Boolean!
  friend: User  tags: [String]  scores: [Int!]
}
type Org implements Node {
  id: String!  title: String  members: [User!]
}
union Entity = User | Org
type Query {
  name: String
  flag: Boolean!
  count: Int
  nums: [Int!]
  tags: [String]
  matrix: [[Int!]!]
  user: User
  users: [User!]
  mustUser: User!
  node: Node
  nodes: [Node]
  entity: Entity
  mustEntity: Entity!
}
"""

FRAGMENT_DEFS = {
    "FU": "fragment FU on User { fu_id: id  fu_name: name }",
    "FO": "fragment FO on Org { fo_id: id  fo_title: title }",
    "FN": "fragment FN on Node { fn_id: id }",
    "FE": "fragment FE on Entity { fe_t: __typename }",
    "FQ": "fragment FQ on Query { fq_name: name }",
}

FRAGMENTS_FOR = {
    "User": ["FU", "FN"],
    "Org": ["FO", "FN"],
    "Node": ["FU", "FO", "FN"],
    "Entity": ["FE"],
    "Query": ["FQ"],
}

_schema = build_schema(FUZZ_SCHEMA_SDL + "\n".join(FRAGMENT_DEFS.values()))


def fuzz_schema():
    return _schema


def _gen_value(rng, type_, depth):
    """Random source value; always shape-correct, scalars always legal."""
    if is_non_null_type(type_):
        return _gen_value(rng, type_.of_type, depth)
    if rng.random() < 0.15:
        return None
    if is_list_type(type_):
        return [_gen_value(rng, type_.of_type, depth) for _ in range(rng.randrange(3))]
    named = get_named_type(type_)
    if is_scalar_type(named):
        if named.name == "String":
            return rng.choice(["a", "b", "xyz", ""])
        if named.name == "Int":
            return rng.randrange(-5, 100)
        return rng.random() < 0.5
    if is_object_type(named):
        return _gen_object(rng, named, depth + 1)
    if is_abstract_type(named):
        roll = rng.random()
        if roll < 0.08:
            return {"__typename": rng.choice(["Nope", "Query", 5])}  # invalid
        runtime = rng.choice(list(_schema.get_possible_types(named)))
        obj = _gen_object(rng, runtime, depth + 1)
        obj["__typename"] = runtime.name
        if roll < 0.16:
            del obj["__typename"]  # missing
        return obj
    raise AssertionError(named)


def _gen_object(rng, object_type, depth):
    if depth > 3:
        return {}
    obj = {}
    for field_name, field in object_type.fields.items():
        if rng.random() < 0.15:
            continue  # missing key
        obj[field_name] = _gen_value(rng, field.type, depth)
    return obj


def _gen_field(rng, field_name, field_type, depth, counter, allow_alias=True):
    named = get_named_type(field_type)
    if is_composite_type(named) and depth >= 3:
        return None
    alias = ""
    if allow_alias and rng.random() < 0.25:
        counter[0] += 1
        alias = f"a{counter[0]}: "
    text = alias + field_name
    roll = rng.random()
    if roll < 0.08:
        text += " @skip(if: true)"
    elif roll < 0.16:
        text += " @include(if: false)"
    elif roll < 0.24:
        text += " @skip(if: false)"
    if is_composite_type(named):
        inner = _gen_for_parent(rng, named, depth + 1, counter)
        text += " { " + " ".join(inner) + " }"
    return text


def _gen_for_parent(rng, parent_type, depth, counter):
    selections = []
    if is_object_type(parent_type) or is_interface_type(parent_type):
        candidates = list(parent_type.fields.items())
        rng.shuffle(candidates)
        for field_name, field in candidates[: rng.randrange(1, 4)]:
            text = _gen_field(rng, field_name, field.type, depth, counter)
            if text is not None:
                selections.append(text)
        # same key + same field again: a legal merge with fresh sub-selections
        mergeable = [
            (n, f) for n, f in candidates
            if is_composite_type(get_named_type(f.type)) and depth < 2
        ]
        if mergeable and rng.random() < 0.3:
            field_name, field = rng.choice(mergeable)
            text = _gen_field(
                rng, field_name, field.type, depth, counter, allow_alias=False
            )
            if text is not None:
                selections.append(text)
    if rng.random() < 0.3:
        selections.append("__typename")
    if is_abstract_type(parent_type):
        for runtime in _schema.get_possible_types(parent_type):
            if rng.random() < 0.6:
                inner = _gen_for_parent(rng, runtime, depth + 1, counter)
                selections.append(f"... on {runtime.name} {{ {' '.join(inner)} }}")
    for fragment in FRAGMENTS_FOR.get(parent_type.name, []):
        if rng.random() < 0.3:
            counter[1].add(fragment)
            selections.append(f"...{fragment}")
    return selections or ["__typename"]


def generate_fuzz_cases(count=600, seed=20261014):
    """Deterministic random (name, sdl, query, root) cases."""
    rng = random.Random(seed)
    cases = []
    for index in range(count):
        counter = [0, set()]
        selections = _gen_for_parent(rng, _schema.query_type, 0, counter)
        query = "{ " + " ".join(selections) + " }"
        if counter[1]:
            query += "\n" + "\n".join(
                FRAGMENT_DEFS[name] for name in sorted(counter[1])
            )
        root = _gen_object(rng, _schema.query_type, 0)
        cases.append((f"fuzz-{index:03d}", FUZZ_SCHEMA_SDL, query, root))
    return cases
