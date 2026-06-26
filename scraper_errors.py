from enum import Enum

class ScraperError(Exception):
    """Base exception class for scraper errors"""
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(self.message)

class ErrorCode(Enum):
    # General errors (1-99)
    PRODUCT_NOT_FOUND = 1
    NETWORK_ERROR = 2
    TIMEOUT_ERROR = 3
    PARSING_ERROR = 4
    SEARCH_CANCELLED = 5
    
    # Store specific errors (100-199)
    GOLLO_SITE_ERROR = 100
    MONGE_SITE_ERROR = 101
    MEXPRESS_SITE_ERROR = 102
    COOPEGUANACASTE_SITE_ERROR = 103
    
    # Browser errors (200-299)
    BROWSER_LAUNCH_ERROR = 200
    PAGE_LOAD_ERROR = 201
    SELECTOR_NOT_FOUND = 202
    
    # Data extraction errors (300-399)
    PRICE_EXTRACTION_ERROR = 300
    NAME_EXTRACTION_ERROR = 301
    URL_EXTRACTION_ERROR = 302
    IMAGE_EXTRACTION_ERROR = 303

def get_error_message(code):
    """Returns a user-friendly error message for each error code"""
    messages = {
        ErrorCode.PRODUCT_NOT_FOUND: "No se encontraron productos que coincidan con la búsqueda",
        ErrorCode.NETWORK_ERROR: "Error de conexión. Por favor, verifique su conexión a internet",
        ErrorCode.TIMEOUT_ERROR: "La búsqueda ha excedido el tiempo de espera",
        ErrorCode.PARSING_ERROR: "Error al procesar los datos de la página",
        ErrorCode.SEARCH_CANCELLED: "Búsqueda cancelada por el usuario",
        
        ErrorCode.GOLLO_SITE_ERROR: "Error al acceder al sitio de Gollo",
        ErrorCode.MONGE_SITE_ERROR: "Error al acceder al sitio de Monge",
        ErrorCode.MEXPRESS_SITE_ERROR: "Error al acceder al sitio de Tienda MExpress",
        ErrorCode.COOPEGUANACASTE_SITE_ERROR: "Error al acceder al sitio de Coopeguanacaste",
        

        ErrorCode.BROWSER_LAUNCH_ERROR: "Error al iniciar el navegador",
        ErrorCode.PAGE_LOAD_ERROR: "Error al cargar la página",
        ErrorCode.SELECTOR_NOT_FOUND: "Error al encontrar elementos en la página",
        
        ErrorCode.PRICE_EXTRACTION_ERROR: "Error al extraer información de precios",
        ErrorCode.NAME_EXTRACTION_ERROR: "Error al extraer nombres de productos",
        ErrorCode.URL_EXTRACTION_ERROR: "Error al extraer URLs de productos",
        ErrorCode.IMAGE_EXTRACTION_ERROR: "Error al extraer imágenes de productos"
    }
    return messages.get(code, "Error desconocido")
