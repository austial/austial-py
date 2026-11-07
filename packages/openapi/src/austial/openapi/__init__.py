"""``austial.openapi`` -- OpenAPI/Swagger decorators and document setup, mirrors ``@nestjs/swagger``.

from austial.openapi import ApiTags, ApiOperation, ApiOkResponse, ApiBearerAuth, DocumentBuilder, SwaggerModule
"""

from austial.openapi.decorators import (
    ApiAcceptedResponse,
    ApiBadRequestResponse,
    ApiBasicAuth,
    ApiBearerAuth,
    ApiConflictResponse,
    ApiCreatedResponse,
    ApiExcludeController,
    ApiExcludeEndpoint,
    ApiForbiddenResponse,
    ApiInternalServerErrorResponse,
    ApiNoContentResponse,
    ApiNotFoundResponse,
    ApiOkResponse,
    ApiOperation,
    ApiProperty,
    ApiPropertyOptional,
    ApiResponse,
    ApiSecurity,
    ApiTags,
    ApiTooManyRequestsResponse,
    ApiUnauthorizedResponse,
    ApiUnprocessableEntityResponse,
)
from austial.openapi.document import DocumentBuilder, OpenApiConfig, SwaggerModule

__all__ = [
    "ApiAcceptedResponse",
    "ApiBadRequestResponse",
    "ApiBasicAuth",
    "ApiBearerAuth",
    "ApiConflictResponse",
    "ApiCreatedResponse",
    "ApiExcludeController",
    "ApiExcludeEndpoint",
    "ApiForbiddenResponse",
    "ApiInternalServerErrorResponse",
    "ApiNoContentResponse",
    "ApiNotFoundResponse",
    "ApiOkResponse",
    "ApiOperation",
    "ApiProperty",
    "ApiPropertyOptional",
    "ApiResponse",
    "ApiSecurity",
    "ApiTags",
    "ApiTooManyRequestsResponse",
    "ApiUnauthorizedResponse",
    "ApiUnprocessableEntityResponse",
    "DocumentBuilder",
    "OpenApiConfig",
    "SwaggerModule",
]
