from app.config import Settings
from app.main import create_app


def test_openapi_has_stable_operations_and_api_key_scheme() -> None:
    app = create_app(Settings(_env_file=None, llm_provider="mock", embedding_provider="hash"))
    schema = app.openapi()
    operations = {
        operation["operationId"]
        for path_item in schema["paths"].values()
        for method, operation in path_item.items()
        if method in {"get", "post", "delete"}
    }
    assert schema["openapi"] == "3.1.0"
    assert operations == {
        "getHealth",
        "getReadiness",
        "listCharacters",
        "chatWithCharacter",
        "resetCharacterSession",
    }
    assert "ApplicationApiKey" in schema["components"]["securitySchemes"]
