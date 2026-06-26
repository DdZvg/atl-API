from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
# from thefuzz import fuzz # Eliminado para evitar problemas de dependencia
import time
import re
from typing import Dict, Set, List, Tuple
import logging
import hashlib
import json # <-- AÑADIDO PARA UNA SALIDA MÁS LIMPIA
from cancellation import cancel_token, is_search_cancelled
from scraper_errors import ScraperError, ErrorCode, get_error_message

# ============================================================
# DEFINICIONES DE ERRORES (SIMULADAS)
# ============================================================
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
        ErrorCode.IMAGE_EXTRACTION_ERROR: "Error al extraer la URL de la imagen.",
        ErrorCode.PARSING_ERROR: "Error inesperado durante el procesamiento de la página.",
        ErrorCode.SEARCH_CANCELLED: "Búsqueda cancelada por el usuario."
    }
    return messages.get(code, "Error desconocido.")

# ============================================================
# FUNCIONES AUXILIARES (MANTENIDAS)
# ============================================================
class AdaptivePopupHandler:
    """Manejador adaptativo de popups (simplificado)"""
    def __init__(self):
        pass
    def track_popup(self, selector, success):
        pass
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clasificar_coincidencia(search_query: str, product_name: str) -> str:
    """
    Clasifica la coincidencia de forma simple, ya que 'thefuzz' no se pudo instalar.
    """
    # Clasificación simple: si la consulta está en el nombre, es exacta.
    if search_query.lower() in product_name.lower():
        return 'exacta'
    return 'parcial'

def remove_all_overlays_js(page):
    """Remover todos los overlays de forma agresiva"""
    # El error 'TypeError: Cannot read properties of null (reading 'classList')'
    # ocurre en la línea 96 del código original (document.body.classList.remove(...))
    # si document.body es null. Esto no debería pasar después de page.goto,
    # pero puede ocurrir si la página se ha cerrado o si el contexto es inválido.
    # La corrección es asegurar que document.body exista.
    page.evaluate("""() => {
        if (!document.body) return; // CORRECCIÓN: Asegurar que document.body existe
        
        const attBg = document.getElementById('att_lightbox_background');
        if (attBg) {
            attBg.remove();
        }
        
        const overlaySelectors = [
            '.modal-popup', '.modals-overlay', '.modal-backdrop', '.modal-slide',
            '[role="dialog"]', '.newsletter-modal', '#newsletter-popup',
            '.popup-container', '.modal-content', '.bio-popup', '#bio_ep',
            '.overlay-popup', '.ui-widget-overlay', '.registration-popup',
            '.register-modal', '.chat-widget', '.chat-container',
            '.fb-dialog', '.modal-dialog', '[class*="lightbox"]',
            '.overlay-background'
        ];
        
        overlaySelectors.forEach(sel => {
            try {
                document.querySelectorAll(sel).forEach(el => el.remove());
            } catch(e) {}
        });
        
        document.body.classList.remove('modal-open', '_has-modal', 'noscroll');
        document.body.style.overflow = 'auto';
        document.body.style.paddingRight = '0';
        document.body.style.pointerEvents = 'auto';
        document.documentElement.style.overflow = 'auto';
    }""")

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

def generate_product_id(name, url):
    """Genera un ID único para un producto basado en su nombre y URL"""
    unique_string = f"{name}_{url}"
    return hashlib.md5(unique_string.encode()).hexdigest()

def extract_prices(item):
    """
    Extrae los precios regular y promocional con lógica mejorada.
    """
    regular_price = "Precio no disponible"
    promo_price = "N/A"
    
    # --- Estrategia 1: Selectores CSS específicos (la más fiable) ---
    regular_price_selectors = [
        '.price-box .old-price .price', '.old-price .price', '.was-price',
        '.regular-price', '.list-price', '.original-price', '.before-price',
        'del .price', 's .price', '[data-price-type="oldPrice"] .price'
    ]
    
    promo_price_selectors = [
        '.price-box .special-price .price', '.special-price .price', '.now-price',
        '.sale-price', '.current-price', '.discount-price', '.offer-price',
        '[data-price-type="finalPrice"] .price'
    ]
    
    # Buscar precio regular
    for selector in regular_price_selectors:
        price_elem = item.select_one(selector)
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price_match = re.search(r'₡\s*[\d.,]+', price_text)
            if price_match:
                regular_price = price_match.group(0)
                break
                
    # Buscar precio promocional
    for selector in promo_price_selectors:
        price_elem = item.select_one(selector)
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price_match = re.search(r'₡\s*[\d.,]+', price_text)
            if price_match:
                promo_price = price_match.group(0)
                break

    # --- Estrategia 2: Búsqueda contextual si los selectores no son suficientes ---
    if regular_price == "Precio no disponible" or promo_price == "N/A":
        all_price_elements = item.find_all(['span', 'div', 'p', 'strong', 'del', 's'])
        found_prices = []

        for elem in all_price_elements:
            text = elem.get_text(strip=True)
            if '₡' in text:
                price_match = re.search(r'₡\s*([\d.,]+)', text)
                if price_match:
                    numeric_value = int(re.sub(r'[^\d]', '', price_match.group(1)))
                    
                    if 1000 <= numeric_value <= 5000000:
                        parent_text = ""
                        if elem.parent:
                            parent_text = elem.parent.get_text(strip=True)
                        
                        is_regular_by_label = re.search(r'regular|antes|lista|normal|original', parent_text, re.I)
                        is_promo_by_label = re.search(r'promoción|promo|oferta|ahora|final|descuento', parent_text, re.I)
                        
                        is_regular_by_class = (
                            elem.name in ['del', 's'] or
                            'line-through' in elem.get('style', '') or
                            any(cls in str(elem.get('class', '')).lower() for cls in ['old', 'was', 'regular', 'antes', 'list', 'normal', 'original'])
                        )
                        
                        is_promo_by_class = any(cls in str(elem.get('class', '')).lower() for cls in ['special', 'promo', 'sale', 'oferta', 'final', 'descuento'])
                        
                        found_prices.append({
                            'text': price_match.group(0),
                            'value': numeric_value,
                            'is_regular': is_regular_by_label or is_regular_by_class,
                            'is_promo': is_promo_by_label or is_promo_by_class
                        })
        
        for p in found_prices:
            if p['is_regular'] and regular_price == "Precio no disponible":
                regular_price = p['text']
            if p['is_promo'] and promo_price == "N/A":
                promo_price = p['text']

        # --- Estrategia 3: Último recurso, usar el valor numérico ---
        if regular_price == "Precio no disponible" or promo_price == "N/A":
            unique_prices = sorted(list({p['value'] for p in found_prices}), reverse=True)
            
            if len(unique_prices) == 1:
                if regular_price == "Precio no disponible":
                    regular_price = next(p['text'] for p in found_prices if p['value'] == unique_prices[0])
                promo_price = "N/A"
            elif len(unique_prices) > 1:
                if regular_price == "Precio no disponible":
                    regular_price = next(p['text'] for p in found_prices if p['value'] == unique_prices[0])
                if promo_price == "N/A":
                    promo_price = next(p['text'] for p in found_prices if p['value'] == unique_prices[-1])

    # --- VALIDACIÓN FINAL: Verificar si los precios son iguales ---
    if regular_price != "Precio no disponible" and promo_price != "N/A":
        regular_numeric = int(re.sub(r'[^\d]', '', regular_price))
        promo_numeric = int(re.sub(r'[^\d]', '', promo_price))
        
        if regular_numeric == promo_numeric:
            promo_price = "N/A"
    
    return regular_price, promo_price

# ============================================================
# FUNCIÓN PRINCIPAL DE SCRAPING (OPTIMIZADA CON PAGINACIÓN)
# ============================================================
def scrape_monge(search_query, max_pages=10):
    """
    Función principal de scraping para Tienda Monge.
    
    Args:
        search_query: Término de búsqueda
        max_pages: Número máximo de páginas a scrapear (por defecto 10, máximo ~90 productos)
    
    Returns:
        Lista de productos encontrados
    """
    base_url = "https://www.tiendamonge.com/"
    products = []
    popup_handler = AdaptivePopupHandler()
    seen_products = set()
    
    start_time = time.time()
    
    # Palabras a filtrar (definidas fuera del bucle para eficiencia)
    palabras_filtro = [
        'conocenos', 'servicios', 'mongepay', 'lista', 'página', 'inicio',
        'fijar', 'dirección', 'ascendente', 'descendente', 'promise',
        'object', 'contacto', 'soporte', 'acerca', 'términos', 'política',
        'Beneficios de comprar en Tienda Monge', 'Mi cesta'
    ]
    
    def extract_products_from_soup(soup, search_query, base_url, seen_products, palabras_filtro):
        """Extrae productos de un objeto BeautifulSoup parseado"""
        page_products = []
        product_items = []
        
        # Estrategia 1: Búsqueda por selectores conocidos
        product_items.extend(soup.find_all('li', class_=re.compile(r'product-item|item', re.I)))
        product_items.extend(soup.find_all('div', class_=re.compile(r'product-card|product-item|item-info', re.I)))
        
        # Estrategia 2: Búsqueda heurística si la Estrategia 1 falla
        if not product_items:
            all_divs = soup.find_all('div', class_=True)
            
            for div in all_divs:
                has_title = div.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'span', 'a'])
                has_price = div.find(['span', 'p'], string=re.compile(r'₡|\$|precio', re.I))
                has_link = div.find('a', href=True)
                
                if has_title and (has_price or has_link):
                    text_content = div.get_text(strip=True)
                    if 50 < len(text_content) < 1000:
                        product_items.append(div)
        
        # Estrategia 3: Búsqueda más amplia si todo lo demás falla
        if not product_items:
            all_elements = soup.find_all(['div', 'li', 'article', 'section'])
            
            for elem in all_elements:
                has_link = elem.find('a', href=True)
                has_price = elem.find(text=re.compile(r'₡'))
                
                if has_link and has_price:
                    title_elem = elem.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'a'])
                    if title_elem:
                        title_text = title_elem.get_text(strip=True)
                        if 10 < len(title_text) < 200:
                            product_items.append(elem)
        
        for item in product_items:
            try:
                name = None
                name_elem = (item.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) or
                            item.find('a', href=True) or
                            item.find('span') or
                            item.find('p'))
                
                if name_elem:
                    name = name_elem.get_text(strip=True)
                
                if not name or len(name) < 5:
                    continue
                
                if any(palabra.lower() in name.lower() for palabra in palabras_filtro):
                    continue
                
                if "[object" in name or "Promise" in name:
                    continue
                
                url = ""
                for link in item.find_all('a', href=True):
                    href = link.get('href', '')
                    if href and href != '#' and not href.startswith('javascript'):
                        url = href
                        break
                
                if not url or url == '#':
                    continue
                
                if not url.startswith('http'):
                    url = base_url.rstrip('/') + '/' + url.lstrip('/')
                
                # Filtro de URL inválida
                if 'catalogsearch/result/' in url:
                    logger.info(f"Producto descartado por URL inválida: {name} - {url}")
                    continue
                
                product_id = generate_product_id(name, url)
                if product_id in seen_products:
                    continue
                seen_products.add(product_id)
                
                regular_price, promo_price = extract_prices(item)
                
                img_url = ""
                img_elem = item.find('img')
                if img_elem:
                    img_url = img_elem.get('src', '') or img_elem.get('data-src', '')
                
                if not img_url:
                    continue
                
                tipo_coincidencia = clasificar_coincidencia(search_query, name)
                
                # Extracción de SKU
                sku = None
                sku_value_element = item.select_one('.product.attribute.sku .value')
                if not sku_value_element:
                    sku_value_element = item.select_one('.sku .value')

                if sku_value_element:
                    sku = sku_value_element.get_text(strip=True)
                
                # Evitar data URIs
                if img_url and img_url.startswith('data:'):
                    img_url = 'https://via.placeholder.com/300?text=No+Image'
                
                page_products.append({
                    'name': name,
                    'regular_price': regular_price,
                    'promo_price': promo_price,
                    'url': url,
                    'image_url': img_url,
                    'store': 'Monge',
                    'availability': 'disponible',
                    'sku': sku,
                    'coincidence_type': tipo_coincidencia,
                    'error': None
                })
                
            except Exception as e:
                logger.error(f"Error procesando producto: {str(e)}")
                continue
        
        return page_products, len(product_items) > 0
    
    def get_total_pages(soup):
        """Detecta el número total de páginas disponibles"""
        try:
            # Buscar el contenedor de paginación de Algolia (usado por Monge)
            pagination = soup.select_one('.ais-Pagination-list')
            if pagination:
                # Buscar todos los enlaces de página (excluyendo anterior/siguiente)
                page_links = pagination.select('a.ais-Pagination-link[aria-label^="Page"]')
                if page_links:
                    # Obtener el número más alto
                    page_numbers = []
                    for link in page_links:
                        aria_label = link.get('aria-label', '')
                        match = re.search(r'Page (\d+)', aria_label)
                        if match:
                            page_numbers.append(int(match.group(1)))
                    if page_numbers:
                        return max(page_numbers)
            
            # Alternativa: buscar por otros selectores de paginación comunes
            pagination_items = soup.select('.pages-items li a, .pagination a, .pager a')
            if pagination_items:
                page_numbers = []
                for item in pagination_items:
                    text = item.get_text(strip=True)
                    if text.isdigit():
                        page_numbers.append(int(text))
                if page_numbers:
                    return max(page_numbers)
                    
        except Exception as e:
            logger.warning(f"Error detectando páginas: {str(e)}")
        
        return 1  # Por defecto, asumir solo 1 página
    
    try:
        with sync_playwright() as p:
            # Configuración del navegador
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage', '--disable-web-security']
            )
            
            context = browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                extra_http_headers={'Accept-Language': 'es-ES,es;q=0.9'}
            )
            
            page = context.new_page()
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(40000)
            
            # Script de inicialización
            page.add_init_script("""
                window.showPopup = () => {};
                window.openModal = () => {};
                window.showNewsletterPopup = () => {};
                window.openChatWidget = () => {};
                
                function removeOverlays() {
                    const bg = document.getElementById('att_lightbox_background');
                    if (bg) bg.remove();
                    if (document.body) {
                        document.body.style.pointerEvents = 'auto';
                        document.body.style.overflow = 'auto';
                    }
                    requestAnimationFrame(removeOverlays);
                }
                requestAnimationFrame(removeOverlays);
            """)
            
            # URL base de búsqueda
            base_search_url = f"{base_url}catalogsearch/result/?q={search_query.replace(' ', '+')}"
            
            # ============================================================
            # PAGINACIÓN: Iterar por todas las páginas
            # ============================================================
            current_page = 1
            total_pages = 1
            
            while current_page <= min(max_pages, total_pages if total_pages > 0 else max_pages):
                if is_search_cancelled():
                    browser.close()
                    raise ScraperError(ErrorCode.SEARCH_CANCELLED, get_error_message(ErrorCode.SEARCH_CANCELLED))

                # Construir URL con parámetro de página
                if current_page == 1:
                    search_url = base_search_url
                else:
                    search_url = f"{base_search_url}&page={current_page}"  # Monge usa 'page' para la paginación
                
                logger.info(f"Scrapeando página {current_page}: {search_url}")
                
                # Navegar a la página con verificación de cancelación
                try:
                    safe_goto(page, search_url, wait_until='domcontentloaded')
                except PlaywrightTimeout:
                    logger.warning(f"Timeout en página {current_page}, intentando con networkidle...")
                    try:
                        safe_goto(page, search_url, wait_until='networkidle')
                    except PlaywrightTimeout:
                        logger.warning(f"Timeout con networkidle en página {current_page}, intentando sin esperar...")
                        safe_goto(page, search_url, wait_until='commit')
                
                # Esperar a que cargue con chequeo de cancelación
                safe_wait(page, 3000)
                remove_all_overlays_js(page)
                safe_wait(page, 1000)
                
                # Esperar el contenedor de productos
                try:
                    page.wait_for_selector('ol.products-list, ul.products-grid, .ais-Hits-list', timeout=10000)
                except PlaywrightTimeout:
                    logger.warning(f"Timeout esperando productos en página {current_page}.")
                
                # Scroll para cargar contenido lazy
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    safe_wait(page, 2000)
                    page.evaluate("window.scrollTo(0, 0)")
                    safe_wait(page, 1000)
                except Exception as e:
                    logger.warning(f"Error durante scroll en página {current_page}: {str(e)}")
                
                # Parsear contenido
                content = page.content()
                soup = BeautifulSoup(content, 'lxml')
                
                # En la primera página, detectar el total de páginas
                if current_page == 1:
                    total_pages = get_total_pages(soup)
                    logger.info(f"Total de páginas detectadas: {total_pages}")
                
                # Extraer productos de esta página
                page_products, found_items_on_page = extract_products_from_soup(
                    soup, search_query, base_url, seen_products, palabras_filtro
                )
                
                if page_products:
                    products.extend(page_products)
                    logger.info(f"Página {current_page}: {len(page_products)} productos extraídos (total: {len(products)})")
                else:
                    # Si no encontramos productos en esta página, puede que no haya más
                    if current_page > 1:
                        logger.info(f"No se encontraron productos en página {current_page}. Deteniendo paginación.")
                        break
                    elif current_page == 1 and not found_items_on_page:
                        logger.info(f"No se encontraron productos en la primera página. Deteniendo paginación.")
                        break
                
                current_page += 1
                
                # Pequeña pausa entre páginas para evitar ser bloqueados
                if current_page <= total_pages:
                    safe_wait(page, 1500)
            
            browser.close()
            
    except ScraperError as se:
        return [{'error': {'code': se.code, 'message': se.message}}]
    except Exception as e:
        logger.error(f"Error general: {str(e)}")
        return [{'error': {'code': ErrorCode.PARSING_ERROR, 'message': str(e)}}]
    
    total_time = time.time() - start_time
    logger.info(f"Scraping completado en {total_time:.2f} segundos. Total productos: {len(products)}")
    
    if not products:
        error = ScraperError(ErrorCode.PRODUCT_NOT_FOUND, get_error_message(ErrorCode.PRODUCT_NOT_FOUND))
        return [{'error': {'code': error.code, 'message': error.message}}]
    
    return products
