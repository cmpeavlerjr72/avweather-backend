import secrets

def new_id(nbytes: int = 12) -> str:
    """URL-safe id for map files."""
    return secrets.token_urlsafe(nbytes)
