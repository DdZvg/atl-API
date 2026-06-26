from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import re
from cancellation import cancel_token, is_search_cancelled
# Asumo que el archivo scraper_errors.py existe y contiene las clases y funciones necesarias.
# from .scraper_errors import ScraperError, ErrorCode, get_error_message 

# Definiciones de errores simuladas para que el código sea ejecutable y demostrativo
class ErrorCode:
    BROWSER_LAUNCH_ERROR = 100
    TIMEOUT_ERROR = 101
    PRODUCT_NOT_FOUND = 102
    NAME_EXTRACTION_ERROR = 103
    PRICE_EXTRACTION_ERROR = 104
    URL_EXTRACTION_ERROR = 105
    IMAGE_EXTRACTION_ERROR = 106
    PARSING_ERROR = 107
    SEARCH_CANCELLED = 108

class ScraperError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(self.message)

def get_error_message(code):
    messages = {
        ErrorCode.BROWSER_LAUNCH_ERROR: "Error al iniciar el navegador.",
        ErrorCode.TIMEOUT_ERROR: "Tiempo de espera agotado al cargar la página.",
        ErrorCode.PRODUCT_NOT_FOUND: "No se encontraron productos para la búsqueda.",
        ErrorCode.NAME_EXTRACTION_ERROR: "Error al extraer el nombre del producto.",
        ErrorCode.PRICE_EXTRACTION_ERROR: "Error al extraer el precio del producto.",
        ErrorCode.URL_EXTRACTION_ERROR: "Error al extraer la URL del producto.",
        ErrorCode.IMAGE_EXTRACTION_ERROR: "Error al extraer la URL de la imagen.",
        ErrorCode.URL_EXTRACTION_ERROR: "Error al extraer la URL del producto.",
        ErrorCode.IMAGE_EXTRACTION_ERROR: "Error al extraer la URL de la imagen.",
        ErrorCode.PARSING_ERROR: "Error inesperado durante el procesamiento de la página.",
        ErrorCode.SEARCH_CANCELLED: "Búsqueda cancelada por el usuario."
    }
    return messages.get(code, "Error desconocido.")

def clasificar_coincidencia(search_query: str, product_name: str) -> str:
    """
    Clasifica la coincidencia de forma más estricta, incluyendo una verificación de similitud
    de caracteres cercanos (fuzzy matching) para modelos como 'Magic7' vs 'Magic 7'.
    """
    # Normalización: minúsculas y eliminación de espacios y caracteres especiales para fuzzy matching
    normalized_query = re.sub(r'[^a-z0-9]', '', search_query.lower())
    normalized_product = re.sub(r'[^a-z0-9]', '', product_name.lower())
    
    # 1. Coincidencia de Subcadena (Fuzzy Matching para modelos)
    # Si la consulta normalizada está contenida en el producto normalizado, es exacta.
    if normalized_query in normalized_product:
        return 'exacta'
        
    # 2. Coincidencia de Palabras Clave (Lógica estricta anterior)
    query_words = set(search_query.lower().split())
    product_words = set(product_name.lower().split())
    
    # Coincidencia Exacta de Palabras
    if query_words.issubset(product_words):
        return 'exacta'
    
    # Coincidencia Parcial de Palabras
    if query_words.intersection(product_words):
        return 'parcial'
        
    # 3. Coincidencia Secundaria (Descarte)
    return 'secundaria'

def create_search_url(query):
    """Formatea la consulta de búsqueda para gollo.com."""
    # Uso de urllib.parse.quote_plus sería más robusto, pero sigo el patrón simple de reemplazo de espacios.
    formatted_query = query.replace(' ', '+')
    return f"https://www.gollo.com/catalogsearch/result/?q={formatted_query}"

def safe_wait(page, timeout_ms, interval_ms=100):
    """
    Espera con chequeo periódico de cancelación.
    Lanza excepción si se cancela durante la espera.
    """
    elapsed = 0
    while elapsed < timeout_ms:
        if is_search_cancelled():
            raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))
        
        wait_time = min(interval_ms, timeout_ms - elapsed)
        if wait_time > 0:
            page.wait_for_timeout(int(wait_time))
        elapsed += wait_time

def safe_goto(page, url, wait_until='domcontentloaded'):
    """
    Navega a una URL con verificación de cancelación.
    """
    if is_search_cancelled():
        raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))
    
    try:
        page.goto(url, wait_until=wait_until, timeout=10000)
    except PlaywrightTimeout:
        # Si se cancela durante el goto, lanzar error
        if is_search_cancelled():
            raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))
        raise

def parse_product_item(item):
    """Función auxiliar para extraer datos de un solo elemento de producto de BeautifulSoup."""
    
    # 1. Extraer URL y Nombre (se usa el mismo elemento)
    url_element = item.find('a', class_='product-item-link')
    if not url_element or 'href' not in url_element.attrs:
        raise ScraperError(ErrorCode.URL_EXTRACTION_ERROR, get_error_message(ErrorCode.URL_EXTRACTION_ERROR))
    url = url_element['href']
    name = url_element.text.strip()
    
    if not name:
        raise ScraperError(ErrorCode.NAME_EXTRACTION_ERROR, get_error_message(ErrorCode.NAME_EXTRACTION_ERROR))

    # 2. Extraer URL de la imagen
    img_element = item.find('img', class_='product-image-photo')
    # Se utiliza 'data-src' como fallback, que es común en sitios con lazy loading
    img_url = img_element.get('src') or img_element.get('data-src') if img_element else None
    if not img_url:
        raise ScraperError(ErrorCode.IMAGE_EXTRACTION_ERROR, get_error_message(ErrorCode.IMAGE_EXTRACTION_ERROR))

    # 3. Extraer Precios
    regular_price = "Precio no encontrado"
    promo_price = "N/A"
    
    # Intenta encontrar el precio especial (promocional) y el precio antiguo (regular)
    special_price_container = item.find('span', class_='special-price')
    old_price_container = item.find('span', class_='old-price')
    
    if special_price_container and old_price_container:
        # Caso 1: Hay precio promocional y precio regular tachado
        promo_price_element = special_price_container.find('span', class_='price')
        regular_price_element = old_price_container.find('span', class_='price')
        
        if promo_price_element:
            promo_price = promo_price_element.text.strip()
        if regular_price_element:
            regular_price = regular_price_element.text.strip()
    else:
        # Caso 2: Solo hay un precio (el regular)
        price_element = item.find('span', class_='price')
        if price_element:
            regular_price = price_element.text.strip()
        else:
            raise ScraperError(ErrorCode.PRICE_EXTRACTION_ERROR, get_error_message(ErrorCode.PRICE_EXTRACTION_ERROR))

    # 4. Extraer SKU (código de tienda)
    sku = None
    sku_element = item.select_one('[data-sku], .sku, .product-sku')
    if sku_element:
        sku = sku_element.text.strip()
    
    # 5. Extraer Disponibilidad
    availability = "disponible"
    # Buscar indicadores de no disponibilidad
    if item.select_one('.out-of-stock, .no-stock, .unavailable'):
        availability = "no disponible"
    elif 'out-of-stock' in str(item.get('class', [])).lower():
        availability = "no disponible"
    
    # 6. Evitar guardar data URIs en imagen
    if img_url and img_url.startswith('data:'):
        img_url = 'https://via.placeholder.com/300?text=No+Image'
    
    return {
        'name': name,
        'regular_price': regular_price,
        'promo_price': promo_price,
        'url': url,
        'image_url': img_url,
        'store': 'Gollo',
        'sku': sku,
        'availability': availability,
        'error': None,
        'coincidence_type': None
    }

def scrape_gollo(search_query):
    """
    Realiza el scraping de productos en gollo.com para una consulta de búsqueda dada.
    Utiliza Playwright para la carga inicial y BeautifulSoup para el parsing eficiente.
    """
    search_url = create_search_url(search_query)
    products = []
    
    if cancel_token.is_cancelled():
        return [{'error': {'code': ErrorCode.SEARCH_CANCELLED, 'message': get_error_message(ErrorCode.SEARCH_CANCELLED)}}]
    
    # Se recomienda usar un contexto de Playwright a nivel superior si se hacen múltiples llamadas,
    # pero para una sola llamada, este enfoque es correcto.
    try:
        with sync_playwright() as p:
            # 1. Lanzar el navegador
            try:
                # Optimización: Usar 'chromium' y añadir un User-Agent para evitar la detección de bots
                browser = p.chromium.launch(headless=True)
                # Crear un contexto con un User-Agent realista
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    extra_http_headers={'Accept-Language': 'es-ES,es;q=0.9'}
                )
                
                if cancel_token.is_cancelled():
                    browser.close()
                    raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))
            except ScraperError:
                raise
            except Exception:
                raise ScraperError(ErrorCode.BROWSER_LAUNCH_ERROR, get_error_message(ErrorCode.BROWSER_LAUNCH_ERROR))
            
            page = None
            try:
                # 2. Navegar y esperar la carga
                page = context.new_page() # Usar el contexto con el User-Agent
                # Optimización: Usar wait_until="domcontentloaded" y luego esperar por el selector clave
                page.goto(search_url, wait_until="load")
                
                # Esperar por el selector de productos, con un timeout más corto si es posible,
                # pero manteniendo 20s como máximo de seguridad.
                try:
                    # Esperar por el contenedor principal de productos
                    # Optimización: Usar page.locator().wait_for() que es más eficiente que wait_for_selector
                    # Usar un selector más específico para el contenedor principal para asegurar que la página cargó
                    # Esperar por el contenedor principal de productos o por el mensaje de no resultados
                    page.wait_for_selector('ol.product-items, ul.product-items, div.message.info.empty', timeout=25000)
                    # Desplazarse al final para asegurar la carga de todos los elementos (lazy loading)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    # Esperar a que la red esté inactiva después del scroll para asegurar la carga de imágenes/datos
                    page.wait_for_load_state('networkidle', timeout=25000)
                except PlaywrightTimeout:
                    # Si el contenedor no aparece, es probable que no haya productos o la página sea lenta.
                    # No es necesariamente un error de timeout, puede ser un "no encontrado".
                    # Continuamos para revisar el contenido.
                    pass 
                
                if cancel_token.is_cancelled():
                    raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED)) 
                
                # 3. Obtener el contenido y parsear con BeautifulSoup
                content = page.content()
                # Optimización: Usar 'lxml' si está disponible, es mucho más rápido que 'html.parser'
                soup = BeautifulSoup(content, 'lxml') # Usamos 'lxml' para máxima eficiencia.
                
                # 4. Encontrar todos los elementos de producto
                # El selector 'li.product-item' parece ser correcto, pero a veces la página no carga el contenido completo.
                # Vamos a intentar encontrar el contenedor principal y luego los items dentro.
                product_list = soup.find('ol', class_='product-items') or soup.find('ul', class_='product-items')
                if product_list:
                    product_items = product_list.find_all('li', class_='product-item')
                else:
                    product_items = []
                
                if not product_items:
                    # Si no hay items, buscamos un mensaje de "no resultados" para un diagnóstico más preciso
                    no_results = soup.find('div', class_='message info empty')
                    if no_results:
                        raise ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
                    else:
                        # Si no hay items ni mensaje de no resultados, asumimos un error de estructura
                        raise ScraperError(ErrorCode.PARSING_ERROR, "Estructura de página inesperada o productos no cargados.")

                # 5. Procesar cada producto
                for item in product_items:
                    try:
                        product_data = parse_product_item(item)
                        
                        # NUEVO: Clasificar la coincidencia
                        tipo_coincidencia = clasificar_coincidencia(search_query, product_data["name"])
                        product_data["coincidence_type"] = tipo_coincidencia
                        
                        # FILTRO: Solo añadir si la coincidencia es 'exacta' o 'parcial'
                        if tipo_coincidencia in ["exacta", "parcial"]:
                            products.append(product_data)
                    except ScraperError as se:
                        # Manejo de errores a nivel de item: registra el error y continúa con el siguiente
                        print(f"Error procesando item: {se.message} (Código: {se.code})")
                        products.append({
                            'error': {
                                'code': se.code,
                                'message': se.message
                            }
                        })
                    except Exception as e:
                        # Manejo de errores inesperados a nivel de item
                        print(f"Error inesperado al procesar item: {str(e)}")
                        products.append({
                            'error': {
                                'code': ErrorCode.PARSING_ERROR,
                                'message': f"Error inesperado: {str(e)}"
                            }
                        })
                
            except ScraperError:
                # Re-lanzar errores de scraping específicos
                raise
            except Exception as e:
                # Capturar cualquier otro error inesperado durante la navegación/parsing
                raise ScraperError(ErrorCode.PARSING_ERROR, f"Error inesperado en la ejecución: {str(e)}")
            finally:
                # 6. Cerrar el navegador
                if page:
                    page.close()
                if browser:
                    browser.close()
                
    except ScraperError as se:
        # Manejo de errores de alto nivel (lanzamiento de navegador, timeout, no encontrado)
        print(f"Error de scraping: {se.message} (Código: {se.code})")
        return [{'error': {'code': se.code, 'message': se.message}}]
    except Exception as e:
        # Manejo de errores de Playwright o del contexto sync_playwright
        print(f"Error fatal: {str(e)}")
        return [{'error': {'code': ErrorCode.PARSING_ERROR, 'message': get_error_message(ErrorCode.PARSING_ERROR)}}]
    
    # 7. Verificación final
    if not products:
        error = ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
        return [{'error': {'code': error.code, 'message': error.message}}]
    
    return products