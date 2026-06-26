"""
FastAPI Microservice para Atlas Scraper
Ejecuta scrapers de tiendas costarricenses en paralelo y retorna resultados en JSON
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

# Importar los scrapers
from gollo_scraper import scrape_gollo
from monge_scraper import scrape_monge
from mexpress_scraper import scrape_mexpress
from coopeguanacaste_scraper import scrape_coopeguanacaste
from cancellation import cancel_token, CancellationToken
from scraper_errors import ErrorCode, get_error_message

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Crear aplicación FastAPI
app = FastAPI(
    title="Atlas Scraper API",
    description="API para búsqueda de productos en tiendas costarricenses",
    version="1.0.0"
)

# Configurar CORS para permitir solicitudes desde Node.js
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especificar los orígenes permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelos Pydantic para respuestas
class ProductResult(BaseModel):
    """Modelo para un producto encontrado"""
    name: str
    store: str
    regular_price: Optional[str] = None
    promo_price: Optional[str] = None
    price: Optional[str] = None
    availability: Optional[str] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    coincidence_type: Optional[str] = None
    error: Optional[Dict[str, Any]] = None

class SearchResponse(BaseModel):
    """Modelo para la respuesta de búsqueda"""
    query: str
    store: str
    results: List[Dict[str, Any]]
    total_results: int
    errors: List[Dict[str, Any]] = []
    timestamp: float

class HealthResponse(BaseModel):
    """Modelo para la respuesta de salud"""
    status: str
    version: str
    timestamp: float

# Diccionario para rastrear búsquedas activas
active_searches: Dict[str, CancellationToken] = {}
search_lock = threading.Lock()

def error_code_value(code: Any) -> int:
    """Return a JSON-friendly numeric error code."""
    if isinstance(code, ErrorCode):
        return code.value
    return int(code)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Endpoint de verificación de salud de la API
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=time.time()
    )

@app.get("/search", response_model=SearchResponse)
async def search(
    q: Optional[str] = Query(None, description="Término de búsqueda"),
    query: Optional[str] = Query(None, description="Término de búsqueda (alternativa)"),
    store: str = Query("all", description="Tienda: all, gollo, monge, mexpress, coopeguanacaste")
):
    """
    Endpoint principal de búsqueda.
    Ejecuta los scrapers en paralelo y retorna resultados consolidados.
    
    Parámetros:
    - q o query: término de búsqueda (requerido)
    - store: tienda específica o 'all' para todas (default: all)
    
    Retorna:
    - JSON con resultados de búsqueda, errores y metadatos
    """
    
    # Obtener el término de búsqueda
    search_query = q or query
    if not search_query:
        raise HTTPException(
            status_code=400,
            detail="Se requiere parámetro 'q' o 'query' con el término de búsqueda"
        )
    
    search_query = search_query.strip()
    store = store.lower()
    
    # Validar tienda
    valid_stores = ["all", "gollo", "monge", "mexpress", "coopeguanacaste"]
    if store not in valid_stores:
        raise HTTPException(
            status_code=400,
            detail=f"Tienda no válida. Opciones: {', '.join(valid_stores)}"
        )
    
    logger.info(f"[BÚSQUEDA] Iniciando búsqueda: query='{search_query}', store='{store}'")
    
    # Crear un nuevo token de cancelación para esta búsqueda
    search_id = f"{search_query}_{store}_{time.time()}"
    new_cancel_token = CancellationToken()
    
    with search_lock:
        active_searches[search_id] = new_cancel_token
    
    try:
        # Resetear el token de cancelación global
        cancel_token.reset()
        
        start_time = time.time()
        
        if store == "all":
            # Ejecutar todos los scrapers en paralelo
            results = await search_all_stores(search_query)
        else:
            # Ejecutar scraper específico
            results = await search_single_store(search_query, store)
        
        elapsed_time = time.time() - start_time
        
        # Separar resultados válidos de errores
        valid_results = [r for r in results if "error" not in r or r["error"] is None]
        errors = [r for r in results if "error" in r and r["error"] is not None]
        
        logger.info(
            f"[BÚSQUEDA] Completada en {elapsed_time:.2f}s: "
            f"{len(valid_results)} productos, {len(errors)} errores"
        )
        
        return SearchResponse(
            query=search_query,
            store=store,
            results=valid_results,
            total_results=len(valid_results),
            errors=errors,
            timestamp=time.time()
        )
    
    except Exception as e:
        logger.error(f"[BÚSQUEDA] Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error en la búsqueda: {str(e)}"
        )
    
    finally:
        # Limpiar token de cancelación
        with search_lock:
            if search_id in active_searches:
                del active_searches[search_id]

async def search_all_stores(search_query: str) -> List[Dict[str, Any]]:
    """
    Ejecuta búsquedas en todas las tiendas en paralelo.
    """
    all_results = []
    errors = []
    
    scrapers = {
        "gollo": scrape_gollo,
        "monge": scrape_monge,
        "mexpress": scrape_mexpress,
        "coopeguanacaste": scrape_coopeguanacaste,
    }
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        # Enviar todas las tareas
        futures = {
            store: executor.submit(scraper, search_query)
            for store, scraper in scrapers.items()
        }
        
        # Procesar resultados conforme se completan
        for store, future in futures.items():
            try:
                results = future.result(timeout=300)
                
                # Separar productos válidos de errores
                store_errors = [p for p in results if "error" in p and p["error"] is not None]
                store_products = [p for p in results if "error" not in p or p["error"] is None]
                
                all_results.extend(store_products)
                errors.extend(store_errors)
                
                logger.info(f"[{store.upper()}] {len(store_products)} productos, {len(store_errors)} errores")
                
            except Exception as e:
                logger.error(f"[{store.upper()}] Error: {str(e)}")
                error_code = getattr(ErrorCode, f"{store.upper()}_SITE_ERROR", 999)
                errors.append({
                    "error": {
                        "code": error_code_value(error_code),
                        "message": f"Error al acceder a {store}: {str(e)}"
                    }
                })
    
    # Si no hay resultados pero hay errores, retornar solo errores
    if not all_results and errors:
        return errors
    
    # Si no hay resultados ni errores, retornar error genérico
    if not all_results:
        return [{
            "error": {
                "code": ErrorCode.PRODUCT_NOT_FOUND.value,
                "message": get_error_message(ErrorCode.PRODUCT_NOT_FOUND)
            }
        }]
    
    # Ordenar por precio (si está disponible)
    def get_price_value(product):
        try:
            if "error" in product and product["error"]:
                return float('inf')
            
            price_str = product.get("regular_price") or product.get("price") or "999999"
            price_str = price_str.replace("₡", "").replace(".", "").replace(",", ".").strip()
            return float(price_str)
        except:
            return float('inf')
    
    all_results.sort(key=get_price_value)
    
    # Agregar errores al final
    if errors:
        all_results.extend(errors)
    
    return all_results

async def search_single_store(search_query: str, store: str) -> List[Dict[str, Any]]:
    """
    Ejecuta búsqueda en una tienda específica.
    """
    scrapers = {
        "gollo": scrape_gollo,
        "monge": scrape_monge,
        "mexpress": scrape_mexpress,
        "coopeguanacaste": scrape_coopeguanacaste,
    }
    
    if store not in scrapers:
        raise HTTPException(
            status_code=400,
            detail=f"Tienda no válida: {store}"
        )
    
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(scrapers[store], search_query)
            results = future.result(timeout=300)
            
            logger.info(f"[{store.upper()}] Búsqueda completada: {len(results)} resultados")
            return results
            
    except Exception as e:
        logger.error(f"[{store.upper()}] Error: {str(e)}")
        return [{
            "error": {
                "code": 999,
                "message": f"Error en {store}: {str(e)}"
            }
        }]

@app.post("/cancel")
async def cancel_search():
    """
    Endpoint para cancelar una búsqueda en curso.
    """
    logger.info("[CANCELACIÓN] Cancelando búsqueda...")
    cancel_token.cancel()
    
    return {
        "status": "cancelled",
        "message": "Búsqueda cancelada exitosamente",
        "timestamp": time.time()
    }

@app.post("/reset")
async def reset_cancellation():
    """
    Endpoint para resetear el token de cancelación.
    """
    logger.info("[RESET] Reseteando token de cancelación...")
    cancel_token.reset()
    
    return {
        "status": "reset",
        "message": "Token de cancelación reseteado",
        "timestamp": time.time()
    }

@app.get("/active-searches")
async def get_active_searches():
    """
    Endpoint para obtener búsquedas activas (solo para debugging).
    """
    with search_lock:
        return {
            "active_searches": len(active_searches),
            "searches": list(active_searches.keys()),
            "timestamp": time.time()
        }

if __name__ == "__main__":
    import uvicorn
    
    # Ejecutar servidor en puerto 8000
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
