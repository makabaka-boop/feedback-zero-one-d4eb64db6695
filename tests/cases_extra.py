"""Extra-rule cases: restrictions and backend-specific behavior, verified
independently with exact expected outputs (not covered by the reference
library comparison).
"""

SCHEMA_OBJECTS = """
type Query {
  name: String
  flag: Boolean!
  count: Int
  nums: [Int!]
  tags: [String]
  user: User
  users: [User!]
}
type User {
  id: String!
  name: String
  age: Int
  friend: User
}
"""

SCHEMA_ABSTRACT = """
interface Node { id: String! }
type User implements Node { id: String!  name: String }
type Org implements Node { id: String!  title: String }
union Entity = User | Org
type Query { node: Node  entity: Entity }
"""

SIMPLE = "type Query { a: String  b: String  n: Int }"


def rejected(*path):
    return {"data": None, "errors": [list(path)]}


# (name, payload, expected output)
EXTRA_CASES = [
    # --- syntax / input shape -------------------------------------------------
    ("reject-query-syntax", {"schema": SIMPLE, "query": "{ a", "root": {}},
     rejected("$")),
    ("reject-schema-syntax", {"schema": "type Query {", "query": "{ a }",
     "root": {}}, rejected("$")),
    ("reject-missing-member", {"schema": SIMPLE, "root": {}}, rejected("$")),
    ("reject-non-string-query", {"schema": SIMPLE, "query": 1, "root": {}},
     rejected("$")),
    ("reject-non-string-schema", {"schema": 1, "query": "{ a }", "root": {}},
     rejected("$")),
    ("reject-non-object-payload", "not an object", rejected("$")),
    # --- request restrictions ---------------------------------------------------
    ("reject-variable-definition",
     {"schema": SIMPLE, "query": "query Q($x: Boolean!) { a @include(if: $x) }",
      "root": {}}, rejected("$")),
    ("reject-variable-use",
     {"schema": SIMPLE, "query": "{ a @include(if: $x) }", "root": {}},
     rejected("a")),
    ("reject-field-arguments",
     {"schema": SCHEMA_OBJECTS, "query": "{ user(id: 1) { id } }", "root": {}},
     rejected("user")),
    ("reject-custom-directive",
     {"schema": SIMPLE, "query": "{ a @cached }", "root": {}}, rejected("a")),
    ("reject-directive-case",
     {"schema": SIMPLE, "query": "{ a @Skip(if: true) }", "root": {}},
     rejected("a")),
    ("reject-introspection-schema",
     {"schema": SIMPLE, "query": "{ __schema { types { name } } }", "root": {}},
     rejected("__schema")),
    ("reject-introspection-type",
     {"schema": SIMPLE, "query": '{ __type(name: "Query") { name } }',
      "root": {}}, rejected("__type")),
    ("reject-two-operations",
     {"schema": SIMPLE, "query": "query A { a } query B { a }", "root": {}},
     rejected("$")),
    ("reject-duplicate-operation-names",
     {"schema": SIMPLE, "query": "query A { a } query A { b }", "root": {}},
     rejected("$")),
    ("reject-empty-query",
     {"schema": SIMPLE, "query": "", "root": {}}, rejected("$")),
    ("reject-fragment-only-document",
     {"schema": SIMPLE, "query": "fragment F on Query { a }", "root": {}},
     rejected("$")),
    ("reject-mutation",
     {"schema": SIMPLE, "query": "mutation { a }", "root": {}}, rejected("$")),
    ("reject-subscription",
     {"schema": SIMPLE, "query": "subscription { a }", "root": {}},
     rejected("$")),
    ("reject-anonymous-plus-named",
     {"schema": SIMPLE, "query": "{ a } query B { a }", "root": {}},
     rejected("$")),
    ("reject-duplicate-fragments",
     {"schema": SIMPLE,
      "query": "{ ...F } fragment F on Query { a } fragment F on Query { b }",
      "root": {}}, rejected("$")),
    ("reject-unused-fragment",
     {"schema": SIMPLE, "query": "{ a } fragment F on Query { a }", "root": {}},
     rejected("$")),
    ("reject-unknown-field",
     {"schema": SIMPLE, "query": "{ nope }", "root": {}}, rejected("nope")),
    ("reject-fragment-cycle",
     {"schema": SIMPLE,
      "query": "{ ...F } fragment F on Query { ...G } "
               "fragment G on Query { ...F }",
      "root": {}}, rejected("$")),
    ("reject-directive-on-operation",
     {"schema": SIMPLE, "query": "query @skip(if: true) { a }", "root": {}},
     rejected("$")),
    ("reject-include-non-boolean",
     {"schema": SIMPLE, "query": "{ a @include(if: 1) }", "root": {}},
     rejected("a")),
    ("reject-skip-without-if",
     {"schema": SIMPLE, "query": "{ a @skip }", "root": {}}, rejected("a")),
    ("reject-typename-with-selection",
     {"schema": SIMPLE, "query": "{ __typename { a } }", "root": {}},
     rejected("__typename")),
    ("reject-field-on-union",
     {"schema": SCHEMA_ABSTRACT, "query": "{ entity { id } }", "root": {}},
     rejected("entity")),
    # --- schema restrictions ------------------------------------------------------
    ("reject-float", {"schema": "type Query { x: Float }", "query": "{ x }",
     "root": {}}, rejected("$")),
    ("reject-id", {"schema": "type Query { x: ID }", "query": "{ x }",
     "root": {}}, rejected("$")),
    ("reject-enum",
     {"schema": "enum E { A B } type Query { x: E }", "query": "{ x }",
      "root": {}}, rejected("$")),
    ("reject-custom-scalar",
     {"schema": "scalar S type Query { x: S }", "query": "{ x }", "root": {}},
     rejected("$")),
    ("reject-input-object",
     {"schema": "input I { a: String } type Query { f(i: I): String }",
      "query": "{ f }", "root": {}}, rejected("$")),
    ("reject-sdl-field-arguments",
     {"schema": "type Query { f(a: String): String }", "query": "{ f }",
      "root": {}}, rejected("$")),
    ("reject-custom-directive-def",
     {"schema": "directive @c on FIELD_DEFINITION  type Query { a: String }",
      "query": "{ a }", "root": {}}, rejected("$")),
    ("reject-duplicate-type",
     {"schema": "type Query { a: String } type Query { b: String }",
      "query": "{ a }", "root": {}}, rejected("$")),
    ("reject-no-query-root",
     {"schema": "type Foo { a: String }", "query": "{ a }", "root": {}},
     rejected("$")),
    # --- field merging (self-written §5.3.2) ---------------------------------------
    ("reject-conflict-different-fields",
     {"schema": SIMPLE, "query": "{ x: a x: b }", "root": {}}, rejected("x")),
    ("reject-conflict-shape",
     {"schema": SIMPLE, "query": "{ x: a x: n }", "root": {}}, rejected("x")),
    ("reject-conflict-nonnull-shape",
     {"schema": "type Query { a: String b: String! }",
      "query": "{ x: a x: b }", "root": {}}, rejected("x")),
    ("reject-conflict-list-shape",
     {"schema": "type Query { a: [String] b: String }",
      "query": "{ x: a x: b }", "root": {}}, rejected("x")),
    ("reject-conflict-subfield",
     {"schema": SCHEMA_OBJECTS, "query": "{ user { x: id } user { x: age } }",
      "root": {}}, rejected("user")),
    ("reject-conflict-via-fragments",
     {"schema": SIMPLE,
      "query": "{ ...F ...G } fragment F on Query { x: a } "
               "fragment G on Query { x: b }",
      "root": {}}, rejected("x")),
    ("reject-conflict-fragment-vs-direct",
     {"schema": SIMPLE,
      "query": "{ x: a ...G } fragment G on Query { x: b }", "root": {}},
     rejected("x")),
    ("reject-conflict-nested-fragment",
     {"schema": SCHEMA_OBJECTS,
      "query": "{ user { ...F x: age } } fragment F on User { x: id }",
      "root": {}}, rejected("user")),
    # pre-validation: skipping does not exempt checks
    ("reject-conflict-despite-skip",
     {"schema": SIMPLE, "query": "{ x: a @skip(if: true) x: b }", "root": {}},
     rejected("x")),
    ("reject-unknown-field-despite-skip",
     {"schema": SIMPLE, "query": "{ nope @skip(if: true) }", "root": {}},
     rejected("nope")),
    # pre-validation: mutual exclusivity does not exempt the shape check
    ("reject-conflict-exclusive-shape",
     {"schema": SCHEMA_ABSTRACT,
      "query": "{ node { ... on User { x: name } ... on Org { x: id } } }",
      "root": {}}, rejected("node")),
    ("reject-conflict-exclusive-list-shape",
     {"schema": "type A { x: [String] } type B { x: String } "
                "type Query { a: A b: B }",
      "query": "{ a { x } b { x } }", "root": {}}, rejected("a")),
    # --- execution: shape/type mismatches are field errors ---------------------------
    ("field-error-object-gets-scalar",
     {"schema": SCHEMA_OBJECTS, "query": "{ user { id } }",
      "root": {"user": 5}},
     {"data": {"user": None}, "errors": [["user"]]}),
    ("field-error-object-gets-list",
     {"schema": SCHEMA_OBJECTS, "query": "{ user { id } }",
      "root": {"user": []}},
     {"data": {"user": None}, "errors": [["user"]]}),
    ("field-error-scalar-gets-object",
     {"schema": SCHEMA_OBJECTS, "query": "{ name }",
      "root": {"name": {"x": 1}}},
     {"data": {"name": None}, "errors": [["name"]]}),
    ("field-error-scalar-gets-list",
     {"schema": SCHEMA_OBJECTS, "query": "{ name }",
      "root": {"name": ["a"]}},
     {"data": {"name": None}, "errors": [["name"]]}),
    ("field-error-list-gets-object",
     {"schema": SCHEMA_OBJECTS, "query": "{ tags }",
      "root": {"tags": {"0": "a"}}},
     {"data": {"tags": None}, "errors": [["tags"]]}),
    ("field-error-list-gets-string",
     {"schema": SCHEMA_OBJECTS, "query": "{ tags }",
      "root": {"tags": "ab"}},
     {"data": {"tags": None}, "errors": [["tags"]]}),
    ("field-error-int-gets-bool",
     {"schema": SCHEMA_OBJECTS, "query": "{ count }",
      "root": {"count": True}},
     {"data": {"count": None}, "errors": [["count"]]}),
    ("field-error-int-gets-string",
     {"schema": SCHEMA_OBJECTS, "query": "{ count }",
      "root": {"count": "1"}},
     {"data": {"count": None}, "errors": [["count"]]}),
    ("field-error-string-gets-int",
     {"schema": SCHEMA_OBJECTS, "query": "{ name }",
      "root": {"name": 5}},
     {"data": {"name": None}, "errors": [["name"]]}),
    ("field-error-abstract-non-string-typename",
     {"schema": SCHEMA_ABSTRACT, "query": "{ node { id } }",
      "root": {"node": {"__typename": 5, "id": "u1"}}},
     {"data": {"node": None}, "errors": [["node"]]}),
    ("field-error-abstract-gets-scalar",
     {"schema": SCHEMA_ABSTRACT, "query": "{ node { id } }",
      "root": {"node": 5}},
     {"data": {"node": None}, "errors": [["node"]]}),
    ("field-error-abstract-typename-is-interface",
     {"schema": SCHEMA_ABSTRACT, "query": "{ node { id } }",
      "root": {"node": {"__typename": "Node", "id": "u1"}}},
     {"data": {"node": None}, "errors": [["node"]]}),
    # --- execution: backend-specific guarantees ---------------------------------------
    ("concrete-ignores-source-typename",
     {"schema": SCHEMA_OBJECTS, "query": "{ user { __typename id } }",
      "root": {"user": {"__typename": "Wrong", "id": "u1"}}},
     {"data": {"user": {"__typename": "User", "id": "u1"}}, "errors": []}),
    ("nullable-list-stays-null",
     {"schema": SCHEMA_OBJECTS, "query": "{ nums }",
      "root": {"nums": None}},
     {"data": {"nums": None}, "errors": []}),
    ("root-revoked-data-null",
     {"schema": SCHEMA_OBJECTS, "query": "{ flag }",
      "root": {"flag": None}},
     {"data": None, "errors": [["flag"]]}),
    ("alias-keys-in-output",
     {"schema": SIMPLE, "query": "{ x: a y: b }",
      "root": {"a": "1", "b": "2"}},
     {"data": {"x": "1", "y": "2"}, "errors": []}),
]
