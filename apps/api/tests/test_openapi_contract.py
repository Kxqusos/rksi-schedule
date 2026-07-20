from app.main import app


def test_openapi_declares_http_bearer_security_scheme():
    schema = app.openapi()
    schemes = schema.get("components", {}).get("securitySchemes", {})
    assert any(
        scheme.get("type") == "http" and scheme.get("scheme") == "bearer"
        for scheme in schemes.values()
    ), f"expected an http bearer security scheme, got {schemes!r}"


def test_protected_routes_reference_the_security_scheme():
    schema = app.openapi()
    # A representative editor-guarded route and an admin-guarded route both
    # must advertise their auth requirement in the contract.
    assert schema["paths"]["/schedule/lessons"]["post"].get("security"), (
        "POST /schedule/lessons must declare a security requirement"
    )
    assert schema["paths"]["/imports/schedule"]["post"].get("security"), (
        "POST /imports/schedule must declare a security requirement"
    )
    assert schema["paths"]["/users"]["post"].get("security"), (
        "POST /users must declare a security requirement"
    )


def test_public_routes_do_not_require_security():
    schema = app.openapi()
    # Public read endpoints stay open — no security requirement.
    assert not schema["paths"]["/schedule/public/latest-week"]["get"].get("security")
