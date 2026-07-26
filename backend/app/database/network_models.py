"""Additive SQLAlchemy models for NSL-KDD-compatible network-flow analysis."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.app.database.session import Base


class NetworkDataset(Base):
    """One uploaded labelled or inference-only network-flow dataset."""

    __tablename__ = "network_datasets"
    __table_args__ = (
        CheckConstraint(
            "total_records >= 0",
            name="ck_network_datasets_total_records_nonnegative",
        ),
        CheckConstraint(
            "source_type IN ('nsl_kdd_labelled', 'nsl_kdd_inference')",
            name="ck_network_datasets_source_type",
        ),
        CheckConstraint(
            "analysis_status IN "
            "('uploaded', 'processing', 'completed', 'failed')",
            name="ck_network_datasets_analysis_status",
        ),
        CheckConstraint(
            "model_threshold IS NULL OR "
            "(model_threshold >= 0 AND model_threshold <= 1)",
            name="ck_network_datasets_model_threshold_range",
        ),
    )

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    uploaded_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    total_records = Column(Integer, nullable=False)
    has_ground_truth = Column(Boolean, nullable=False, default=False)
    source_type = Column(String(32), nullable=False)
    analysis_status = Column(
        String(32),
        nullable=False,
        default="uploaded",
        index=True,
    )
    analysis_error = Column(Text, nullable=True)
    model_name = Column(String(255), nullable=True)
    model_threshold = Column(Float, nullable=True)
    analysis_started_at = Column(DateTime, nullable=True)
    analysis_completed_at = Column(DateTime, nullable=True)

    flows = relationship(
        "NetworkFlow",
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="NetworkFlow.dataset_id",
    )
    predictions = relationship(
        "NetworkPrediction",
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="NetworkPrediction.dataset_id",
    )
    incidents = relationship(
        "NetworkIncident",
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="NetworkIncident.dataset_id",
    )


class NetworkFlow(Base):
    """One original 41-feature NSL-KDD-compatible network record."""

    __tablename__ = "network_flows"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "row_number",
            name="uq_network_flows_dataset_row_number",
        ),
        CheckConstraint(
            "row_number >= 0",
            name="ck_network_flows_row_number_nonnegative",
        ),
        CheckConstraint(
            "actual_family IS NULL OR "
            "actual_family IN ('normal', 'dos', 'probe', 'r2l', 'u2r')",
            name="ck_network_flows_actual_family",
        ),
    )

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("network_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number = Column(Integer, nullable=False)

    duration = Column(Integer, nullable=False)
    protocol_type = Column(String(32), nullable=False, index=True)
    service = Column(String(64), nullable=False, index=True)
    flag = Column(String(16), nullable=False)
    src_bytes = Column(BigInteger, nullable=False)
    dst_bytes = Column(BigInteger, nullable=False)
    land = Column(Integer, nullable=False)
    wrong_fragment = Column(Integer, nullable=False)
    urgent = Column(Integer, nullable=False)
    hot = Column(Integer, nullable=False)
    num_failed_logins = Column(Integer, nullable=False)
    logged_in = Column(Integer, nullable=False)
    num_compromised = Column(Integer, nullable=False)
    root_shell = Column(Integer, nullable=False)
    su_attempted = Column(Integer, nullable=False)
    num_root = Column(Integer, nullable=False)
    num_file_creations = Column(Integer, nullable=False)
    num_shells = Column(Integer, nullable=False)
    num_access_files = Column(Integer, nullable=False)
    num_outbound_cmds = Column(Integer, nullable=False)
    is_host_login = Column(Integer, nullable=False)
    is_guest_login = Column(Integer, nullable=False)
    count = Column(Integer, nullable=False)
    srv_count = Column(Integer, nullable=False)
    serror_rate = Column(Float, nullable=False)
    srv_serror_rate = Column(Float, nullable=False)
    rerror_rate = Column(Float, nullable=False)
    srv_rerror_rate = Column(Float, nullable=False)
    same_srv_rate = Column(Float, nullable=False)
    diff_srv_rate = Column(Float, nullable=False)
    srv_diff_host_rate = Column(Float, nullable=False)
    dst_host_count = Column(Integer, nullable=False)
    dst_host_srv_count = Column(Integer, nullable=False)
    dst_host_same_srv_rate = Column(Float, nullable=False)
    dst_host_diff_srv_rate = Column(Float, nullable=False)
    dst_host_same_src_port_rate = Column(Float, nullable=False)
    dst_host_srv_diff_host_rate = Column(Float, nullable=False)
    dst_host_serror_rate = Column(Float, nullable=False)
    dst_host_srv_serror_rate = Column(Float, nullable=False)
    dst_host_rerror_rate = Column(Float, nullable=False)
    dst_host_srv_rerror_rate = Column(Float, nullable=False)

    actual_label = Column(String(64), nullable=True)
    actual_family = Column(String(16), nullable=True, index=True)
    difficulty_level = Column(Integer, nullable=True)

    dataset = relationship(
        "NetworkDataset",
        back_populates="flows",
        foreign_keys=[dataset_id],
    )
    prediction = relationship(
        "NetworkPrediction",
        back_populates="flow",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="NetworkPrediction.flow_id",
        uselist=False,
        single_parent=True,
    )
    incident = relationship(
        "NetworkIncident",
        back_populates="flow",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="NetworkIncident.flow_id",
        uselist=False,
        single_parent=True,
    )


class NetworkPrediction(Base):
    """One final frozen-model prediction for one network flow."""

    __tablename__ = "network_predictions"
    __table_args__ = (
        CheckConstraint(
            "rf_attack_probability >= 0 AND rf_attack_probability <= 1",
            name="ck_network_predictions_probability_range",
        ),
        CheckConstraint(
            "predicted_binary IN (0, 1)",
            name="ck_network_predictions_binary",
        ),
        CheckConstraint(
            "predicted_class IN ('normal', 'attack')",
            name="ck_network_predictions_class",
        ),
        CheckConstraint(
            "threshold_used >= 0 AND threshold_used <= 1",
            name="ck_network_predictions_threshold_range",
        ),
        CheckConstraint(
            "actual_binary IS NULL OR actual_binary IN (0, 1)",
            name="ck_network_predictions_actual_binary",
        ),
    )

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("network_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flow_id = Column(
        Integer,
        ForeignKey("network_flows.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    rf_attack_probability = Column(Float, nullable=False, index=True)
    predicted_binary = Column(Integer, nullable=False)
    predicted_class = Column(String(16), nullable=False, index=True)
    threshold_used = Column(Float, nullable=False)
    model_name = Column(String(255), nullable=False)
    model_version = Column(String(128), nullable=False)
    is_correct = Column(Boolean, nullable=True)
    actual_binary = Column(Integer, nullable=True)

    dataset = relationship(
        "NetworkDataset",
        back_populates="predictions",
        foreign_keys=[dataset_id],
    )
    flow = relationship(
        "NetworkFlow",
        back_populates="prediction",
        foreign_keys=[flow_id],
    )
    incident = relationship(
        "NetworkIncident",
        back_populates="prediction",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="NetworkIncident.prediction_id",
        uselist=False,
        single_parent=True,
    )


class NetworkIncident(Base):
    """An explainable analyst workflow item for a predicted network intrusion."""

    __tablename__ = "network_incidents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'investigating', 'resolved', 'false_positive')",
            name="ck_network_incidents_status",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1",
            name="ck_network_incidents_risk_score_range",
        ),
        CheckConstraint(
            "actual_family IS NULL OR "
            "actual_family IN ('normal', 'dos', 'probe', 'r2l', 'u2r')",
            name="ck_network_incidents_actual_family",
        ),
    )

    id = Column(Integer, primary_key=True)
    dataset_id = Column(
        Integer,
        ForeignKey("network_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    flow_id = Column(
        Integer,
        ForeignKey("network_flows.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    prediction_id = Column(
        Integer,
        ForeignKey("network_predictions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )
    incident_type = Column(String(128), nullable=False)
    severity = Column(String(32), nullable=False, index=True)
    risk_score = Column(Float, nullable=False, index=True)
    evidence = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    status = Column(
        String(32),
        nullable=False,
        default="open",
        index=True,
    )
    protocol_type = Column(String(32), nullable=True)
    service = Column(String(64), nullable=True)
    flag = Column(String(16), nullable=True)
    actual_label = Column(String(64), nullable=True)
    actual_family = Column(String(16), nullable=True)

    dataset = relationship(
        "NetworkDataset",
        back_populates="incidents",
        foreign_keys=[dataset_id],
    )
    flow = relationship(
        "NetworkFlow",
        back_populates="incident",
        foreign_keys=[flow_id],
    )
    prediction = relationship(
        "NetworkPrediction",
        back_populates="incident",
        foreign_keys=[prediction_id],
    )
