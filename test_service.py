"""
Prueba end-to-end del servicio SIN tocar Cognito ni MySQL reales:
- Genera un par de llaves RSA propio y firma un JWT falso con esa llave,
  simulando exactamente la forma de un token de Cognito.
- Parchea cognito_auth._get_jwks() para que devuelva la llave publica
  propia en vez de llamar a AWS.
- Parchea db.get_enrollment() para devolver datos falsos (o None, para
  probar el 404) en vez de conectarse a MySQL.
"""
import os
import time
import json

os.environ["COGNITO_REGION"] = "us-east-1"
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_FAKEPOOL"
os.environ["COGNITO_APP_CLIENT_ID"] = "1tpv6des7mi6dd33pf2l62qulv"
os.environ["DB_HOST"] = "unused-in-this-test"
os.environ["DB_USER"] = "unused"
os.environ["DB_PASSWORD"] = "unused"
os.environ["DB_NAME"] = "unused"

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from jwt.algorithms import RSAAlgorithm

import cognito_auth
import db
import app as app_module

results = {"pass": [], "fail": []}


def check(name, cond):
    if cond:
        results["pass"].append(name)
        print("PASS:", name)
    else:
        results["fail"].append(name)
        print("FAIL:", name)


# ---- Generar llave RSA propia y JWKS falso ----
private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
KID = "test-kid-1"
jwk_public = json.loads(RSAAlgorithm.to_jwk(public_key))
jwk_public["kid"] = KID
jwk_public["use"] = "sig"
jwk_public["alg"] = "RS256"

# Parchea _get_jwks para no llamar a Cognito real
cognito_auth._jwks_cache["keys"] = {KID: jwk_public}
cognito_auth._jwks_cache["fetched_at"] = time.time()
cognito_auth._get_jwks = lambda: cognito_auth._jwks_cache["keys"]


def make_token(sub="sub-abc-123", token_use="access", client_id=None, expired=False):
    now = int(time.time())
    payload = {
        "sub": sub,
        "token_use": token_use,
        "iss": cognito_auth.ISSUER,
        "iat": now - 10,
        "exp": now - 10 if expired else now + 3600,
    }
    if token_use == "access":
        payload["client_id"] = client_id or os.environ["COGNITO_APP_CLIENT_ID"]
    else:
        payload["aud"] = client_id or os.environ["COGNITO_APP_CLIENT_ID"]
    return jwt.encode(payload, private_pem, algorithm="RS256", headers={"kid": KID})


client = app_module.app.test_client()

# ---- Test 1: falta curso_id ----
r = client.get("/diploma", headers={"Authorization": "Bearer whatever"})
check("sin curso_id -> 400", r.status_code == 400)

# ---- Test 2: token invalido (basura) ----
r = client.get("/diploma?curso_id=entryId123", headers={"Authorization": "Bearer esto-no-es-un-jwt"})
check("token invalido -> 401", r.status_code == 401)

# ---- Test 3: sin header Authorization ----
r = client.get("/diploma?curso_id=entryId123")
check("sin Authorization -> 401", r.status_code == 401)

# ---- Test 4: token expirado ----
token_exp = make_token(expired=True)
r = client.get("/diploma?curso_id=entryId123", headers={"Authorization": f"Bearer {token_exp}"})
check("token expirado -> 401", r.status_code == 401)
check("mensaje de expiracion es claro", "expiro" in r.get_json().get("error", "").lower())

# ---- Test 5: client_id que no matchea ----
token_bad_client = make_token(client_id="otro-client-id-que-no-es")
r = client.get("/diploma?curso_id=entryId123", headers={"Authorization": f"Bearer {token_bad_client}"})
check("client_id incorrecto -> 401", r.status_code == 401)

# ---- Test 6: token valido pero usuario NO inscrito en ese curso ----
# app.py hace "from db import get_enrollment", asi que hay que parchear
# el nombre importado en app_module, no el de db (si no, el parche no aplica).
token_ok = make_token(sub="sub-no-inscrito")
app_module.get_enrollment = lambda cognito_sub, curso_id: None
r = client.get("/diploma?curso_id=entryId123", headers={"Authorization": f"Bearer {token_ok}"})
check("token valido sin inscripcion -> 404", r.status_code == 404)

# ---- Test 7: token valido, usuario SI inscrito -> devuelve el PDF ----
import datetime
fake_row = {
    "nombre": "Nate",
    "apellido": "Mejia",
    "curso_id": "entryId123",
    "curso_nombre": "Python for Everybody",
    "fecha_inscripcion": datetime.datetime(2026, 9, 20, 10, 0, 0),
}
app_module.get_enrollment = lambda cognito_sub, curso_id: fake_row if curso_id == "entryId123" else None

token_valid = make_token(sub="sub-si-inscrito")
r = client.get("/diploma?curso_id=entryId123", headers={"Authorization": f"Bearer {token_valid}"})
check("token valido + inscrito -> 200", r.status_code == 200)
check("content-type es application/pdf", r.content_type == "application/pdf")
check("PDF empieza con la firma %PDF", r.data[:4] == b"%PDF")
check("trae Content-Disposition con el nombre del archivo", "diploma_entryId123.pdf" in r.headers.get("Content-Disposition", ""))
check("el PDF no esta vacio y tiene tamano razonable", len(r.data) > 1000)

with open("/tmp/diploma-service/diploma_from_service.pdf", "wb") as f:
    f.write(r.data)

# ---- Test 8: token con id_token (token_use='id') tambien deberia funcionar ----
token_id = make_token(sub="sub-si-inscrito", token_use="id")
r = client.get("/diploma?curso_id=entryId123", headers={"Authorization": f"Bearer {token_id}"})
check("id_token tambien es aceptado -> 200", r.status_code == 200)

# ---- Test 9: healthz ----
r = client.get("/healthz")
check("healthz -> 200", r.status_code == 200)

# ---- Test 10: headers CORS presentes ----
r = client.get("/healthz")
check("CORS header presente", "Access-Control-Allow-Origin" in r.headers)

print("\n=== SUMMARY ===")
print("PASS:", len(results["pass"]), " FAIL:", len(results["fail"]))
if results["fail"]:
    print("Failed:", results["fail"])
    raise SystemExit(1)
