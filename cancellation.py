
import threading

class CancellationToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    def is_cancelled(self):
        return self._event.is_set()
        
    def reset(self):
        self._event.clear()

# Global instance
cancel_token = CancellationToken()

# Global flag para desktop_app (compatible)
search_cancel_flag = None

def is_search_cancelled():
    """
    Verifica si la búsqueda ha sido cancelada.
    Chequea tanto cancel_token como search_cancel_flag (para compatibility con desktop_app)
    """
    global search_cancel_flag
    
    # Chequear cancel_token
    if cancel_token.is_cancelled():
        return True
    
    # Chequear search_cancel_flag si está disponible (para desktop_app)
    if search_cancel_flag is not None and search_cancel_flag.is_set():
        return True
    
    return False

def set_search_cancel_flag(flag):
    """
    Establece la referencia al search_cancel_flag de desktop_app
    """
    global search_cancel_flag
    search_cancel_flag = flag

