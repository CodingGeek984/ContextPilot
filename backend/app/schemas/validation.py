from typing import Type, TypeVar

from flask import jsonify, request
from pydantic import BaseModel, ValidationError

SchemaT = TypeVar('SchemaT', bound=BaseModel)


def parse_body(schema: Type[SchemaT], payload=None):
    """Validate a JSON payload against a schema.

    Returns a tuple ``(data, error_response)`` where ``error_response`` is a
    ready-to-return Flask response when validation fails, otherwise ``None``.
    """
    if payload is None:
        payload = request.get_json(silent=True)

    if payload is None:
        return None, (jsonify({
            'error': 'Request body must be valid JSON'
        }), 400)

    try:
        data = schema.model_validate(payload)
    except ValidationError as exc:
        return None, (jsonify({
            'error': f'Invalid request body: {schema.__name__}',
            'details': exc.errors(include_url=False, include_context=False)
        }), 400)

    return data, None


def dump(model: Type[SchemaT], payload):
    """Normalise a controller response through its response schema."""
    if payload is None:
        return None
    if isinstance(payload, list):
        return [model.model_validate(item).model_dump() for item in payload]
    return model.model_validate(payload).model_dump()