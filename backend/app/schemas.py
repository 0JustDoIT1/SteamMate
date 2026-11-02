from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """API 응답 공용 기반: 파이썬은 snake_case, JSON은 camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
