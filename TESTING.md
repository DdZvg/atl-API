# Testing - Atlas Scraper API

Guía para probar la API FastAPI con ejemplos de curl y código.

## Requisitos previos

1. Tener la API ejecutándose:
```bash
python main.py
```

2. La API estará disponible en: `http://localhost:8000`

## 1. Health Check

Verificar que la API está funcionando:

```bash
curl -X GET "http://localhost:8000/health"
```

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": 1703000000.123
}
```

## 2. Búsqueda en Todas las Tiendas

Buscar un producto en todas las tiendas:

```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=all"
```

**Parámetros:**
- `q=arroz`: Término de búsqueda
- `store=all`: Buscar en todas las tiendas

## 3. Búsqueda en Tienda Específica

### Gollo
```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=gollo"
```

### Monge
```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=monge"
```

### Mexpress
```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=mexpress"
```

### CoopGuanacaste
```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=coopeguanacaste"
```

## 4. Búsquedas Complejas

### Producto con espacios
```bash
curl -X GET "http://localhost:8000/search?q=arroz%20integral&store=all"
```

### Producto con caracteres especiales
```bash
curl -X GET "http://localhost:8000/search?q=aceite%20de%20coco&store=all"
```

### Parámetro alternativo 'query'
```bash
curl -X GET "http://localhost:8000/search?query=arroz&store=all"
```

## 5. Cancelar Búsqueda

Mientras se ejecuta una búsqueda larga, cancelarla:

```bash
# En una terminal, iniciar búsqueda
curl -X GET "http://localhost:8000/search?q=arroz&store=all"

# En otra terminal, cancelar
curl -X POST "http://localhost:8000/cancel"
```

**Respuesta:**
```json
{
  "status": "cancelled",
  "message": "Búsqueda cancelada exitosamente",
  "timestamp": 1703000000.123
}
```

## 6. Reset de Token de Cancelación

Resetear el token de cancelación:

```bash
curl -X POST "http://localhost:8000/reset"
```

**Respuesta:**
```json
{
  "status": "reset",
  "message": "Token de cancelación reseteado",
  "timestamp": 1703000000.123
}
```

## 7. Búsquedas Activas (Debug)

Ver búsquedas activas:

```bash
curl -X GET "http://localhost:8000/active-searches"
```

**Respuesta:**
```json
{
  "active_searches": 2,
  "searches": ["arroz_all_1703000000.123", "pan_gollo_1703000000.456"],
  "timestamp": 1703000000.123
}
```

## Testing con Python

### Instalación de requests
```bash
pip install requests
```

### Script de prueba
```python
import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Health check
print("1. Health Check:")
response = requests.get(f"{BASE_URL}/health")
print(json.dumps(response.json(), indent=2))

# 2. Búsqueda en todas las tiendas
print("\n2. Búsqueda en todas las tiendas:")
response = requests.get(f"{BASE_URL}/search", params={"q": "arroz", "store": "all"})
data = response.json()
print(f"Total resultados: {data['total_results']}")
print(f"Errores: {len(data['errors'])}")
if data['results']:
    print(f"Primer producto: {data['results'][0]['name']}")

# 3. Búsqueda en tienda específica
print("\n3. Búsqueda en Gollo:")
response = requests.get(f"{BASE_URL}/search", params={"q": "arroz", "store": "gollo"})
data = response.json()
print(f"Total resultados: {data['total_results']}")

# 4. Cancelar búsqueda
print("\n4. Cancelar búsqueda:")
response = requests.post(f"{BASE_URL}/cancel")
print(json.dumps(response.json(), indent=2))

# 5. Reset
print("\n5. Reset token:")
response = requests.post(f"{BASE_URL}/reset")
print(json.dumps(response.json(), indent=2))
```

## Testing con JavaScript/TypeScript

### Con Fetch API
```javascript
const BASE_URL = "http://localhost:8000";

// 1. Health check
fetch(`${BASE_URL}/health`)
  .then(r => r.json())
  .then(data => console.log("Health:", data));

// 2. Búsqueda
fetch(`${BASE_URL}/search?q=arroz&store=all`)
  .then(r => r.json())
  .then(data => {
    console.log(`Total: ${data.total_results}`);
    console.log(`Errores: ${data.errors.length}`);
    console.log("Resultados:", data.results);
  });

// 3. Cancelar
fetch(`${BASE_URL}/cancel`, { method: "POST" })
  .then(r => r.json())
  .then(data => console.log("Cancelado:", data));
```

### Con Axios
```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000'
});

// 1. Health check
api.get('/health')
  .then(res => console.log("Health:", res.data));

// 2. Búsqueda
api.get('/search', {
  params: { q: 'arroz', store: 'all' }
})
  .then(res => {
    console.log(`Total: ${res.data.total_results}`);
    console.log("Resultados:", res.data.results);
  });

// 3. Cancelar
api.post('/cancel')
  .then(res => console.log("Cancelado:", res.data));
```

## Swagger UI

Acceder a la documentación interactiva:

```
http://localhost:8000/docs
```

Aquí puedes:
- Ver todos los endpoints
- Probar los endpoints directamente
- Ver esquemas de respuesta
- Descargar especificación OpenAPI

## ReDoc

Acceder a documentación alternativa:

```
http://localhost:8000/redoc
```

## Casos de Prueba Recomendados

### 1. Búsqueda exitosa
```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=all"
```
**Esperado:** Resultados de múltiples tiendas

### 2. Búsqueda sin resultados
```bash
curl -X GET "http://localhost:8000/search?q=xyzabc123&store=all"
```
**Esperado:** Error "No se encontraron productos"

### 3. Tienda inválida
```bash
curl -X GET "http://localhost:8000/search?q=arroz&store=invalid"
```
**Esperado:** Error 400 "Tienda no válida"

### 4. Sin parámetro de búsqueda
```bash
curl -X GET "http://localhost:8000/search"
```
**Esperado:** Error 400 "Se requiere parámetro 'q'"

### 5. Búsqueda larga (timeout)
```bash
curl -X GET "http://localhost:8000/search?q=a&store=all"
```
**Esperado:** Timeout después de 300 segundos

### 6. Cancelación durante búsqueda
```bash
# Terminal 1
curl -X GET "http://localhost:8000/search?q=arroz&store=all"

# Terminal 2 (mientras se ejecuta)
curl -X POST "http://localhost:8000/cancel"
```
**Esperado:** Búsqueda se cancela

## Monitoreo de Logs

Ver logs en tiempo real:

```bash
# En otra terminal mientras la API se ejecuta
tail -f /tmp/api.log
```

## Performance

### Tiempos típicos de respuesta

- **Health check**: < 10ms
- **Búsqueda en 1 tienda**: 30-60 segundos
- **Búsqueda en todas las tiendas**: 30-60 segundos (paralelo)
- **Cancelación**: < 100ms

### Recursos utilizados

- **CPU**: Bajo (scrapers usan Playwright)
- **Memoria**: ~500MB por búsqueda
- **Conexión**: Requiere acceso a internet

## Troubleshooting

### Error: "Connection refused"
- Verificar que la API esté ejecutándose
- Verificar puerto 8000

### Error: "Playwright browsers not installed"
```bash
playwright install chromium
```

### Error: "No products found"
- Intentar con otro término de búsqueda
- Verificar que las tiendas estén en línea
- Revisar logs de la API

### Respuesta lenta
- Normal: los scrapers tardan 30-60 segundos
- Verificar conexión a internet
- Intentar con una tienda específica

## Documentación OpenAPI

Descargar especificación OpenAPI:

```bash
curl -X GET "http://localhost:8000/openapi.json" > openapi.json
```

Usar con herramientas como:
- Postman
- Insomnia
- OpenAPI Generator
