"""
Acceso a la misma tabla `inscripciones` que ya usan las Lambdas de
/inscripcion y /mis-cursos. Reutiliza las mismas variables de entorno
(DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT) para no duplicar
configuracion.
"""
import os
import pymysql


def get_connection():
    return pymysql.connect(
        host=os.environ["DB_HOST"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        port=int(os.environ.get("DB_PORT", 3306)),
        connect_timeout=10,
    )


def get_enrollment(cognito_sub, curso_id):
    """Devuelve el dict de la inscripcion (nombre, apellido, curso_nombre,
    fecha_inscripcion) o None si el usuario no esta inscrito en ese curso."""
    connection = get_connection()
    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(
                """
                SELECT nombre, apellido, curso_id, curso_nombre, fecha_inscripcion
                FROM inscripciones
                WHERE cognito_sub = %s AND curso_id = %s
                """,
                (cognito_sub, curso_id),
            )
            return cursor.fetchone()
    finally:
        connection.close()
