"""SQLAlchemy database models."""
from sqlalchemy import Column, Integer, String, Float, Time, ForeignKey, Text, JSON, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
import uuid

try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    Vector = None
    PGVECTOR_AVAILABLE = False


class KnowledgeDocument(Base):
    """Reviewed source summaries, not unverified scraped pages."""
    __tablename__ = "knowledge_documents"
    id = Column(Integer, primary_key=True)
    source_key = Column(String(100), unique=True, nullable=False)
    title = Column(String(200), nullable=False)
    url = Column(String(500), nullable=False)
    city = Column(String(100), nullable=False, index=True)
    poi_name = Column(String(100), nullable=False)
    aliases = Column(JSON, nullable=False)
    reviewed_on = Column(String(10), nullable=False)
    expires_on = Column(String(10), nullable=False)
    content_hash = Column(String(64), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    chunks = relationship("KnowledgeChunk", cascade="all, delete-orphan", back_populates="document")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id = Column(String(140), primary_key=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id"), nullable=False, index=True)
    topic = Column(String(40), nullable=False)
    content = Column(Text, nullable=False)
    embedding_model = Column(String(100), nullable=False)
    embedding_vec = Column(Vector(512) if PGVECTOR_AVAILABLE else JSON, nullable=False)
    document = relationship("KnowledgeDocument", back_populates="chunks")


class User(Base):
    """User model for authentication."""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    saved_itineraries = relationship("SavedItinerary", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")


class City(Base):
    """City model."""
    __tablename__ = "cities"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    name_zh = Column(String(100), nullable=True)
    country = Column(String(100), nullable=False)
    country_zh = Column(String(100), nullable=True)
    time_zone = Column(String(50), default="UTC")
    default_currency = Column(String(10), default="USD")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_domestic = Column(Boolean, default=False, nullable=False, index=True)
    
    activities = relationship("Activity", back_populates="city", cascade="all, delete-orphan")


class Activity(Base):
    """Activity model."""
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("city_id", "provider_name", "provider_poi_id", name="uq_activity_provider_poi"),)
    
    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    name_zh = Column(String(200), nullable=True)
    category = Column(String(50), nullable=False, index=True)
    base_cost = Column(Float, default=0.0)
    avg_duration_minutes = Column(Integer, nullable=False)
    rating = Column(Float, default=0.0)  # 0-5 scale
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    open_time = Column(Time, nullable=True)  # None means always open
    close_time = Column(Time, nullable=True)
    description = Column(Text, nullable=True)
    description_zh = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # List of tags like ["family_friendly", "wheelchair_accessible"]
    provider_name = Column(String(30), nullable=True)
    provider_poi_id = Column(String(100), nullable=True)
    provider_metadata = Column(JSON, nullable=True)
    
    city = relationship("City", back_populates="activities")
    reviews = relationship("Review", back_populates="activity", cascade="all, delete-orphan")


class SavedItinerary(Base):
    """Saved itinerary model for persistence."""
    __tablename__ = "saved_itineraries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)  # Nullable for backward compatibility
    session_id = Column(String(255), nullable=False, index=True)  # Keep for non-authenticated users
    city_ids = Column(JSON, nullable=False)  # List of city IDs included in itinerary
    trip_data = Column(JSON, nullable=False)  # Full TripPreferences object
    itinerary_data = Column(JSON, nullable=False)  # Full ItineraryResponse object
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    is_public = Column(Boolean, default=False, nullable=False, index=True)
    share_token = Column(String(64), unique=True, nullable=True, index=True)
    view_count = Column(Integer, default=0, nullable=False)

    # Relationships
    user = relationship("User", back_populates="saved_itineraries")
    collaboration_sessions = relationship("CollaborationSession", back_populates="itinerary", cascade="all, delete-orphan")


class Review(Base):
    """User review for activities."""
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)  # Nullable for backward compatibility
    session_id = Column(String(255), nullable=False, index=True)  # Keep for non-authenticated users
    rating = Column(Float, nullable=False)  # 1-5 scale
    comment = Column(Text, nullable=True)
    helpful_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    activity = relationship("Activity", back_populates="reviews")
    user = relationship("User", back_populates="reviews")


class CollaborationSession(Base):
    """Real-time collaborative planning session."""
    __tablename__ = "collaboration_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_token = Column(String(64), unique=True, nullable=False, index=True)
    itinerary_id = Column(String(36), ForeignKey("saved_itineraries.id"), nullable=True)
    created_by_session = Column(String(255), nullable=False)
    participants = Column(JSON, nullable=False)  # List of {session_id, joined_at, name}
    state = Column(JSON, nullable=False)  # Current itinerary state (OT document)
    last_activity = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    itinerary = relationship("SavedItinerary", back_populates="collaboration_sessions")


class Flight(Base):
    """Flight connection between cities."""
    __tablename__ = "flights"

    id = Column(Integer, primary_key=True, index=True)
    origin_city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    destination_city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    airline = Column(String(100), nullable=True)
    avg_price = Column(Float, nullable=False)  # Average price in USD
    avg_duration_minutes = Column(Integer, nullable=False)
    frequency = Column(String(50), nullable=True)  # "daily", "3x_week", etc.

    origin_city = relationship("City", foreign_keys=[origin_city_id])
    destination_city = relationship("City", foreign_keys=[destination_city_id])


class Accommodation(Base):
    """Accommodation recommendations for cities."""
    __tablename__ = "accommodations"

    id = Column(Integer, primary_key=True, index=True)
    city_id = Column(Integer, ForeignKey("cities.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False, index=True)  # "budget", "midrange", "luxury"
    avg_price_per_night = Column(Float, nullable=False, index=True)
    rating = Column(Float, default=0.0)  # 0-5 scale
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    amenities = Column(JSON, nullable=True)  # List of amenities like ["wifi", "breakfast", "pool"]

    city = relationship("City")


class ActivityEmbedding(Base):
    """Stores vector embeddings for activities (used for RAG semantic retrieval)."""
    __tablename__ = "activity_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, unique=True, index=True)
    # embedding_vec is a pgvector VECTOR(1536) column — managed via raw SQL in migrations
    # We use JSON as the SQLAlchemy type so the ORM doesn't break if pgvector isn't installed
    embedding_vec = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    activity = relationship("Activity", backref="embedding_record")
