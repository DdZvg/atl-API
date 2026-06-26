from gollo_scraper import scrape_gollo
from monge_scraper import scrape_monge
from mexpress_scraper import scrape_mexpress
from coopeguanacaste_scraper import scrape_coopeguanacaste
from scraper_errors import ScraperError, ErrorCode, get_error_message
import concurrent.futures

def search_all_stores(query):
    """
    Search all stores (Gollo, Monge, Mexpress, Coopeguanacaste) simultaneously for products.
    Returns combined results from all stores with error handling.
    """
    all_results = []
    errors = []
    
    # Use ThreadPoolExecutor to run all scrapers concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit all scraping tasks
        gollo_future = executor.submit(scrape_gollo, query)
        monge_future = executor.submit(scrape_monge, query)
        mexpress_future = executor.submit(scrape_mexpress, query)
        coop_future = executor.submit(scrape_coopeguanacaste, query)
        
        # Get results from all stores
        try:
            gollo_results = gollo_future.result()
            # Check for errors in Gollo results
            gollo_errors = [p for p in gollo_results if 'error' in p and p['error'] is not None]
            gollo_products = [p for p in gollo_results if 'error' not in p or p['error'] is None]
            all_results.extend(gollo_products)
            errors.extend(gollo_errors)
        except Exception as e:
            errors.append({
                'error': {
                    'code': ErrorCode.GOLLO_SITE_ERROR.value,
                    'message': f"Error en Gollo: {str(e)}"
                }
            })
        
        try:
            monge_results = monge_future.result()
            # Check for errors in Monge results
            monge_errors = [p for p in monge_results if 'error' in p and p['error'] is not None]
            monge_products = [p for p in monge_results if 'error' not in p or p['error'] is None]
            all_results.extend(monge_products)
            errors.extend(monge_errors)
        except Exception as e:
            errors.append({
                'error': {
                    'code': ErrorCode.MONGE_SITE_ERROR.value,
                    'message': f"Error en Monge: {str(e)}"
                }
            })
        
        try:
            mexpress_results = mexpress_future.result()
            # Check for errors in Mexpress results
            mexpress_errors = [p for p in mexpress_results if 'error' in p and p['error'] is not None]
            mexpress_products = [p for p in mexpress_results if 'error' not in p or p['error'] is None]
            all_results.extend(mexpress_products)
            errors.extend(mexpress_errors)
        except Exception as e:
            errors.append({
                'error': {
                    'code': ErrorCode.MEXPRESS_SITE_ERROR.value,
                    'message': f"Error en Mexpress: {str(e)}"
                }
            })
        
        try:
            coop_results = coop_future.result()
            # Check for errors in Coopeguanacaste results
            coop_errors = [p for p in coop_results if 'error' in p and p['error'] is not None]
            coop_products = [p for p in coop_results if 'error' not in p or p['error'] is None]
            all_results.extend(coop_products)
            errors.extend(coop_errors)
        except Exception as e:
            errors.append({
                'error': {
                    'code': ErrorCode.COOPEGUANACASTE_SITE_ERROR.value,
                    'message': f"Error en Coopeguanacaste: {str(e)}"
                }
            })
    
    # If we have no results but have errors, return the errors
    if not all_results and errors:
        return errors
    
    # If we have no results and no errors, return product not found error
    if not all_results:
        return [{
            'error': {
                'code': ErrorCode.PRODUCT_NOT_FOUND.value,
                'message': get_error_message(ErrorCode.PRODUCT_NOT_FOUND)
            }
        }]
    
    # Sort results by regular price (removing currency symbol and converting to float)
    def get_price_value(product):
        try:
            price = product['regular_price'].replace('₡', '').replace('.', '').strip()
            return float(price)
        except:
            return float('inf')
    
    # Sort products by price
    all_results.sort(key=get_price_value)
    
    # Add any errors at the end of the results
    if errors:
        all_results.extend(errors)
    
    return all_results
