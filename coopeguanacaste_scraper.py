from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import re
import time
import hashlib
from typing import List, Dict, Any
from cancellation import cancel_token, is_search_cancelled

# ============================================================
# DEFINICIONES DE ERRORES
# ============================================================
class ErrorCode:
    BROWSER_LAUNCH_ERROR = 400
    TIMEOUT_ERROR = 401
    PRODUCT_NOT_FOUND = 402
    NAME_EXTRACTION_ERROR = 403
    PRICE_EXTRACTION_ERROR = 404
    URL_EXTRACTION_ERROR = 405
    IMAGE_EXTRACTION_ERROR = 406
    PARSING_ERROR = 407
    COOPEGUANACASTE_SITE_ERROR = 408
    SKU_EXTRACTION_ERROR = 409
    DESCRIPTION_EXTRACTION_ERROR = 410
    SEARCH_CANCELLED = 411

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
        ErrorCode.COOPEGUANACASTE_SITE_ERROR: "Error al acceder al sitio de Coopeguanacaste.",
        ErrorCode.SKU_EXTRACTION_ERROR: "Error al extraer el SKU del producto.",
        ErrorCode.COOPEGUANACASTE_SITE_ERROR: "Error al acceder al sitio de Coopeguanacaste.",
        ErrorCode.SKU_EXTRACTION_ERROR: "Error al extraer el SKU del producto.",
        ErrorCode.DESCRIPTION_EXTRACTION_ERROR: "Error al extraer la descripción del producto.",
        ErrorCode.SEARCH_CANCELLED: "Búsqueda cancelada por el usuario."
    }
    return messages.get(code, "Error desconocido.")

def clasificar_coincidencia(search_query: str, product_name: str) -> str:
    """Clasificación simple de coincidencia."""
    if search_query.lower() in product_name.lower():
        return 'exacta'
    return 'parcial'

def create_search_url(query: str, page_number: int = 1) -> str:
    """Formatea la consulta de búsqueda para tienda.coopeguanacaste.com con paginación.
    
    Args:
        query: Término de búsqueda
        page_number: Número de página (1-indexed)
    
    Returns:
        URL de búsqueda con pageSize=18 (máximo) y el número de página especificado
    """
    formatted_query = query.replace(' ', '+')
    # Usar filterSearch con pageSize=18 (máximo permitido) para obtener más resultados
    return f"https://tienda.coopeguanacaste.com/filterSearch?q={formatted_query}#/pageSize=18&viewMode=grid&orderBy=0&pageNumber={page_number}"

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

def extract_prices(item: BeautifulSoup) -> tuple:
    """
    Extrae los precios regular y promocional de un elemento de producto.
    """
    regular_price = "Precio no disponible"
    promo_price = ""
    
    # El precio regular está en un span con clase 'price actual-price' dentro de un div 'prices'
    price_elem = item.select_one('.prices .actual-price')
    
    if price_elem:
        price_text = price_elem.text.strip()
        if price_text and 'no disponible' not in price_text.lower():
            regular_price = price_text
    
    # El precio de promoción (antiguo) está en un span con clase 'old-price'
    promo_elem = item.select_one('.prices .old-price')
    if promo_elem:
        promo_price = promo_elem.text.strip()
        # Si hay precio antiguo, el precio regular extraído es el precio de oferta
        # y el precio antiguo es el precio regular original.
        regular_price_temp = regular_price
        regular_price = promo_price
        promo_price = regular_price_temp
    
    if regular_price == "Precio no disponible":
        # Si no se encuentra el precio, intentamos buscar el precio en el contenedor principal
        price_text_match = re.search(r'₡[\d\s,.]+', item.text)
        if price_text_match:
            regular_price = price_text_match.group(0).strip()
        else:
            # No lanzamos error aquí, ya que el precio puede no estar disponible
            pass

    return regular_price, promo_price

def parse_product_item_search_page(item: BeautifulSoup, search_query: str) -> Dict[str, Any]:
    """Función auxiliar para extraer datos básicos de un solo elemento de producto de la página de búsqueda."""
    
    # 1. Extraer URL y Nombre
    url_element = item.select_one('h2.product-title a')
    
    if not url_element or 'href' not in url_element.attrs:
        raise ScraperError(ErrorCode.URL_EXTRACTION_ERROR, get_error_message(ErrorCode.URL_EXTRACTION_ERROR))
    
    url = url_element['href']
    if not url.startswith('http'):
        url = 'https://tienda.coopeguanacaste.com' + url
    
    name = url_element.text.strip()
    
    if not name:
        raise ScraperError(ErrorCode.NAME_EXTRACTION_ERROR, get_error_message(ErrorCode.NAME_EXTRACTION_ERROR))

    # 2. Extraer URL de la imagen (de la página de búsqueda)
    img_url = None
    picture_link = item.select_one('.picture a')
    if picture_link and 'href' in picture_link.attrs:
        # La URL del enlace de la imagen en la vista de lista es la URL del producto, no la imagen.
        # Buscamos el 'src' del tag 'img'
        img_element = item.select_one('.picture img')
        if img_element:
            potential_url = img_element.get('src') or img_element.get('data-src') or img_element.get('data-original')
            if potential_url and not potential_url.startswith('data:'):
                img_url = potential_url
    
    if not img_url:
        img_url = 'https://tienda.coopeguanacaste.com/images/thumbs/default-image_360.png'
    
    if img_url and not img_url.startswith('http'):
        img_url = 'https://tienda.coopeguanacaste.com' + img_url

    # 3. Extraer Precios
    regular_price, promo_price = extract_prices(item)
    
    # 4. Extraer Disponibilidad
    availability = "disponible"
    availability_indicators = item.select_one('.availability, .stock-status, .in-stock')
    if availability_indicators:
        status_text = availability_indicators.text.strip().lower()
        if 'no disponible' in status_text or 'agotado' in status_text or 'sin stock' in status_text:
            availability = "no disponible"
        else:
            availability = "disponible"
    
    if 'sold-out' in item.get('class', []) or 'out-of-stock' in item.get('class', []):
        availability = "no disponible"
    
    # 5. Generar ID del producto (hash)
    product_id = hashlib.md5(f"{name}{url}".encode()).hexdigest()[:8]

    return {
        'name': name,
        'url': url,
        'image_url': img_url,
        'regular_price': regular_price,
        'promo_price': promo_price,
        'availability': availability,
        'store': 'Coopeguanacaste',
        'product_id': product_id,
        'classification': clasificar_coincidencia(search_query, name),
        'sku': None, # Se inicializa a None, se llenará en la página de detalle
        'description': None # Se inicializa a None, se llenará en la página de detalle
    }

def scrape_product_details(page, product_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Navega a la página de detalle del producto y extrae el SKU, la descripción corta y la URL de la imagen de alta resolución.
    """
    try:
        if cancel_token.is_cancelled():
            return product_data

        # Navegar a la URL del producto
        page.goto(product_data['url'], wait_until="domcontentloaded", timeout=30000)
        
        # Obtener el contenido HTML de la página después de la carga de JS
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # 1. Extraer SKU
        sku = None
        sku_element = soup.select_one('.sku .value')
        if sku_element:
            sku = sku_element.text.strip()
        
        # 2. Extraer Descripción (Corta)
        description = None
        # La descripción corta está en un div con clase 'short-description'
        description_element = soup.select_one('.short-description')
        if description_element:
            description = description_element.text.strip()
        
        # 3. Extraer URL de la imagen de alta resolución (simulando clic en el modal)
        img_hr_url = None
        
        try:
            # 3.1. Simular clic en la imagen principal para abrir el modal
            # El selector para la imagen principal que abre el modal es '.picture a'
            # El elemento a veces no es visible, intentamos forzar el clic o usar el elemento img
            page.wait_for_selector('.picture img', timeout=10000)
            page.click('.picture img', force=True)
            
            # 3.2. Esperar a que el modal cargue y la imagen de alta resolución esté visible
            # El selector para la imagen dentro del modal es 'img.mfp-img'
            page.wait_for_selector('img.mfp-img', timeout=5000)
            
            # 3.3. Obtener el src de la imagen dentro del modal
            img_element_in_modal = page.locator('img.mfp-img').first
            img_hr_url = img_element_in_modal.get_attribute('src')
            
            # 3.4. Cerrar el modal (opcional, pero buena práctica)
            page.click('.mfp-close')
            
        except Exception as e:
            print(f"[ADVERTENCIA] Fallo al simular clic o extraer imagen del modal: {e}")
            # Si falla el clic, volvemos a la lógica anterior de extraer la mejor URL posible del HTML
            
            # Intento 1: href del enlace principal
            main_link_element = soup.select_one('.picture a')
            if main_link_element and 'href' in main_link_element.attrs:
                img_hr_url = main_link_element['href']
            
            # Intento 2: data-full-image-url en la imagen
            if not img_hr_url:
                main_img_element = soup.select_one('.picture img')
                if main_img_element:
                    img_hr_url = main_img_element.get('data-full-image-url')
        
        # 3.5. Asegurar que la URL de la imagen sea absoluta y actualizar
        if img_hr_url:
            if not img_hr_url.startswith('http'):
                img_hr_url = 'https://tienda.coopeguanacaste.com' + img_hr_url
            product_data['image_url'] = img_hr_url # Sobrescribimos la URL de la imagen de la vista de lista

        # Actualizar los datos del producto
        product_data['sku'] = sku
        product_data['description'] = description
        
    except PlaywrightTimeout:
        print(f"[ADVERTENCIA] Tiempo de espera agotado al cargar la página de detalle: {product_data['url']}")
    except Exception as e:
        print(f"[ADVERTENCIA] Error al extraer detalles de {product_data['url']}: {e}")
        
    return product_data

def scrape_coopeguanacaste(search_query: str) -> List[Dict]:
    """
    Scraping principal para Coopeguanacaste.
    Usa Playwright para cargar JavaScript y obtener contenido dinámico.
    Itera por todas las páginas de resultados para obtener todos los productos.
    """
    products = []
    max_pages = 50  # Límite de seguridad para evitar loops infinitos
    
    if cancel_token.is_cancelled():
        return [{'error': {'code': ErrorCode.SEARCH_CANCELLED, 'message': get_error_message(ErrorCode.SEARCH_CANCELLED)}}]
    
    with sync_playwright() as p:
        try:
            # Iniciar el navegador (usando chromium por defecto)
            browser = p.chromium.launch()
            
            if cancel_token.is_cancelled():
                browser.close()
                raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))

            page = browser.new_page()
            
            # Navegar a la página de búsqueda inicial
            search_url = create_search_url(search_query, 1)
            print(f"[INFO] Navegando a: {search_url}")
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            
            # Esperar a que cargue el contenido dinámico inicial
            try:
                page.wait_for_selector('.product-grid', timeout=15000)
            except PlaywrightTimeout:
                # Verificar si hay mensaje de "no resultados"
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                page_text = soup.get_text().lower()
                if 'no se han encontrado' in page_text or 'sin resultados' in page_text:
                    raise ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
                raise ScraperError(ErrorCode.TIMEOUT_ERROR, get_error_message(ErrorCode.TIMEOUT_ERROR))
            
            # Cambiar el selector de productos por página a 18 (máximo)
            try:
                page_size_selector = page.locator('select#products-pagesize')
                if page_size_selector.count() > 0:
                    page_size_selector.select_option('18')
                    print("[INFO] Cambiado pageSize a 18 productos por página")
                    # Esperar a que la página se actualice
                    time.sleep(2)
                    page.wait_for_selector('.product-grid', timeout=10000)
            except Exception as e:
                print(f"[ADVERTENCIA] No se pudo cambiar el pageSize: {e}")
            
            # Iterar por todas las páginas de resultados
            current_page = 1
            processed_product_urls = set()  # Para evitar duplicados
            
            while current_page <= max_pages:
                if cancel_token.is_cancelled():
                    raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))
                
                print(f"[INFO] Procesando página {current_page}")
                
                # Pequeña pausa para asegurar que el contenido dinámico se cargue
                time.sleep(1)
                
                html_content = page.content()
                soup = BeautifulSoup(html_content, 'html.parser')
                product_items = soup.select('.product-grid .product-item')
                
                # Si no hay productos en esta página, hemos llegado al final
                if not product_items:
                    if current_page == 1:
                        # Verificar si hay mensaje de "no resultados"
                        page_text = soup.get_text().lower()
                        if 'no se han encontrado' in page_text or 'sin resultados' in page_text:
                            raise ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
                        raise ScraperError(ErrorCode.PARSING_ERROR, get_error_message(ErrorCode.PARSING_ERROR))
                    else:
                        print(f"[INFO] No hay más productos en la página {current_page}. Fin de paginación.")
                        break
                
                print(f"[INFO] Encontrados {len(product_items)} productos en la página {current_page}")
                
                # Procesar los resultados de la búsqueda
                products_added_this_page = 0
                for item in product_items:
                    if cancel_token.is_cancelled():
                        raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))

                    try:
                        # Extraer datos básicos de la página de búsqueda
                        product_data = parse_product_item_search_page(item, search_query)
                        
                        # Verificar si ya procesamos este producto (evitar duplicados)
                        if product_data['url'] in processed_product_urls:
                            continue
                        processed_product_urls.add(product_data['url'])
                        
                        # Navegar a la página de detalle para obtener SKU, descripciones y URL de imagen HR
                        product_data = scrape_product_details(page, product_data)
                        
                        products.append(product_data)
                        products_added_this_page += 1
                    except ScraperError as e:
                        print(f"[ADVERTENCIA] Error al parsear un producto: {e.message}")
                
                print(f"[INFO] Agregados {products_added_this_page} productos nuevos de la página {current_page}")
                
                # Si no se agregaron productos nuevos, probablemente estamos viendo los mismos
                if products_added_this_page == 0:
                    print("[INFO] No se encontraron productos nuevos. Fin de paginación.")
                    break
                
                # Buscar el botón de "siguiente página" o el número de la siguiente página
                # Primero, volver a la página de búsqueda si navegamos a detalles
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector('.product-grid', timeout=10000)
                
                # Intentar cambiar pageSize de nuevo (se reinicia al navegar)
                try:
                    page_size_selector = page.locator('select#products-pagesize')
                    if page_size_selector.count() > 0:
                        page_size_selector.select_option('18')
                        time.sleep(2)
                except Exception:
                    pass
                
                # Buscar botón de siguiente página
                next_page_found = False
                try:
                    # Buscar el enlace de la siguiente página por número
                    next_page_num = current_page + 1
                    next_page_link = page.locator(f'.pager a:has-text("{next_page_num}")')
                    
                    if next_page_link.count() > 0:
                        next_page_link.first.click()
                        time.sleep(2)
                        page.wait_for_selector('.product-grid', timeout=10000)
                        current_page += 1
                        next_page_found = True
                    else:
                        # Buscar botón "Siguiente" o "Next"
                        next_button = page.locator('.pager .next-page a, .pager a.next')
                        if next_button.count() > 0:
                            next_button.first.click()
                            time.sleep(2)
                            page.wait_for_selector('.product-grid', timeout=10000)
                            current_page += 1
                            next_page_found = True
                except Exception as e:
                    print(f"[INFO] No se encontró siguiente página: {e}")
                
                if not next_page_found:
                    print("[INFO] No hay más páginas disponibles. Fin de paginación.")
                    break

            browser.close()
            print(f"[INFO] Total de productos encontrados: {len(products)}")
            
        except PlaywrightTimeout:
            raise ScraperError(ErrorCode.TIMEOUT_ERROR, get_error_message(ErrorCode.TIMEOUT_ERROR))
        except ScraperError:
            raise
        except Exception as e:
            raise ScraperError(ErrorCode.BROWSER_LAUNCH_ERROR, f"{get_error_message(ErrorCode.BROWSER_LAUNCH_ERROR)} Detalle: {e}")

    if not products:
        raise ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
        
    return products