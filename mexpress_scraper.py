from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import re
import time
import hashlib
from typing import List, Dict, Any
from cancellation import cancel_token, is_search_cancelled
#from scraper_errors import ScraperError, ErrorCode, get_error_message


# ============================================================
# DEFINICIONES DE ERRORES (Reutilizando la estructura del usuario)
# ============================================================
# Asumo que el archivo scraper_errors.py está disponible o que las clases
# ErrorCode y ScraperError se definen en el mismo módulo o se importan.
# Para la ejecución independiente, las defino aquí como en los ejemplos del usuario.

class ErrorCode:
    BROWSER_LAUNCH_ERROR = 200
    TIMEOUT_ERROR = 3
    PRODUCT_NOT_FOUND = 1
    NAME_EXTRACTION_ERROR = 301
    PRICE_EXTRACTION_ERROR = 300
    URL_EXTRACTION_ERROR = 302
    IMAGE_EXTRACTION_ERROR = 303
    PARSING_ERROR = 4
    MEXPRESS_SITE_ERROR = 102
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
        ErrorCode.PARSING_ERROR: "Error inesperado durante el procesamiento de la página.",
        ErrorCode.MEXPRESS_SITE_ERROR: "Error al acceder al sitio de Tienda MExpress.",
        ErrorCode.SEARCH_CANCELLED: "Búsqueda cancelada por el usuario."
    }
    return messages.get(code, "Error desconocido.")

def clasificar_coincidencia(search_query: str, product_name: str) -> str:
    """Clasificación simple de coincidencia."""
    if search_query.lower() in product_name.lower():
        return 'exacta'
    return 'parcial'

def create_search_url(query: str) -> str:
    """Formatea la consulta de búsqueda para tiendamexpress.com."""
    # La URL de búsqueda es: https://www.tiendamexpress.com/filterSearch?advs=true&cid=0&mid=0&vid=0&q={query}&sid=true&isc=true&orderBy=5
    formatted_query = query.replace(' ', '+')
    return f"https://www.tiendamexpress.com/filterSearch?advs=true&cid=0&mid=0&vid=0&q={formatted_query}&sid=true&isc=true&orderBy=5"

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

def extract_prices(item: BeautifulSoup) -> tuple[str, str]:
    """
    Extrae los precios regular y promocional de un elemento de producto.
    Basado en la estructura:
    - Precio de promoción (actual): <span class="price actual-price">¢ 579.900</span>
    - Precio regular (antiguo): <span class="price old-price">¢ 639.900</span>
    """
    regular_price = "Precio no disponible"
    promo_price = "N/A"
    
    # 1. Buscar precio regular (old-price)
    old_price_elem = item.select_one('.prices .old-price')
    if old_price_elem:
        regular_price = old_price_elem.text.strip()
        
    # 2. Buscar precio de promoción (actual-price)
    actual_price_elem = item.select_one('.prices .actual-price')
    if actual_price_elem:
        # Si hay old-price, el actual-price es el precio de promoción
        if old_price_elem:
            promo_price = actual_price_elem.text.strip()
        # Si no hay old-price, el actual-price es el precio regular
        else:
            regular_price = actual_price_elem.text.strip()
            
    if regular_price == "Precio no disponible":
        raise ScraperError(ErrorCode.PRICE_EXTRACTION_ERROR, get_error_message(ErrorCode.PRICE_EXTRACTION_ERROR))

    return regular_price, promo_price

def parse_product_item(item: BeautifulSoup) -> Dict[str, Any]:
    """Función auxiliar para extraer datos de un solo elemento de producto de BeautifulSoup."""
    
    # 1. Extraer URL y Nombre
    # El enlace principal está en un <a> dentro de 'h3.product-title'
    url_element = item.select_one('h3.product-title a')
    
    if not url_element or 'href' not in url_element.attrs:
        # Fallback: buscar el enlace de la imagen, que también contiene la URL del producto
        url_element = item.select_one('.picture a')
        if not url_element or 'href' not in url_element.attrs:
            raise ScraperError(ErrorCode.URL_EXTRACTION_ERROR, get_error_message(ErrorCode.URL_EXTRACTION_ERROR))
    
    url = "https://www.tiendamexpress.com" + url_element['href']
    
    # El nombre está en el texto del enlace
    name = url_element.text.strip()
    
    if not name:
        # Si el enlace de la imagen fue el fallback, intentar obtener el nombre del atributo 'title'
        if 'title' in url_element.attrs:
            name = url_element['title'].strip()
            
    if not name:
        raise ScraperError(ErrorCode.NAME_EXTRACTION_ERROR, get_error_message(ErrorCode.NAME_EXTRACTION_ERROR))

    # 2. Extraer URL de la imagen
    # La imagen está en un <img> dentro de un <a> con clase 'picture' o 'product-picture'
    img_element = item.select_one('.picture a img')
    
    # Si la imagen usa lazy loading, el src es un gif transparente y la URL real está en data-lazyloadsrc
    if img_element and 'data-lazyloadsrc' in img_element.attrs:
        img_url = img_element['data-lazyloadsrc']
    else:
        img_url = img_element.get('src') if img_element else None
        
    if not img_url:
        raise ScraperError(ErrorCode.IMAGE_EXTRACTION_ERROR, get_error_message(ErrorCode.IMAGE_EXTRACTION_ERROR))

    # 3. Extraer Precios
    regular_price, promo_price = extract_prices(item)
    
    # Extraer SKU (código de tienda)
    sku = None
    sku_element = item.select_one('[data-sku], .sku, .product-sku')
    if sku_element:
        sku = sku_element.text.strip()
    
    # Evitar guardar data URIs en imagen
    if img_url and img_url.startswith('data:'):
        img_url = 'https://via.placeholder.com/300?text=No+Image'

    return {
        'name': name,
        'regular_price': regular_price,
        'promo_price': promo_price,
        'url': url,
        'image_url': img_url,
        'store': 'Tienda MExpress',
        'availability': 'disponible',
        'sku': sku,
        'error': None,
        'coincidence_type': None
    }

def scrape_mexpress(search_query: str) -> List[Dict[str, Any]]:
    """
    Realiza el scraping de productos en tiendamexpress.com para una consulta de búsqueda dada.
    """
    search_url = create_search_url(search_query)
    products = []
    
    if cancel_token.is_cancelled():
        return [{'error': {'code': ErrorCode.SEARCH_CANCELLED, 'message': get_error_message(ErrorCode.SEARCH_CANCELLED)}}]
    
    try:
        with sync_playwright() as p:
            # 1. Lanzar el navegador
            try:
                browser = p.chromium.launch(headless=True)
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
                page = context.new_page()
                page.set_default_timeout(20000)
                page.set_default_navigation_timeout(30000)
                
                # 2. Navegar y esperar la carga
                page.goto(search_url, wait_until="load")
                
                # Intentar cerrar el popup de Black Days si aparece
                try:
                    # Selector del botón de cerrar el modal (la 'x')
                    close_button_selector = 'div.modal-content button.close'
                    page.wait_for_selector(close_button_selector, timeout=5000)
                    page.click(close_button_selector)
                    time.sleep(1) # Pequeña espera para que el modal desaparezca
                except PlaywrightTimeout:
                    # No hay popup o ya se cerró
                    pass
                
                # Esperar por el selector de productos, que es el contenedor principal
                product_list_selector = 'div.product-grid'
                try:
                    page.wait_for_selector(product_list_selector, timeout=15000)
                except PlaywrightTimeout:
                    # Si no encuentra el contenedor, puede que no haya resultados
                    pass 
                
                if cancel_token.is_cancelled():
                    raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED)) 
                
                # 3. Obtener el contenido y parsear con BeautifulSoup
                content = page.content()
                soup = BeautifulSoup(content, 'lxml')
                
                # 4. Encontrar todos los elementos de producto
                # Los items de producto están en 'div.item-box' dentro de 'div.product-grid'
                product_grid = soup.find('div', class_='product-grid')
                if product_grid:
                    product_items = product_grid.find_all('div', class_='item-box')
                else:
                    product_items = []
                
                if not product_items:
                    # Buscar mensaje de "no resultados"
                    no_results = soup.find('div', class_='no-result')
                    if no_results:
                        raise ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
                    else:
                        # Si no hay items ni mensaje de no resultados, asumimos un error de estructura
                        raise ScraperError(ErrorCode.PARSING_ERROR, "Estructura de página inesperada o productos no cargados.")

                # 5. Procesar cada producto
                for item in product_items:
                    try:
                        product_data = parse_product_item(item)
                        
                        # Clasificar la coincidencia
                        tipo_coincidencia = clasificar_coincidencia(search_query, product_data["name"])
                        product_data["coincidence_type"] = tipo_coincidencia
                        
                        # Solo añadir si la coincidencia es 'exacta' o 'parcial'
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
                raise
            except Exception as e:
                raise ScraperError(ErrorCode.PARSING_ERROR, f"Error inesperado en la ejecución: {str(e)}")
            finally:
                if page:
                    page.close()
                if browser:
                    browser.close()
                
    except ScraperError as se:
        print(f"Error de scraping: {se.message} (Código: {se.code})")
        return [{'error': {'code': se.code, 'message': se.message}}]
    except Exception as e:
        print(f"Error fatal: {str(e)}")
        return [{'error': {'code': ErrorCode.PARSING_ERROR, 'message': get_error_message(ErrorCode.PARSING_ERROR)}}]
    
    # 6. Verificación final
    if not products:
        error = ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
        return [{'error': {'code': error.code, 'message': error.message}}]
    
    return products