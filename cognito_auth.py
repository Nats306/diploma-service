"""
Verifica el JWT de Cognito (access token o id token) contra las llaves
publicas (JWKS) del User Pool. No depende de un authorizer de API
Gateway -- el propio servicio valida el token, porque esta ruta va a
estar detras de una integracion HTTP_PROXY (no Lambda), asi que la
info del authorizer de API Gateway no llega automaticamente al
contenedor como si fuera un evento de Lambda.
"""
import os
import time
import json
import urllib.request

import jwt
from jwt.algorithms import RSAAlgorithm

COGNITO_REGION = os.environ.get("COGNITO_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
COGNITO_APP_CLIENT_ID = os.environ["COGNITO_APP_CLIENT_ID"]

ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

_jwks_cache = {"keys": None, "fetched_at": 0}
_JWKS_TTL_SECONDS = 3600


class TokenError(Exception):
    pass


def _get_jwks():
    now = time.time()
    if _jwks_cache["keys"] is not None and (now - _jwks_cache["fetched_at"]) < _JWKS_TTL_SECONDS:
        return _jwks_cache["keys"]

    with urllib.request.urlopen(JWKS_URL, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    keys_by_kid = {k["kid"]: k for k in data["keys"]}
    _jwks_cache["keys"] = keys_by_kid
    _jwks_cache["fetched_at"] = now
    return keys_by_kid


def verify_token(token):
    """Devuelve el dict de claims si el token es valido. Lanza TokenError si no."""
    if not token:
        raise TokenError("Falta el token")

    try:
        header = jwt.get_unverified_header(token)
    except Exception as e:
        raise TokenError(f"Token malformado: {e}")

    kid = header.get("kid")
    if not kid:
        raise TokenError("Token sin 'kid'")

    try:
        keys_by_kid = _get_jwks()
        jwk = keys_by_kid.get(kid)
        if jwk is None:
            # el kid puede no estar en cache si Cognito roto las llaves; refresca una vez
            _jwks_cache["keys"] = None
            keys_by_kid = _get_jwks()
            jwk = keys_by_kid.get(kid)
        if jwk is None:
            raise TokenError("No se encontro la llave publica (kid) para este token")
        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    except TokenError:
        raise
    except Exception as e:
        raise TokenError(f"No se pudieron obtener las llaves publicas de Cognito: {e}")

    try:
        claims = jwt.decode(
            token,
            key=public_key,
            algorithms=["RS256"],
            issuer=ISSUER,
            options={"verify_aud": False},  # el aud/client_id se valida a mano abajo
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("El token expiro, inicia sesion de nuevo")
    except Exception as e:
        raise TokenError(f"Token invalido: {e}")

    token_use = claims.get("token_use")
    if token_use == "access":
        client_ok = claims.get("client_id") == COGNITO_APP_CLIENT_ID
    elif token_use == "id":
        client_ok = COGNITO_APP_CLIENT_ID in (claims.get("aud"), *([] if not isinstance(claims.get("aud"), list) else claims.get("aud")))
    else:
        raise TokenError(f"token_use inesperado: {token_use}")

    if not client_ok:
        raise TokenError("El token no fue emitido para esta aplicacion (client id no coincide)")

    if "sub" not in claims:
        raise TokenError("El token no trae 'sub'")

    return claims
