# diploma-service

Función "pesada" del proyecto: genera el diploma en PDF de un curso en el
que el usuario está inscrito. Corre como contenedor en OpenShift/Kubernetes.

No toca Cognito, Contentful ni las Lambdas de `/inscripcion` / `/mis-cursos`
— sólo lee de la misma tabla `inscripciones` en MySQL.

## Cómo funciona

`GET /diploma?curso_id=<entry id de Contentful>`
Header: `Authorization: Bearer <access_token o id_token de Cognito>`

1. El servicio valida el JWT él mismo contra las llaves públicas (JWKS) de
   tu User Pool de Cognito — no depende de un authorizer de API Gateway,
   porque esta ruta va a través de una integración HTTP_PROXY (no Lambda),
   así que la info del authorizer no llega automáticamente al contenedor.
2. Saca el `sub` del token y busca en `inscripciones` la fila con ese
   `cognito_sub` + `curso_id`.
3. Si no está inscrito → 404. Si el token es inválido/expiró → 401.
4. Si todo bien, genera el PDF (nombre completo, curso, fecha, firma/sello
   visual) y lo devuelve como `application/pdf`.

Todo esto ya está probado con un JWT falso firmado con una llave propia y
una capa de MySQL mockeada (`test_service.py`) — 15/15 checks en verde,
sin tocar tu Cognito ni tu base de datos reales.

## 1. Build de la imagen

Como ya tienes un clúster de OpenShift pero no necesariamente un registry
externo, lo más simple es un **build binario dentro del clúster**:

```bash
# dentro de la carpeta diploma-service/
oc new-build --binary --name=diploma-service --strategy=docker
oc start-build diploma-service --from-dir=. --follow
```

Esto sube tu código, lo construye con tu Dockerfile dentro del clúster, y
lo publica en el registry interno de OpenShift bajo un ImageStream llamado
`diploma-service`.

Si en cambio ya usas un registry externo (Docker Hub, Quay, ECR, etc.):

```bash
docker build -t <tu-registry>/diploma-service:latest .
docker push <tu-registry>/diploma-service:latest
```

## 2. Desplegar

Edita `openshift/01-secret.yaml` con tus valores reales (host de MySQL,
User Pool ID de Cognito, etc. — mismo User Pool / client id que ya usa el
front) y aplícalo junto con el resto:

```bash
oc apply -f openshift/01-secret.yaml

# Si usaste el build binario (oc new-build), la imagen ya vive en el
# ImageStream de tu proyecto — reemplaza IMAGE_PLACEHOLDER en
# 02-deployment.yaml por algo como:
#   image-registry.openshift-image-registry.svc:5000/<tu-proyecto>/diploma-service:latest
# Si usaste un registry externo, pon ahí la referencia completa a tu imagen.

oc apply -f openshift/02-deployment.yaml
oc apply -f openshift/03-service.yaml
oc apply -f openshift/04-route.yaml

oc get route diploma-service   # aquí sale la URL pública (https://...)
```

## 3. Conectar con tu API Gateway (para que quede bajo la misma URL)

Como tu API (`zqpoe9lth8...`) es un **HTTP API** (se ve por la pantalla del
JWT authorizer que usaste para `/inscripcion`), esto es más simple de lo
que parece — no hace falta VPC Link porque la Route de OpenShift ya es
pública:

1. En tu API Gateway → **Routes** → **Create** → `GET /diploma`.
2. **Attach integration** → tipo **HTTP** (no Lambda) → URL: la URL de la
   Route de OpenShift + `/diploma` (por ejemplo
   `https://diploma-service-tu-proyecto.apps.tu-cluster.com/diploma`).
   Método: `GET`.
3. **Authorization: NONE** en esta ruta — el propio contenedor valida el
   JWT, no hace falta duplicarlo en API Gateway.
4. La configuración de **CORS** que ya tienes en el API (la que arreglaste
   para `/inscripcion` y `/mis-cursos`) es a nivel de todo el API, así que
   `/diploma` la hereda automáticamente — no hay que tocar nada ahí,
   siempre que `GET` ya esté en Allow-Methods (ya lo está, por `/mis-cursos`).

Con eso, el front puede pegarle a
`https://zqpoe9lth8.execute-api.us-east-1.amazonaws.com/diploma?curso_id=...`
exactamente con el mismo patrón que ya usa para `/mis-cursos`, mandando el
`Authorization: Bearer <token>`.

## Archivos

- `app.py` — servicio Flask (`/diploma`, `/healthz`)
- `cognito_auth.py` — verificación del JWT contra el JWKS de Cognito
- `db.py` — consulta a `inscripciones` (mismas credenciales que las Lambdas)
- `diploma_render.py` — dibuja el PDF del diploma con reportlab
- `Dockerfile`, `requirements.txt`, `.dockerignore`
- `openshift/` — Secret, Deployment, Service y Route
- `test_service.py` — prueba end-to-end con JWT y DB mockeados
