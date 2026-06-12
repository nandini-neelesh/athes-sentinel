from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.app.database.session import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class LogFile(Base):
    __tablename__ = "log_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)

    raw_logs = relationship("RawLog", back_populates="log_file")
    ip_features = relationship("IPFeature", back_populates="log_file")
    incidents = relationship("Incident", back_populates="log_file")


class RawLog(Base):
    __tablename__ = "raw_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("log_files.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    ip_address = Column(String, index=True, nullable=False)
    user_id = Column(String, nullable=True)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=False)
    event_type = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    log_file = relationship("LogFile", back_populates="raw_logs")


class IPFeature(Base):
    __tablename__ = "ip_features"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("log_files.id"), nullable=False)
    ip_address = Column(String, index=True, nullable=False)
    total_requests = Column(Integer)
    failed_login_count = Column(Integer)
    success_login_count = Column(Integer)
    error_4xx_count = Column(Integer)
    error_5xx_count = Column(Integer)
    error_rate = Column(Float)
    unique_endpoints = Column(Integer)
    endpoint_entropy = Column(Float)
    avg_response_time = Column(Float)
    max_response_time = Column(Float)
    sensitive_endpoint_count = Column(Integer)
    request_frequency = Column(Float)
    ml_anomaly_score = Column(Float, nullable=True)

    log_file = relationship("LogFile", back_populates="ip_features")


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("log_files.id"), nullable=False)
    ip_address = Column(String, index=True, nullable=False)
    incident_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    risk_score = Column(Float, nullable=False)
    evidence = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    status = Column(String, default="open")
    analyst_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    log_file = relationship("LogFile", back_populates="incidents")
