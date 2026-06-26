"""
Modelos de base de datos para almacenamiento temporal de búsquedas.
"""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class SearchResult(db.Model):
    """
    Modelo para almacenar resultados de búsquedas.
    """
    __tablename__ = 'search_results'
    
    id = db.Column(db.Integer, primary_key=True)
    search_query = db.Column(db.String(255), nullable=False, index=True)
    store = db.Column(db.String(50), nullable=False)  # gollo, monge, mexpress, coopeguanacaste
    product_name = db.Column(db.String(500), nullable=False)
    price = db.Column(db.String(50))  # Mantenido para compatibilidad
    regular_price = db.Column(db.String(50))  # Precio regular/sin promoción
    promo_price = db.Column(db.String(50))    # Precio con promoción
    availability = db.Column(db.String(100))
    url = db.Column(db.String(500))
    image_url = db.Column(db.String(500))
    sku = db.Column(db.String(100))
    category = db.Column(db.String(255))
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Hash único para evitar duplicados (combinación de store + product_name + sku)
    unique_hash = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Campo especial: ID de grupo de comparación (productos similares)
    comparison_group_id = db.Column(db.Integer, db.ForeignKey('comparison_groups.id'), nullable=True, index=True)
    
    # Relación con grupo de comparación
    comparison_group = db.relationship('ComparisonGroup', backref='products', lazy=True)
    
    def __repr__(self):
        return f'<SearchResult {self.id}: {self.product_name} - {self.store}>'
    
    def to_dict(self):
        """Convierte el modelo a diccionario."""
        return {
            'id': self.id,
            'search_query': self.search_query,
            'store': self.store,
            'name': self.product_name,  # Alias for frontend compatibility
            'product_name': self.product_name,
            'price': self.price,
            'regular_price': self.regular_price,
            'promo_price': self.promo_price,
            'availability': self.availability,
            'url': self.url,
            'image_url': self.image_url,
            'sku': self.sku,
            'category': self.category,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'comparison_group_id': self.comparison_group_id,
        }


class ComparisonGroup(db.Model):
    """
    Modelo para agrupar productos similares para comparación automática.
    Productos con el mismo nombre (normalizado) pertenecen al mismo grupo.
    """
    __tablename__ = 'comparison_groups'
    
    id = db.Column(db.Integer, primary_key=True)
    normalized_name = db.Column(db.String(500), unique=True, nullable=False, index=True)
    search_query = db.Column(db.String(255), nullable=False, index=True)
    
    # Información de comparación
    min_price = db.Column(db.Float)  # Precio mínimo en el grupo
    max_price = db.Column(db.Float)  # Precio máximo en el grupo
    avg_price = db.Column(db.Float)  # Precio promedio
    store_count = db.Column(db.Integer, default=0)  # Cantidad de tiendas diferentes
    product_count = db.Column(db.Integer, default=0)  # Cantidad de productos en el grupo
    
    cheapest_store = db.Column(db.String(50))  # Tienda con el precio más bajo
    most_expensive_store = db.Column(db.String(50))  # Tienda con el precio más alto
    
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ComparisonGroup {self.normalized_name}: {self.product_count} productos>'
    
    def to_dict(self):
        """Convierte el modelo a diccionario."""
        return {
            'id': self.id,
            'normalized_name': self.normalized_name,
            'search_query': self.search_query,
            'min_price': self.min_price,
            'max_price': self.max_price,
            'avg_price': self.avg_price,
            'store_count': self.store_count,
            'product_count': self.product_count,
            'cheapest_store': self.cheapest_store,
            'most_expensive_store': self.most_expensive_store,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
        }


class SearchSession(db.Model):
    """
    Modelo para rastrear sesiones de búsqueda.
    Útil para agrupar múltiples búsquedas y generar reportes.
    """
    __tablename__ = 'search_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    total_results = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SearchSession {self.session_id}: {self.total_results} resultados>'


class TrackedProduct(db.Model):
    """
    Modelo para productos que el usuario quiere seguir (tracking).
    Base separada del almacenamiento temporal de búsquedas.
    """
    __tablename__ = 'tracked_products'
    
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(500), nullable=False, index=True)
    store = db.Column(db.String(50), nullable=False, index=True)
    url = db.Column(db.String(500))
    image_url = db.Column(db.String(500))
    sku = db.Column(db.String(100))
    category = db.Column(db.String(255))
    
    # Hash único para identificar el producto
    product_hash = db.Column(db.String(100), unique=True, nullable=False, index=True)
    
    # Precio inicial y actual
    initial_price = db.Column(db.Float)
    current_price = db.Column(db.Float)
    lowest_price = db.Column(db.Float)
    highest_price = db.Column(db.Float)
    
    # Alertas
    target_price = db.Column(db.Float)  # Precio objetivo para alertas
    alert_enabled = db.Column(db.Boolean, default=False)
    last_alert_sent = db.Column(db.DateTime)
    
    # Metadatos
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relación con historial de precios
    price_history = db.relationship('PriceHistory', backref='product', lazy='dynamic', 
                                    cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<TrackedProduct {self.product_name} - {self.store}>'
    
    def to_dict(self):
        """Convierte el modelo a diccionario."""
        return {
            'id': self.id,
            'product_name': self.product_name,
            'store': self.store,
            'url': self.url,
            'image_url': self.image_url,
            'sku': self.sku,
            'category': self.category,
            'initial_price': self.initial_price,
            'current_price': self.current_price,
            'lowest_price': self.lowest_price,
            'highest_price': self.highest_price,
            'target_price': self.target_price,
            'alert_enabled': self.alert_enabled,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'price_count': self.price_history.count() if self.price_history else 0,
        }


class PriceHistory(db.Model):
    """
    Modelo para guardar el historial de precios de un producto.
    Cada registro es un "snapshot" del precio en un momento dado.
    """
    __tablename__ = 'price_history'
    
    id = db.Column(db.Integer, primary_key=True)
    tracked_product_id = db.Column(db.Integer, db.ForeignKey('tracked_products.id'), nullable=False, index=True)
    
    # Precios en este snapshot
    regular_price = db.Column(db.Float)
    promo_price = db.Column(db.Float)
    effective_price = db.Column(db.Float, nullable=False)  # El precio más bajo (promo o regular)
    
    # Metadatos
    availability = db.Column(db.String(100))
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Indicador de cambio
    price_change = db.Column(db.Float, default=0)  # Diferencia con el precio anterior
    price_change_percent = db.Column(db.Float, default=0)  # Porcentaje de cambio
    
    def __repr__(self):
        return f'<PriceHistory {self.tracked_product_id}: {self.effective_price} @ {self.recorded_at}>'
    
    def to_dict(self):
        """Convierte el modelo a diccionario."""
        return {
            'id': self.id,
            'tracked_product_id': self.tracked_product_id,
            'regular_price': self.regular_price,
            'promo_price': self.promo_price,
            'effective_price': self.effective_price,
            'availability': self.availability,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
            'price_change': self.price_change,
            'price_change_percent': self.price_change_percent,
        }


class PriceAlert(db.Model):
    """
    Modelo para almacenar alertas de precio enviadas.
    Registro histórico de notificaciones.
    """
    __tablename__ = 'price_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    tracked_product_id = db.Column(db.Integer, db.ForeignKey('tracked_products.id'), nullable=False, index=True)
    
    alert_type = db.Column(db.String(50), nullable=False)  # 'price_drop', 'target_reached', 'lowest_ever'
    old_price = db.Column(db.Float)
    new_price = db.Column(db.Float)
    target_price = db.Column(db.Float)
    
    message = db.Column(db.Text)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Relación
    product = db.relationship('TrackedProduct', backref='alerts')
    
    def __repr__(self):
        return f'<PriceAlert {self.alert_type}: {self.old_price} -> {self.new_price}>'
    
    def to_dict(self):
        """Convierte el modelo a diccionario."""
        return {
            'id': self.id,
            'tracked_product_id': self.tracked_product_id,
            'alert_type': self.alert_type,
            'old_price': self.old_price,
            'new_price': self.new_price,
            'target_price': self.target_price,
            'message': self.message,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'product': self.product.to_dict() if self.product else None,
        }
