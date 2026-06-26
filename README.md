# Atlas Scraper API - FastAPI Microservice

API FastAPI para búsqueda de productos en tiendas costarricenses (Gollo, Monge, Mexpress, CoopGuanacaste) con ejecución paralela de scrapers.

## Características

- ✅ Ejecuta scrapers en paralelo usando `ThreadPoolExecutor`
- ✅ Endpoint GET `/search?q={query}&store={all|gollo|monge|mexpress|coopeguanacaste}`
- ✅ Endpoint POST `/cancel` para cancelar búsquedas en curso
- ✅ Manejo robusto de errores por tienda (no bloquea otras tiendas)
- ✅ Respuestas JSON estructuradas con Pydantic
- ✅ CORS habilitado para integración con frontend
- ✅ Logging detallado de operaciones
- ✅ Health check en `/health`

## Instalación

### Requisitos previos
- Python 3.9+
- pip o pip3

### Pasos de instalación

1. **Instalar dependencias:**
```bash
pip install -r requirements.txt
```

2. **Instalar navegadores de Playwright:**
```bash
playwright install chromium
```

## Uso

### Iniciar la API

```bash
python main.py
```

La API estará disponible en `http://localhost:8000`

### Documentación interactiva

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Endpoints

### 1. Health Check
```
GET /health
```

**Respuesta:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": 1703000000.123
}
```

### 2. Búsqueda de Productos

```
GET /search?q={query}&store={store}
```

**Parámetros:**
- `q` (string, requerido): Término de búsqueda
- `store` (string, opcional): `all`, `gollo`, `monge`, `mexpress`, `coopeguanacaste` (default: `all`)

**Ejemplo:**
```bash
curl "http://localhost:8000/search?q=arroz&store=all"
```

**Respuesta exitosa:**
```json
{
  "query": "arroz",
  "store": "all",
  "results": [
    {
      "name": "Arroz Integral 5kg",
      "store": "Gollo",
      "regular_price": "₡3,500",
      "promo_price": "₡2,999",
      "availability": "disponible",
      "url": "https://www.gollo.com/...",
      "image_url": "https://...",
      "sku": "123456",
      "category": "Granos",
      "description": "Arroz integral de alta calidad",
      "coincidence_type": "exacta",
      "error": null
    }
  ],
  "total_results": 24,
  "errors": [],
  "timestamp": 1703000000.123
}
```

**Respuesta con errores:**
```json
{
  "query": "arroz",
  "store": "all",
  "results": [
    {
      "name": "Arroz Integral 5kg",
      "store": "Gollo",
      "regular_price": "₡3,500",
      "promo_price": "₡2,999",
      "availability": "disponible",
      "url": "https://www.gollo.com/...",
      "image_url": "https://...",
      "sku": "123456",
      "category": "Granos",
      "description": null,
      "coincidence_type": "exacta",
      "error": null
    }
  ],
  "total_results": 12,
  "errors": [
    {
      "error": {
        "code": 101,
        "message": "Error al acceder al sitio de Monge"
      }
    }
  ],
  "timestamp": 1703000000.123
}
```

### 3. Cancelar Búsqueda

```
POST /cancel
```

**Respuesta:**
```json
{
  "status": "cancelled",
  "message": "Búsqueda cancelada exitosamente",
  "timestamp": 1703000000.123
}
```

### 4. Resetear Token de Cancelación

```
POST /reset
```

**Respuesta:**
```json
{
  "status": "reset",
  "message": "Token de cancelación reseteado",
  "timestamp": 1703000000.123
}
```

### 5. Búsquedas Activas (Debug)

```
GET /active-searches
```

**Respuesta:**
```json
{
  "active_searches": 2,
  "searches": ["arroz_all_1703000000.123", "pan_gollo_1703000000.456"],
  "timestamp": 1703000000.123
}
```

## Estructura de Respuesta

### Producto Exitoso
```json
{
  "name": "Nombre del producto",
  "store": "Nombre de la tienda",
  "regular_price": "₡1,000",
  "promo_price": "₡800",
  "price": "₡800",
  "availability": "disponible",
  "url": "https://...",
  "image_url": "https://...",
  "sku": "123456",
  "category": "Categoría",
  "description": "Descripción del producto",
  "coincidence_type": "exacta",
  "error": null
}
```

### Producto con Error
```json
{
  "error": {
    "code": 101,
    "message": "Error al acceder al sitio de Monge"
  }
}
```

## Códigos de Error

| Código | Mensaje |
|--------|---------|
| 1 | No se encontraron productos que coincidan con la búsqueda |
| 2 | Error de conexión. Por favor, verifique su conexión a internet |
| 3 | La búsqueda ha excedido el tiempo de espera |
| 4 | Error al procesar los datos de la página |
| 5 | Búsqueda cancelada por el usuario |
| 100 | Error al acceder al sitio de Gollo |
| 101 | Error al acceder al sitio de Monge |
| 102 | Error al acceder al sitio de Mexpress |
| 200 | Error al iniciar el navegador |
| 201 | Error al cargar la página |
| 202 | Error al encontrar elementos en la página |
| 300 | Error al extraer información de precios |
| 301 | Error al extraer nombres de productos |
| 302 | Error al extraer URLs de productos |
| 303 | Error al extraer imágenes de productos |

## Características de los Scrapers

### Gollo Scraper
- Extrae productos de https://www.gollo.com
- Soporta precios regulares y promocionales
- Clasificación de coincidencias: exacta, parcial, secundaria

### Monge Scraper
- Extrae productos de https://www.monge.cr
- Manejo de disponibilidad
- Extracción de imágenes con lazy loading

### Mexpress Scraper
- Extrae productos de https://www.mexpress.cr
- Información de SKU y categorías
- Soporte para múltiples formatos de precio

### CoopGuanacaste Scraper
- Extrae productos de https://www.coopeguanacaste.com
- Información detallada de disponibilidad
- Extracción de descripciones de productos

## Manejo de Errores

La API está diseñada para ser **resiliente**:

1. Si una tienda falla, los resultados de otras tiendas se retornan normalmente
2. Los errores se incluyen en el array `errors` de la respuesta
3. No hay bloqueos: si 1 de 4 tiendas falla, obtendrás resultados de 3

**Ejemplo:**
```json
{
  "query": "arroz",
  "store": "all",
  "results": [12 productos de 3 tiendas exitosas],
  "total_results": 12,
  "errors": [
    {
      "error": {
        "code": 101,
        "message": "Error al acceder al sitio de Monge"
      }
    }
  ]
}
```

## Cancelación de Búsquedas

1. Realizar una búsqueda (toma tiempo)
2. Mientras se ejecuta, llamar a `POST /cancel`
3. La búsqueda se detiene y retorna los resultados parciales

**Flujo:**
```
Cliente → GET /search?q=arroz (inicia búsqueda en paralelo)
Cliente → POST /cancel (cancela la búsqueda)
API → Detiene threads de scrapers
API → Retorna error con código 5 (SEARCH_CANCELLED)
```

## Configuración

### Variables de entorno (opcional)

Crear archivo `.env`:
```
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
FASTAPI_WORKERS=4
LOG_LEVEL=INFO
```

## Desarrollo

### Ejecutar con auto-reload
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Ejecutar con múltiples workers
```bash
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

## Integración con Frontend

### Ejemplo con Fetch API (JavaScript/TypeScript)
```javascript
// Búsqueda
const response = await fetch('http://localhost:8000/search?q=arroz&store=all');
const data = await response.json();
console.log(data.results);

// Cancelar
await fetch('http://localhost:8000/cancel', { method: 'POST' });
```

### Ejemplo con Axios
```javascript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000'
});

// Búsqueda
const { data } = await api.get('/search', {
  params: { q: 'arroz', store: 'all' }
});

// Cancelar
await api.post('/cancel');
```

## Performance

- **Timeout por tienda**: 300 segundos
- **Max workers**: 4 (ejecución paralela)
- **Respuesta típica**: 30-60 segundos (todas las tiendas)
- **Resultados típicos**: 10-50 productos por tienda

## Troubleshooting

### Error: "Playwright browsers not installed"
```bash
playwright install chromium
```

### Error: "Connection refused"
Asegurar que la API esté ejecutándose:
```bash
python main.py
```

### Error: "No products found"
- Verificar que el término de búsqueda sea válido
- Intentar con otra tienda específica
- Revisar logs de la API

## Licencia

MIT
