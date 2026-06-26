# wsgi.py
import sys, os

path = '/home/steve777/atlas-api'
if path not in sys.path:
    sys.path.append(path)
os.chdir(path)

from main import app
from a2wsgi import ASGIMiddleware

application = ASGIMiddleware(app)