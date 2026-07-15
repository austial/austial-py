"""Austial -- a NestJS-inspired, batteries-included web framework for Python,
built on top of FastAPI.

Quickstart::

    from austial import Module, Controller, Get, Injectable, AustialFactory

Most day-to-day symbols (decorators, exceptions, guards, etc.) are re-exported
here for convenience, mirroring how ``@nestjs/common`` re-exports everything
Nest apps need. Deeper framework internals live in ``austial.core``,
``austial.config``, ``austial.database``, ``austial.terminus``,
``austial.testing`` and ``austial.cli``.
"""

# This distribution ("austial") ships the real top-level ``austial/__init__.py``,
# while ``austial.common``, ``austial.core``, ``austial.config``, ``austial.database``,
# ``austial.terminus``, ``austial.testing`` and ``austial.cli`` each live in their own
# sibling distribution under packages/. pkgutil-style namespace extension merges those
# sibling ``austial/<name>`` directories onto this package's search path so that
# ``import austial.common`` etc. keeps resolving, matching NestJS's split into
# separately-published `@nestjs/*` packages while keeping this convenience barrel intact.
import importlib.metadata
from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)

from austial.common import (
    AllExceptionsFilter,
    ArgumentMetadata,
    ArgumentsHost,
    BadRequestException,
    Body,
    CallHandler,
    CanActivate,
    Catch,
    ConflictException,
    Controller,
    Delete,
    ExceptionFilter,
    ExecutionContext,
    ForbiddenException,
    Get,
    Global,
    Head,
    Header,
    Headers,
    HttpCode,
    HttpException,
    Inject,
    Injectable,
    InternalServerErrorException,
    Logger,
    LoggingMiddleware,
    MethodNotAllowedException,
    MiddlewareConsumer,
    Module,
    NestInterceptor,
    NestMiddleware,
    NotFoundException,
    NotImplementedException,
    Optional_,
    Options,
    Param,
    Patch,
    PipeTransform,
    Post,
    Put,
    Query,
    Req,
    Res,
    Scope,
    ServiceUnavailableException,
    TooManyRequestsException,
    TransformInterceptor,
    UnauthorizedException,
    UnprocessableEntityException,
    UseFilters,
    UseGuards,
    UseInterceptors,
    UsePipes,
    ValidationPipe,
)
from austial.core import DynamicModule, Reflector
from austial.core.app import AustialApplication
from austial.core.factory import AustialFactory

# Derived from the installed distribution's metadata (itself computed by hatch-vcs
# from the nearest git tag), so this never drifts out of sync with a manual release
# version bump again.
__version__ = importlib.metadata.version("austial")

__all__ = [
    "AllExceptionsFilter",
    "ArgumentMetadata",
    "ArgumentsHost",
    "AustialApplication",
    "AustialFactory",
    "BadRequestException",
    "Body",
    "CallHandler",
    "CanActivate",
    "Catch",
    "ConflictException",
    "Controller",
    "Delete",
    "DynamicModule",
    "ExceptionFilter",
    "ExecutionContext",
    "ForbiddenException",
    "Get",
    "Global",
    "Head",
    "Header",
    "Headers",
    "HttpCode",
    "HttpException",
    "Inject",
    "Injectable",
    "InternalServerErrorException",
    "Logger",
    "LoggingMiddleware",
    "MethodNotAllowedException",
    "MiddlewareConsumer",
    "Module",
    "NestInterceptor",
    "NestMiddleware",
    "NotFoundException",
    "NotImplementedException",
    "Options",
    "Optional_",
    "Param",
    "Patch",
    "PipeTransform",
    "Post",
    "Put",
    "Query",
    "Reflector",
    "Req",
    "Res",
    "Scope",
    "ServiceUnavailableException",
    "TooManyRequestsException",
    "TransformInterceptor",
    "UnauthorizedException",
    "UnprocessableEntityException",
    "UseFilters",
    "UseGuards",
    "UseInterceptors",
    "UsePipes",
    "ValidationPipe",
]
