from austial import Controller, Get, UseGuards

from src.modules.health.guards.api_key_guard import ApiKeyGuard
from src.modules.health.health_dto import HealthResponseDto
from src.modules.health.health_service import HealthService


@Controller("health")
class HealthController:
    def __init__(self, health_service: HealthService):
        self.health_service = health_service

    @Get()
    async def check(self) -> HealthResponseDto:
        return await self.health_service.check()

    @Get("protected")
    @UseGuards(ApiKeyGuard)
    async def protected(self):
        return {"message": "You presented a valid x-api-key header."}
