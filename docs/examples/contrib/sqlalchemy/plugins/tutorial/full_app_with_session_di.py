from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from litestar import Litestar, get, post, put
from litestar.datastructures import State
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_409_CONFLICT

TodoType = Dict[str, Any]
TodoCollectionType = List[TodoType]


class Base(DeclarativeBase): ...


class TodoItem(Base):
    __tablename__ = "todo_items"

    title: Mapped[str] = mapped_column(primary_key=True)
    done: Mapped[bool]


@asynccontextmanager
async def db_connection(app: Litestar) -> AsyncGenerator[None, None]:
    engine = getattr(app.state, "engine", None)
    if engine is None:
        engine = create_async_engine("sqlite+aiosqlite:///todo.sqlite")
        app.state.engine = engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield
    finally:
        await engine.dispose()


sessionmaker = async_sessionmaker(expire_on_commit=False)


async def provide_transaction(state: State) -> AsyncGenerator[AsyncSession, None]:
    async with sessionmaker(bind=state.engine) as session:
        try:
            async with session.begin():
                yield session
        except IntegrityError as exc:
            raise ClientException(
                status_code=HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc


def serialize_todo(todo: TodoItem) -> TodoType:
    return {"title": todo.title, "done": todo.done}


async def get_todo_by_title(todo_name, session: AsyncSession) -> TodoItem:
    query = select(TodoItem).where(TodoItem.title == todo_name)
    result = await session.execute(query)
    try:
        return result.scalar_one()
    except NoResultFound as e:
        raise NotFoundException(detail=f"TODO {todo_name!r} not found") from e


async def get_todo_list(done: Optional[bool], session: AsyncSession) -> List[TodoItem]:
    query = select(TodoItem)
    if done is not None:
        query = query.where(TodoItem.done.is_(done))

    result = await session.execute(query)
    return result.scalars().all()


@get("/")
async def get_list(
    transaction: AsyncSession, done: Optional[bool] = None
) -> TodoCollectionType:
    return [serialize_todo(todo) for todo in await get_todo_list(done, transaction)]


@post("/")
async def add_item(data: TodoType, transaction: AsyncSession) -> TodoType:
    new_todo = TodoItem(title=data["title"], done=data["done"])
    transaction.add(new_todo)
    return serialize_todo(new_todo)


@put("/{item_title:str}")
async def update_item(
    item_title: str, data: TodoType, transaction: AsyncSession
) -> TodoType:
    todo_item = await get_todo_by_title(item_title, transaction)
    todo_item.title = data["title"]
    todo_item.done = data["done"]
    return serialize_todo(todo_item)


app = Litestar(
    [get_list, add_item, update_item],
    dependencies={"transaction": provide_transaction},
    lifespan=[db_connection],
)
