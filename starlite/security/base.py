from __future__ import annotations

from abc import ABC, abstractmethod
from copy import copy
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterable, TypeVar

from starlite import Response
from starlite.connection import ASGIConnection
from starlite.di import Provide
from starlite.middleware.authentication import AbstractAuthenticationMiddleware
from starlite.types import (
    ControllerRouterHandler,
    Guard,
    Scopes,
    SyncOrAsyncUnion,
    TypeEncodersMap,
)
from starlite.utils.sync import AsyncCallable

__all__ = ("AbstractSecurityConfig",)


if TYPE_CHECKING:
    from pydantic_openapi_schema.v3_1_0 import Components, SecurityRequirement

    from starlite.config.app import AppConfig
    from starlite.enums import MediaType, OpenAPIMediaType
    from starlite.middleware.base import DefineMiddleware
    from starlite.types import ResponseCookies


UserType = TypeVar("UserType")
AuthType = TypeVar("AuthType")


class AbstractSecurityConfig(ABC, Generic[UserType, AuthType]):
    """A base class for Security Configs - this class can be used on the application level
    or be manually configured on the router / controller level to provide auth.
    """

    authentication_middleware_class: type[AbstractAuthenticationMiddleware]
    """The authentication middleware class to use.

    Must inherit from
    :class:`AbstractAuthenticationMiddleware <starlite.middleware.authentication.AbstractAuthenticationMiddleware>`
    """
    guards: Iterable[Guard] | None = None
    """An iterable of guards to call for requests, providing authorization functionalities."""
    exclude: str | list[str] | None = None
    """A pattern or list of patterns to skip in the authentication middleware."""
    exclude_opt_key: str = "exclude_from_auth"
    """An identifier to use on routes to disable authentication and authorization checks for a particular route."""
    scopes: Scopes | None = None
    """ASGI scopes processed by the authentication middleware, if ``None``, both ``http`` and ``websocket`` will be
    processed."""
    route_handlers: Iterable[ControllerRouterHandler] | None = None
    """An optional iterable of route handlers to register."""
    dependencies: dict[str, Provide] | None = None
    """An optional dictionary of dependency providers."""
    retrieve_user_handler: Callable[[Any, ASGIConnection], SyncOrAsyncUnion[Any | None]]
    """Callable that receives the ``auth`` value from the authentication middleware and returns a ``user`` value.

    Notes:
        - User and Auth can be any arbitrary values specified by the security backend.
        - The User and Auth values will be set by the middleware as ``scope["user"]`` and ``scope["auth"]`` respectively.
          Once provided, they can access via the ``connection.user`` and ``connection.auth`` properties.
        - The callable can be sync or async. If it is sync, it will be wrapped to support async.

    """
    type_encoders: TypeEncodersMap | None = None
    """A mapping of types to callables that transform them into types supported for serialization."""

    def on_app_init(self, app_config: AppConfig) -> AppConfig:
        """Handle app init by injecting middleware, guards etc. into the app. This method can be used only on the app
        level.

        Args:
            app_config: An instance of :class:`AppConfig <starlite.config.AppConfig>`

        Returns:
            The :class:`AppConfig <starlite.config.AppConfig>`.
        """
        app_config.middleware.insert(0, self.middleware)

        if app_config.openapi_config:
            app_config.openapi_config = copy(app_config.openapi_config)
            if isinstance(app_config.openapi_config.components, list):
                app_config.openapi_config.components.append(self.openapi_components)
            elif app_config.openapi_config.components:
                app_config.openapi_config.components = [self.openapi_components, app_config.openapi_config.components]
            else:
                app_config.openapi_config.components = [self.openapi_components]

            if isinstance(app_config.openapi_config.security, list):
                app_config.openapi_config.security.append(self.security_requirement)
            else:
                app_config.openapi_config.security = [self.security_requirement]

        if self.guards:
            app_config.guards.extend(self.guards)

        if self.dependencies:
            app_config.dependencies.update(self.dependencies)

        if self.route_handlers:
            app_config.route_handlers.extend(self.route_handlers)

        if self.type_encoders is None:
            self.type_encoders = app_config.type_encoders

        return app_config

    def create_response(
        self,
        content: Any | None,
        status_code: int,
        media_type: MediaType | OpenAPIMediaType | str,
        headers: dict[str, Any] | None = None,
        cookies: ResponseCookies | None = None,
    ) -> Response[Any]:
        """Create a response object.

        Handles setting the type encoders mapping on the response.

        Args:
            content: A value for the response body that will be rendered into bytes string.
            status_code: An HTTP status code.
            media_type: A value for the response 'Content-Type' header.
            headers: A string keyed dictionary of response headers. Header keys are insensitive.
            cookies: A list of :class:`Cookie <starlite.datastructures.Cookie>` instances to be set under
                the response 'Set-Cookie' header.

        Returns:
            A response object.
        """
        return Response(
            content=content,
            status_code=status_code,
            media_type=media_type,
            headers=headers,
            cookies=cookies,
            type_encoders=self.type_encoders,
        )

    def __post_init__(self) -> None:
        self.retrieve_user_handler = AsyncCallable(self.retrieve_user_handler)

    @property
    @abstractmethod
    def openapi_components(self) -> Components:  # pragma: no cover
        """Create OpenAPI documentation for the JWT auth schema used.

        Returns:
            An :class:`Components <pydantic_openapi_schema.v3_1_0.components.Components>` instance.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def security_requirement(self) -> SecurityRequirement:  # pragma: no cover
        """Return OpenAPI 3.1.

        :class:`SecurityRequirement <pydantic_openapi_schema.v3_1_0.security_requirement.SecurityRequirement>` for the auth
        backend.

        Returns:
            An OpenAPI 3.1 :class:`SecurityRequirement <pydantic_openapi_schema.v3_1_0.security_requirement.SecurityRequirement>` dictionary.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def middleware(self) -> DefineMiddleware:  # pragma: no cover
        """Create an instance of the config's ``authentication_middleware_class`` attribute and any required kwargs,
        wrapping it in Starlite's ``DefineMiddleware``.

        Returns:
            An instance of :class:`DefineMiddleware <starlite.middleware.base.DefineMiddleware>`.
        """
        raise NotImplementedError