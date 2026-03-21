"""Common API models shared across all endpoints."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ErrorResponse(BaseModel):
    """Standard error envelope returned by all error handlers."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        serialize_by_alias=True,
    )

    success: bool = False
    error: str
