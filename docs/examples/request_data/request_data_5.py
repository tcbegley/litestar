from dataclasses import dataclass

from litestar import Litestar, post
from litestar.enums import RequestEncodingType
from litestar.params import Body


@dataclass
class User:
    id: int
    name: str


@post(path="/")
async def create_user(
    data: User = Body(media_type=RequestEncodingType.MULTI_PART),
) -> User:
    return data


app = Litestar(route_handlers=[create_user])