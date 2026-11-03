from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """API 응답 공용 기반: 파이썬은 snake_case, JSON은 camelCase."""

    # 응답 JSON에는 기본값 필드도 항상 포함되므로, 출력 스키마에서 필수로 표시해 프론트 타입을 정확히 맞춘다.
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, json_schema_serialization_defaults_required=True
    )
