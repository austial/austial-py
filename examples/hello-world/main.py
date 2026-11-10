"""A complete Austial app in one file: DI, a guard, a pipe-validated body and Swagger docs.

pip install austial uvicorn
uvicorn main:app --reload        # then open http://localhost:8000/docs
"""

from dataclasses import dataclass

from pydantic import BaseModel

from austial import (
    AustialFactory,
    Body,
    CanActivate,
    Controller,
    ExecutionContext,
    Get,
    Injectable,
    Module,
    NotFoundException,
    Param,
    Post,
    UseGuards,
)


class CreateCatDto(BaseModel):
    name: str
    age: int


@dataclass
class Cat:
    id: int
    name: str
    age: int


@Injectable()
class CatsService:
    def __init__(self) -> None:
        self._cats: list[Cat] = []

    def create(self, dto: CreateCatDto) -> Cat:
        cat = Cat(id=len(self._cats) + 1, name=dto.name, age=dto.age)
        self._cats.append(cat)
        return cat

    def find_one(self, id: int) -> Cat:
        for cat in self._cats:
            if cat.id == id:
                return cat
        raise NotFoundException(f"Cat {id} not found")


@Injectable()
class ApiKeyGuard(CanActivate):
    async def can_activate(self, context: ExecutionContext) -> bool:
        return context.switch_to_http().get_request().headers.get("x-api-key") == "secret"


@Controller("cats")
class CatsController:
    def __init__(self, cats: CatsService) -> None:  # injected by type hint
        self.cats = cats

    @Post()
    @UseGuards(ApiKeyGuard)
    async def create(self, dto: CreateCatDto = Body()) -> Cat:
        return self.cats.create(dto)

    @Get(":id")
    async def find_one(self, id: int = Param()) -> Cat:
        return self.cats.find_one(id)


@Module(controllers=[CatsController], providers=[CatsService, ApiKeyGuard])
class AppModule:
    pass


app = AustialFactory.create(AppModule, title="Cats")
