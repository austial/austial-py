"""``austial.http`` -- an injectable HTTP client, mirrors ``@nestjs/axios``.

from austial.http import HttpModule, HttpService
"""

from austial.http.http_module import HttpModule
from austial.http.http_service import HTTP_OPTIONS, HttpModuleOptions, HttpService, HttpStatusError

__all__ = ["HTTP_OPTIONS", "HttpModule", "HttpModuleOptions", "HttpService", "HttpStatusError"]
