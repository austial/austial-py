"""``austial.graphql`` -- serve a Strawberry GraphQL schema with dependency injection in resolvers.

from austial.graphql import GraphQLModule, inject
"""

from austial.graphql.graphql_module import GRAPHQL_OPTIONS, GraphQLModule, GraphQLMount, GraphQLOptions, inject

__all__ = ["GRAPHQL_OPTIONS", "GraphQLModule", "GraphQLMount", "GraphQLOptions", "inject"]
