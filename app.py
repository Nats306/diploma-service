"""
Servicio de generacion de diplomas (funcion "pesada" en OpenShift).

GET /diploma?curso_id=<entry id de Contentful>
  Header: Authorization: Bearer <access_token o id_token de Cognito>
  -> 200 application/pdf   (el diploma)
  -> 400 si falta curso_id
  -> 401 si el token falta/es invalido/expiro
  -> 404 si el usuario no esta inscrito en ese curso
  -> 500 error interno

GET /healthz -> probe de liveness/readiness para OpenShift
"""
import logging
import os

from flask import Flask, request, jsonify, Response

from cognito_auth import verify_token, TokenError
from db import get_enrollment
from diploma_render import generar_diploma_pdf, formatear_fecha_es

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diploma-service")

app = Flask(__name__)

# CORS de respaldo (lo ideal es configurarlo en el API Gateway, igual que
# las otras rutas, pero dejarlo tambien aqui no hace daño si alguna vez
# se llama directo a la Route de OpenShift).
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")


@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    resp.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    return resp


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"}), 200


@app.route("/diploma", methods=["OPTIONS"])
def diploma_preflight():
    return "", 204


@app.route("/diploma", methods=["GET"])
def diploma():
    curso_id = request.args.get("curso_id")
    if not curso_id:
        return jsonify({"error": "El parametro curso_id es obligatorio"}), 400

    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.lower().startswith("bearer ") else None

    try:
        claims = verify_token(token)
    except TokenError as e:
        return jsonify({"error": str(e)}), 401

    cognito_sub = claims["sub"]

    try:
        enrollment = get_enrollment(cognito_sub, curso_id)
    except Exception as e:
        logger.exception("Error consultando la base de datos")
        return jsonify({"error": "Error interno del servidor"}), 500

    if not enrollment:
        return jsonify({"error": "No estas inscrito en este curso"}), 404

    nombre_completo = f"{enrollment['nombre']} {enrollment['apellido']}".strip()
    fecha_txt = formatear_fecha_es(enrollment["fecha_inscripcion"])

    try:
        pdf_bytes = generar_diploma_pdf(
            nombre_completo=nombre_completo,
            curso_nombre=enrollment["curso_nombre"],
            fecha_inscripcion=fecha_txt,
            curso_id=curso_id,
        )
    except Exception:
        logger.exception("Error generando el PDF")
        return jsonify({"error": "Error interno del servidor"}), 500

    filename = f"diploma_{curso_id}.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
