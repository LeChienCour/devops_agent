# Demo Script — FinOps Agent

**Evento:** AWS Community Day 2026  
**Duración total de la demo:** ~20 minutos  
**Contexto:** La demo se graba; puede repetirse 2-3 veces durante la sesión de 1 hora.

---

## Pre-Demo Checklist (15 min antes)

```
[ ] AWS credentials activos y no expiran en la próxima hora
    → aws sts get-caller-identity

[ ] Bedrock model access habilitado en us-east-1
    → aws bedrock list-foundation-models --region us-east-1 | grep claude-sonnet

[ ] infra/ desplegada (Lambda, DynamoDB, SNS, EventBridge)
    → aws lambda get-function --function-name finops-agent-agent-dev

[ ] Canal Slack #finops-demo configurado y webhook activo
    → curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"test"}'

[ ] Demo resources sembrados
    → make seed-demo   (solo una vez, dejar up durante toda la sesión)

[ ] Cold start quemado (run de calentamiento SIN cámara)
    → make invoke

[ ] Terminal lista: font grande, tema oscuro, sin notificaciones
[ ] Dos ventanas side-by-side: terminal izquierda / Slack derecha
```

---

## Flujo de la Demo (Minuto a Minuto)

### Bloque 1 — Contexto (0:00 – 2:00)

**Lo que dices:**
> "¿Cuánto dinero pierde tu cuenta AWS mientras duermes? Elastic IPs sin usar, volúmenes EBS huérfanos, Lambdas con 3 GB de memoria para un handler de 200 líneas. Este agente lo detecta solo, cada semana, y te manda un reporte a Slack."

**Lo que muestras:**
```bash
# Mostrar los recursos "leaky" que sembramos
aws ec2 describe-volumes \
  --filters "Name=status,Values=available" \
  --query "Volumes[*].{ID:VolumeId,Size:Size,Type:VolumeType,AZ:AvailabilityZone}" \
  --output table

aws ec2 describe-addresses \
  --query "Addresses[?AssociationId==null].{IP:PublicIp,AllocationId:AllocationId}" \
  --output table
```

> "Ahí están: dos volúmenes gp2 de 50 GB sin attachar, una EIP sin instancia. $24 al mes tirados."

---

### Bloque 2 — Arquitectura rápida (2:00 – 4:00)

**Lo que muestras:** Diagrama en README (o slide si aplica)

**Lo que dices:**
> "El agente corre en Lambda. LangGraph orquesta el loop: planea qué herramientas llamar, recolecta datos de tu cuenta, analiza con Claude, genera findings estructurados. Todo con guardrails: máximo 5 iteraciones, máximo $0.50 en Bedrock por run."

**Puntos clave a mencionar:**
- Tools son funciones Python en-proceso (no overhead de MCP en Lambda)
- Bedrock = Claude Sonnet, región us-east-1
- Output: DynamoDB + Slack Block Kit

---

### Bloque 3 — Trigger y ejecución en vivo (4:00 – 10:00)

```bash
# Mostrar primero lo que va a correr
cat scripts/run_local.py   # o mostrar handler.py brevemente
```

```bash
# Disparar el agente — método 1: Lambda directo
make invoke
```

**Mientras carga (~2-3 min):**
> "El agente genera primero un plan de investigación — decide qué herramientas llamar y en qué orden. Luego las ejecuta, analiza los resultados, y si necesita más datos itera. Los guardrails aseguran que no se vaya de las manos."

**Cuando responde:**
```json
{
  "investigation_id": "...",
  "findings_count": 4,
  "total_savings_usd": 27.15,
  "bedrock_cost_usd": 0.28,
  "status": "COMPLETED"
}
```

> "4 findings, $27 de ahorro mensual detectado, $0.28 en Bedrock. ROI inmediato."

---

### Bloque 4 — Ver los findings en Slack (10:00 – 13:00)

**Cambiar a ventana de Slack:**

> "El agente mandó el reporte a Slack automáticamente. Block Kit, ordenado por impacto, con el comando de remediación exacto."

**Puntos a señalar en el mensaje Slack:**
- Severidad con emoji (🔴 CRITICAL / 🟠 HIGH / 🟡 MEDIUM / 🟢 LOW)
- `estimated_monthly_usd` por finding
- Remediation command listo para copiar

---

### Bloque 5 — Reporte Markdown + DynamoDB (13:00 – 16:00)

```bash
# Generar reporte desde DynamoDB
python scripts/generate_report.py \
  --investigation-id <id-del-output-anterior>

# O con output a archivo
python scripts/generate_report.py \
  --investigation-id <id> \
  --output /tmp/report.md && cat /tmp/report.md
```

> "Los findings persisten en DynamoDB. Este script genera un Markdown desde el histórico — útil para tickets o documentación de remediación."

---

### Bloque 6 — Shift-left FinOps con Infracost (16:00 – 19:00)

**Mostrar ci.yml:**

```bash
cat .github/workflows/ci.yml | grep -A 20 "infracost"
```

> "Antes de que el agente detecte un leak en producción, Infracost lo avisa en el PR. Cada vez que alguien toca infra/, la pipeline calcula el delta de costo y lo comenta. Shift-left FinOps: mueve la conversación de costos al momento del code review."

---

### Bloque 7 — Cierre (19:00 – 20:00)

> "Una Lambda de ~$1/mes que corre cada lunes, detecta waste, y notifica al equipo. Open source, Terraform, desplegable en 30 minutos. El repo está en GitHub, link en las slides."

```bash
# Opcional: mostrar el cleanup (si es la última toma)
# make cleanup-demo
```

---

## Planes de Contingencia

### Fallo: Bedrock timeout o ThrottlingException

**Síntoma:** `make invoke` tarda >5 min o devuelve `FAILED`

```bash
# Verificar que el modelo está habilitado
aws bedrock list-foundation-models --region us-east-1 \
  --query "modelSummaries[?contains(modelId,'claude-sonnet')]"

# Cambiar a modelo alternativo si es necesario
# Editar infra/variables.tf → bedrock_model_id
```

**Backup:** Mostrar el output pregrabado en `/tmp/finops_response_backup.json` si existe.

---

### Fallo: Lambda cold start muy lento (>15s)

**Prevención:** Ya ejecutado el warm-up pre-demo.

**Si igual falla:** 
```bash
# Invocar directamente y mostrar logs mientras carga
make invoke &
make logs
```

---

### Fallo: AWS credentials expiradas

```bash
# Renovar credenciales (si usas aws-vault o similar)
aws-vault exec <profile> -- make invoke

# O exportar nuevas credenciales
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...
```

---

### Fallo: Slack webhook no entrega

**Síntoma:** `invoke` devuelve findings pero Slack no muestra nada.

```bash
# Probar webhook directamente
curl -X POST $SLACK_WEBHOOK_URL \
  -H 'Content-type: application/json' \
  -d '{"text":"test de conexión"}'

# Ver logs para confirmar que el notifier corrió
make logs | grep slack
```

**Backup:** Mostrar el reporte generado por `generate_report.py` en lugar de Slack.

---

### Fallo: Demo resources no visibles (seed no aplicó)

```bash
# Verificar estado de los recursos
terraform -chdir=infra/demo show

# Re-sembrar si es necesario (tarda ~2 min)
make seed-demo
```

---

### Fallo: Lambda function no existe (infra no desplegada)

```bash
# Re-desplegar solo el Lambda (rápido si la infra base existe)
make deploy
```

---

## Comandos de Referencia Rápida

```bash
make seed-demo          # Sembrar leaks demo
make invoke             # Disparar investigación on-demand
make logs               # Tail CloudWatch logs en vivo
make deploy             # Build + upload Lambda
make cleanup-demo       # Destruir recursos demo

# Generar reporte
python scripts/generate_report.py --investigation-id <id>

# Ver último investigation_id en DynamoDB
aws dynamodb query \
  --table-name finops-agent-findings-dev \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk":{"S":"<investigation-id>"}}' \
  --region us-east-1
```

---

## Variables de Entorno Necesarias

```bash
# En Lambda (via Terraform outputs o SSM)
DYNAMODB_TABLE_NAME=finops-agent-findings-dev
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:ACCOUNT:finops-agent-alerts-dev
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-5-20250929-v1:0
AWS_REGION_NAME=us-east-1
COST_THRESHOLD_USD=5.0

# En local (.env)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```
