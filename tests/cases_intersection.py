"""Legal-intersection cases: valid under both this backend's restrictions and
full GraphQL. Each output is compared against the reference library
(graphql-core's executor): data and error paths must match exactly.
"""

SCHEMA_OBJECTS = """
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
}
type User {
  id: String!
  name: String
  age: Int
  vip: Boolean
  tags: [String]
  friend: User
}
"""

SCHEMA_ABSTRACT = """
interface Node { id: String! }
type User implements Node { id: String!  name: String }
type Org implements Node { id: String!  title: String }
union Entity = User | Org
type Query {
  node: Node
  entity: Entity
  nodes: [Node]
  mustNodes: [Node!]!
}
"""

# (name, schema_sdl, query, root)
INTERSECTION_CASES = [
    # --- basics: aliases, missing keys, nulls ------------------------------
    ("scalars", SCHEMA_OBJECTS, "{ name flag count }",
     {"name": "n", "flag": True, "count": 3}),
    ("aliases", SCHEMA_OBJECTS, "{ a: name b: flag c: count }",
     {"name": "x", "flag": False, "count": 0}),
    ("missing-keys-become-null", SCHEMA_OBJECTS, "{ name count }",
     {}),
    ("null-root", SCHEMA_OBJECTS, "{ name count }", None),
    ("non-object-root", SCHEMA_OBJECTS, "{ name count }", 7),
    ("typename-root", SCHEMA_OBJECTS, "{ __typename }", {}),
    ("typename-alias", SCHEMA_OBJECTS, "{ t: __typename }", {}),
    # --- nesting and merging ------------------------------------------------
    ("nested-object", SCHEMA_OBJECTS, "{ user { id name age vip } }",
     {"user": {"id": "u1", "name": "Ann", "age": 30, "vip": True}}),
    ("nested-missing", SCHEMA_OBJECTS, "{ user { id name } }", {"user": {}}),
    ("same-key-merge", SCHEMA_OBJECTS, "{ user { id } user { name } }",
     {"user": {"id": "u1", "name": "Ann"}}),
    ("same-key-merge-via-alias", SCHEMA_OBJECTS,
     "{ u: user { id } u: user { name } }", {"user": {"id": "u1", "name": "Ann"}}),
    ("deep-friend-chain", SCHEMA_OBJECTS,
     "{ user { id friend { id friend { id } } } }",
     {"user": {"id": "a", "friend": {"id": "b", "friend": {"id": "c"}}}}),
    ("deep-friend-null", SCHEMA_OBJECTS,
     "{ user { id friend { id } } }", {"user": {"id": "a", "friend": None}}),
    # --- directives ----------------------------------------------------------
    ("skip-true", SCHEMA_OBJECTS, "{ a: name @skip(if: true) b: flag }",
     {"name": "x", "flag": True}),
    ("skip-false", SCHEMA_OBJECTS, "{ a: name @skip(if: false) }",
     {"name": "x"}),
    ("include-false", SCHEMA_OBJECTS, "{ a: name @include(if: false) b: flag }",
     {"name": "x", "flag": True}),
    ("include-true", SCHEMA_OBJECTS, "{ a: name @include(if: true) }",
     {"name": "x"}),
    ("skip-on-inline-fragment", SCHEMA_OBJECTS,
     "{ ... @skip(if: true) { name } flag }", {"name": "x", "flag": True}),
    ("skip-on-fragment-spread", SCHEMA_OBJECTS,
     "{ ...F @include(if: false) flag } fragment F on Query { name }",
     {"name": "x", "flag": True}),
    # --- fragments -------------------------------------------------------------
    ("named-fragment", SCHEMA_OBJECTS,
     "{ user { ...U } } fragment U on User { id name }",
     {"user": {"id": "u1", "name": "Ann"}}),
    ("fragment-on-query", SCHEMA_OBJECTS,
     "{ ...Q } fragment Q on Query { name flag }",
     {"name": "x", "flag": True}),
    ("nested-fragments", SCHEMA_OBJECTS,
     "{ user { ...U } } fragment U on User { ...I } fragment I on User { id }",
     {"user": {"id": "u1"}}),
    ("inline-fragment-no-condition", SCHEMA_OBJECTS, "{ ... { name } }",
     {"name": "x"}),
    ("fragment-merge-same-key", SCHEMA_OBJECTS,
     "{ user { ...U } user { ...I } } "
     "fragment U on User { id } fragment I on User { name }",
     {"user": {"id": "u1", "name": "Ann"}}),
    # --- lists -----------------------------------------------------------------
    ("scalar-list", SCHEMA_OBJECTS, "{ tags }", {"tags": ["a", "b"]}),
    ("scalar-list-null-item", SCHEMA_OBJECTS, "{ tags }",
     {"tags": ["a", None, "b"]}),
    ("empty-list", SCHEMA_OBJECTS, "{ tags }", {"tags": []}),
    ("object-list", SCHEMA_OBJECTS, "{ users { id tags } }",
     {"users": [{"id": "a", "tags": ["x"]}, {"id": "b", "tags": None}]}),
    ("object-list-null-item", SCHEMA_OBJECTS, "{ users { id } }",
     {"users": [{"id": "a"}, None, {"id": "b"}]}),
    ("list-order-preserved", SCHEMA_OBJECTS, "{ nums }", {"nums": [3, 1, 2]}),
    # --- non-null bubbling -------------------------------------------------------
    ("spec-example", "type Query { a: [Int!] }", "{ z: a }", {"a": [None]}),
    ("nonnull-item-revokes-list", SCHEMA_OBJECTS, "{ nums }",
     {"nums": [1, None, 2]}),
    ("list-stops-after-revoke", SCHEMA_OBJECTS, "{ nums }",
     {"nums": [None, None, None]}),
    ("nonnull-scalar-at-root", SCHEMA_OBJECTS, "{ flag }", {"flag": None}),
    ("root-revoked-data-null", SCHEMA_OBJECTS, "{ flag name }",
     {"flag": None, "name": "x"}),
    ("object-revoked-by-child", SCHEMA_OBJECTS, "{ user { id name } }",
     {"user": {"id": None, "name": "Ann"}}),
    ("object-revoke-stops-remaining-fields", SCHEMA_OBJECTS,
     "{ user { id name } }", {"user": {"id": None, "name": None}}),
    ("outer-continues-after-revoke", SCHEMA_OBJECTS,
     "{ a: user { id } b: name }", {"user": {"id": None}, "name": "kept"}),
    ("nonnull-object-revokes-root", SCHEMA_OBJECTS, "{ mustUser { id } name }",
     {"mustUser": {"id": None}, "name": "x"}),
    ("nested-list-bubble", SCHEMA_OBJECTS, "{ matrix }",
     {"matrix": [[1], None, [2]]}),
    ("nested-list-inner-item", SCHEMA_OBJECTS, "{ matrix }",
     {"matrix": [[1, None]]}),
    ("error-order-depth-first", SCHEMA_OBJECTS, "{ user { id } nums }",
     {"user": {"id": None}, "nums": [None]}),
    ("two-errors-two-fields", SCHEMA_OBJECTS, "{ a: flag b: user { id } }",
     {"flag": None, "user": {"id": None}}),
    # --- abstract types -----------------------------------------------------------
    ("interface-basic", SCHEMA_ABSTRACT,
     "{ node { id ... on User { name } ... on Org { title } } }",
     {"node": {"__typename": "User", "id": "u1", "name": "Ann"}}),
    ("interface-other-branch", SCHEMA_ABSTRACT,
     "{ node { id ... on User { name } ... on Org { title } } }",
     {"node": {"__typename": "Org", "id": "o1", "title": "Acme"}}),
    ("interface-typename-meta", SCHEMA_ABSTRACT, "{ node { __typename id } }",
     {"node": {"__typename": "Org", "id": "o1"}}),
    ("union-basic", SCHEMA_ABSTRACT,
     "{ entity { ... on User { name } ... on Org { title } } }",
     {"entity": {"__typename": "User", "name": "Ann"}}),
    ("union-typename", SCHEMA_ABSTRACT, "{ entity { __typename } }",
     {"entity": {"__typename": "Org"}}),
    ("interface-list-mixed", SCHEMA_ABSTRACT, "{ nodes { id __typename } }",
     {"nodes": [{"__typename": "User", "id": "u1"},
                {"__typename": "Org", "id": "o1"}]}),
    ("interface-list-with-null", SCHEMA_ABSTRACT, "{ nodes { id } }",
     {"nodes": [{"__typename": "User", "id": "u1"}, None]}),
    ("abstract-missing-typename", SCHEMA_ABSTRACT, "{ node { id } }",
     {"node": {"id": "u1"}}),
    ("abstract-unknown-typename", SCHEMA_ABSTRACT, "{ node { id } }",
     {"node": {"__typename": "Nope", "id": "u1"}}),
    ("abstract-wrong-type-typename", SCHEMA_ABSTRACT, "{ entity { __typename } }",
     {"entity": {"__typename": "Query"}}),
    ("abstract-nonnull-list-bubble", SCHEMA_ABSTRACT, "{ mustNodes { id } }",
     {"mustNodes": [{"__typename": "User", "id": "u1"}, None]}),
    ("abstract-child-bubble", SCHEMA_ABSTRACT, "{ node { id } }",
     {"node": {"__typename": "User", "id": None}}),
    ("fragment-on-interface", SCHEMA_ABSTRACT,
     "{ node { ...N } } fragment N on Node { id }",
     {"node": {"__typename": "User", "id": "u1"}}),
    ("fragment-on-union", SCHEMA_ABSTRACT,
     "{ entity { ...E } } fragment E on Entity { ... on User { name } }",
     {"entity": {"__typename": "User", "name": "Ann"}}),
    ("exclusive-alias-different-fields", SCHEMA_ABSTRACT,
     "{ node { ... on User { x: name } ... on Org { x: title } } }",
     {"node": {"__typename": "Org", "title": "Acme"}}),
    # --- more merging / collection ------------------------------------------------
    ("alias-duplication-same-field", SCHEMA_OBJECTS, "{ a: name a: name }",
     {"name": "x"}),
    ("skip-merge", SCHEMA_OBJECTS, "{ a: name @skip(if: true) a: name }",
     {"name": "x"}),
    ("custom-schema-block", "schema { query: MyQ } type MyQ { a: String }",
     "{ a }", {"a": "x"}),
    ("deep-error-path", SCHEMA_OBJECTS, "{ user { friend { id } } }",
     {"user": {"friend": {"id": None}}}),
    ("error-in-object-list", SCHEMA_OBJECTS, "{ users { id } }",
     {"users": [{"id": "a"}, {"id": None}]}),
    ("object-revoke-stops-siblings", "type Query { o: O } "
     "type O { x: Int! y: Int! }", "{ o { x y } }", {"o": {"x": None, "y": None}}),
    # --- collection order and misc --------------------------------------------------
    ("skip-then-collect-order", SCHEMA_OBJECTS,
     "{ a: name @skip(if: true) b: flag a: name }",
     {"name": "x", "flag": True}),
    ("duplicate-spread-collected-once", SCHEMA_OBJECTS,
     "{ ...F ...F } fragment F on Query { name }", {"name": "x"}),
    ("alias-named-like-meta", SCHEMA_OBJECTS, "{ __typename: name }",
     {"name": "x"}),
    ("covariant-interface-field",
     "interface Node { id: String!  friend: Node } "
     "type User implements Node { id: String!  friend: User } "
     "type Query { node: Node }",
     "{ node { id friend { id } } }",
     {"node": {"__typename": "User", "id": "u1",
               "friend": {"__typename": "User", "id": "u2"}}}),
    ("deep-nonnull-chain-bubble", "type Query { a: [[Int!]!]! }",
     "{ a }", {"a": [[None]]}),
    ("abstract-item-error-in-list", SCHEMA_ABSTRACT, "{ nodes { id } }",
     {"nodes": [{"__typename": "User", "id": "u1"}, {"id": "no-typename"},
                {"__typename": "Org", "id": "o1"}]}),
    ("all-fields-skipped", SCHEMA_OBJECTS, "{ a: name @skip(if: true) }",
     {"name": "x"}),
]
