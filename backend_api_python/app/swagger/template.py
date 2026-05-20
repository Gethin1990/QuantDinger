"""OpenAPI 3.0.3 base template for QuantDinger API."""

from app._version import APP_VERSION
from app.swagger.tags import SWAGGER_TAGS


def get_swagger_template():
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "QuantDinger API",
            "description": "Quantitative trading platform backend API",
            "version": APP_VERSION,
            "contact": {"name": "QuantDinger"},
        },
        "servers": [
            {"url": "/", "description": "Current server"},
        ],
        "tags": SWAGGER_TAGS,
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "JWT token from POST /api/auth/login or POST /api/auth/login-code",
                },
            },
            "schemas": {
                "ResponseEnvelope": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "integer",
                            "description": "1 = success, 0 = failure",
                            "example": 1,
                        },
                        "msg": {
                            "type": "string",
                            "description": "Human-readable message",
                            "example": "success",
                        },
                        "data": {
                            "description": "Response payload (type varies per endpoint)",
                        },
                    },
                    "required": ["code", "msg"],
                },
                "ErrorResponse": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "integer", "example": 0},
                        "msg": {"type": "string", "example": "Error description"},
                        "data": {"type": "object", "nullable": True},
                    },
                },
                "AgentResponseEnvelope": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "integer",
                            "description": "0 = success (agent convention)",
                            "example": 0,
                        },
                        "message": {"type": "string", "example": "ok"},
                        "data": {"description": "Response payload"},
                    },
                },
                "AgentErrorResponse": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "integer"},
                        "message": {"type": "string"},
                        "details": {"type": "object", "nullable": True},
                        "retriable": {"type": "boolean"},
                        "data": {"type": "object", "nullable": True},
                    },
                },
            },
            "responses": {
                "Unauthorized": {
                    "description": "Authentication required",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                            "example": {"code": 401, "msg": "Token missing", "data": None},
                        }
                    },
                },
                "Forbidden": {
                    "description": "Insufficient permissions",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                            "example": {"code": 403, "msg": "Admin access required", "data": None},
                        }
                    },
                },
                "ServerError": {
                    "description": "Internal server error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                            "example": {"code": 500, "msg": "Internal server error", "data": None},
                        }
                    },
                },
            },
        },
    }
