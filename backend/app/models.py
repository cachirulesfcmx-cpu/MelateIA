"""SQLAlchemy ORM models."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow)

    predictions = relationship("Prediction", back_populates="user", cascade="all, delete-orphan")


class Draw(Base):
    __tablename__ = "draws"
    __table_args__ = (UniqueConstraint("game_type", "draw_number", name="uq_game_draw"),)

    id = Column(Integer, primary_key=True, index=True)
    game_type = Column(String, index=True, nullable=False)
    draw_number = Column(Integer, index=True, nullable=False)
    draw_date = Column(String, nullable=True)         # ISO date string
    numbers = Column(String, nullable=False)          # comma-separated 6 main numbers
    additional = Column(Integer, nullable=True)       # R7 / F7 when present
    source = Column(String, default="manual")         # csv | manual
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    game_type = Column(String, index=True, nullable=False)
    strategy = Column(String, nullable=False)
    numbers = Column(String, nullable=False)          # comma-separated
    score = Column(Float, default=0.0)
    explanation = Column(Text, default="")
    status = Column(String, default="pendiente")      # pendiente | comparada | usada
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="predictions")
    results = relationship("PredictionResult", back_populates="prediction", cascade="all, delete-orphan")


class PredictionResult(Base):
    __tablename__ = "prediction_results"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), nullable=False)
    draw_id = Column(Integer, ForeignKey("draws.id"), nullable=False)
    hits = Column(Integer, default=0)
    matched_numbers = Column(String, default="")
    missed_numbers = Column(String, default="")
    evaluated_at = Column(DateTime, default=utcnow)

    prediction = relationship("Prediction", back_populates="results")


class ModelPerformance(Base):
    __tablename__ = "model_performance"
    __table_args__ = (UniqueConstraint("strategy", "game_type", name="uq_strategy_game"),)

    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String, nullable=False)
    game_type = Column(String, nullable=False)
    total_predictions = Column(Integer, default=0)
    total_hits = Column(Integer, default=0)
    average_hits = Column(Float, default=0.0)
    best_hits = Column(Integer, default=0)
    weight = Column(Float, default=1.0)               # multi-armed bandit weight
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class CsvUpload(Base):
    __tablename__ = "csv_uploads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String, nullable=False)
    game_type = Column(String, nullable=False)
    rows_imported = Column(Integer, default=0)
    uploaded_at = Column(DateTime, default=utcnow)


class LearningLog(Base):
    """Time-series snapshot of the reinforcement-learning evolution.

    One row is appended every time an evaluation updates a strategy's weight,
    so the analytics can plot how the system's learning evolves over time.
    """
    __tablename__ = "learning_log"

    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String, index=True, nullable=False)
    game_type = Column(String, index=True, nullable=False)
    hits = Column(Integer, default=0)
    weight = Column(Float, default=1.0)
    average_hits = Column(Float, default=0.0)
    created_at = Column(DateTime, default=utcnow, index=True)


class RateLimit(Base):
    """Lightweight DB-backed rate limiting (works across serverless instances)."""
    __tablename__ = "rate_limit"

    id = Column(Integer, primary_key=True, index=True)
    bucket = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)


class PushSubscription(Base):
    """Web Push subscription for notifications."""
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    endpoint = Column(Text, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class StrategyContextPerf(Base):
    """Per-context (regime) reinforcement weights for the contextual bandit."""
    __tablename__ = "strategy_context_perf"
    __table_args__ = (UniqueConstraint("strategy", "game_type", "context", name="uq_strategy_game_context"),)

    id = Column(Integer, primary_key=True, index=True)
    strategy = Column(String, nullable=False)
    game_type = Column(String, index=True, nullable=False)
    context = Column(String, index=True, nullable=False)
    total_predictions = Column(Integer, default=0)
    total_hits = Column(Integer, default=0)
    average_hits = Column(Float, default=0.0)
    weight = Column(Float, default=1.0)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
