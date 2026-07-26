"""Focused SQLite verification for additive network-flow database models."""

import unittest

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.database import models  # noqa: F401 - registers old models
from backend.app.database.network_models import (
    NetworkDataset,
    NetworkFlow,
    NetworkIncident,
    NetworkPrediction,
)
from backend.app.database.session import Base


def network_flow_values(row_number: int, **overrides):
    """Return a complete, small NSL-KDD-compatible flow for model tests."""
    values = {
        "row_number": row_number,
        "duration": 0,
        "protocol_type": "tcp",
        "service": "http",
        "flag": "SF",
        "src_bytes": 181,
        "dst_bytes": 5450,
        "land": 0,
        "wrong_fragment": 0,
        "urgent": 0,
        "hot": 0,
        "num_failed_logins": 0,
        "logged_in": 1,
        "num_compromised": 0,
        "root_shell": 0,
        "su_attempted": 0,
        "num_root": 0,
        "num_file_creations": 0,
        "num_shells": 0,
        "num_access_files": 0,
        "num_outbound_cmds": 0,
        "is_host_login": 0,
        "is_guest_login": 0,
        "count": 8,
        "srv_count": 8,
        "serror_rate": 0.0,
        "srv_serror_rate": 0.0,
        "rerror_rate": 0.0,
        "srv_rerror_rate": 0.0,
        "same_srv_rate": 1.0,
        "diff_srv_rate": 0.0,
        "srv_diff_host_rate": 0.0,
        "dst_host_count": 9,
        "dst_host_srv_count": 9,
        "dst_host_same_srv_rate": 1.0,
        "dst_host_diff_srv_rate": 0.0,
        "dst_host_same_src_port_rate": 0.11,
        "dst_host_srv_diff_host_rate": 0.0,
        "dst_host_serror_rate": 0.0,
        "dst_host_srv_serror_rate": 0.0,
        "dst_host_rerror_rate": 0.0,
        "dst_host_srv_rerror_rate": 0.0,
        "actual_label": None,
        "actual_family": None,
        "difficulty_level": None,
    }
    values.update(overrides)
    return values


class NetworkModelSchemaTest(unittest.TestCase):
    """Create, constrain, relate, and cascade the complete additive schema."""

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")

        @event.listens_for(cls.engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
            del connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def setUp(self):
        self.session = self.Session()

    def tearDown(self):
        self.session.rollback()
        self.session.close()

    def test_schema_relationships_constraints_and_cascade(self):
        table_names = set(inspect(self.engine).get_table_names())
        self.assertTrue(
            {"users", "log_files", "raw_logs", "ip_features", "incidents"}
            <= table_names
        )
        self.assertTrue(
            {
                "network_datasets",
                "network_flows",
                "network_predictions",
                "network_incidents",
            }
            <= table_names
        )

        dataset = NetworkDataset(
            filename="inference-only.csv",
            total_records=1,
            has_ground_truth=False,
            source_type="nsl_kdd_inference",
        )
        flow = NetworkFlow(**network_flow_values(row_number=0))
        prediction = NetworkPrediction(
            rf_attack_probability=0.91,
            predicted_binary=1,
            predicted_class="attack",
            threshold_used=0.38,
            model_name="NSL-KDD improved Random Forest",
            model_version="artifact-sha256",
            is_correct=None,
            actual_binary=None,
        )
        incident = NetworkIncident(
            incident_type="Predicted Network Intrusion",
            severity="high",
            risk_score=0.91,
            evidence="Random Forest attack probability exceeded threshold.",
            recommended_action="Review the network-flow record.",
            protocol_type="tcp",
            service="http",
            flag="SF",
            actual_label=None,
            actual_family=None,
        )
        dataset.flows.append(flow)
        prediction.dataset = dataset
        prediction.flow = flow
        incident.dataset = dataset
        incident.flow = flow
        incident.prediction = prediction
        self.session.add(dataset)
        self.session.commit()

        dataset_id = dataset.id
        flow_id = flow.id
        prediction_id = prediction.id
        incident_id = incident.id
        self.session.expire_all()

        reloaded_dataset = self.session.get(NetworkDataset, dataset_id)
        reloaded_flow = self.session.get(NetworkFlow, flow_id)
        reloaded_prediction = self.session.get(
            NetworkPrediction, prediction_id
        )
        reloaded_incident = self.session.get(NetworkIncident, incident_id)
        self.assertEqual(reloaded_dataset.flows[0].id, flow_id)
        self.assertEqual(reloaded_dataset.predictions[0].id, prediction_id)
        self.assertEqual(reloaded_dataset.incidents[0].id, incident_id)
        self.assertEqual(reloaded_flow.dataset.id, dataset_id)
        self.assertEqual(reloaded_flow.prediction.id, prediction_id)
        self.assertEqual(reloaded_flow.incident.id, incident_id)
        self.assertEqual(reloaded_prediction.dataset.id, dataset_id)
        self.assertEqual(reloaded_prediction.flow.id, flow_id)
        self.assertEqual(reloaded_prediction.incident.id, incident_id)
        self.assertEqual(reloaded_incident.dataset.id, dataset_id)
        self.assertEqual(reloaded_incident.flow.id, flow_id)
        self.assertEqual(reloaded_incident.prediction.id, prediction_id)
        self.assertIsNone(reloaded_flow.actual_label)
        self.assertIsNone(reloaded_flow.actual_family)
        self.assertIsNone(reloaded_flow.difficulty_level)
        self.assertIsNone(reloaded_prediction.is_correct)
        self.assertIsNone(reloaded_prediction.actual_binary)

        labelled_dataset = NetworkDataset(
            filename="labelled.txt",
            total_records=1,
            has_ground_truth=True,
            source_type="nsl_kdd_labelled",
        )
        labelled_flow = NetworkFlow(
            **network_flow_values(
                row_number=0,
                actual_label="normal",
                actual_family="normal",
                difficulty_level=21,
            )
        )
        labelled_dataset.flows.append(labelled_flow)
        self.session.add(labelled_dataset)
        self.session.commit()
        self.assertTrue(labelled_dataset.has_ground_truth)
        self.assertEqual(labelled_dataset.flows[0].actual_label, "normal")
        self.assertEqual(labelled_dataset.flows[0].actual_family, "normal")
        self.assertEqual(labelled_dataset.flows[0].difficulty_level, 21)

        duplicate_row = NetworkFlow(**network_flow_values(row_number=0))
        duplicate_row.dataset_id = dataset_id
        self.session.add(duplicate_row)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

        duplicate_prediction = NetworkPrediction(
            dataset_id=dataset_id,
            flow_id=flow_id,
            rf_attack_probability=0.8,
            predicted_binary=1,
            predicted_class="attack",
            threshold_used=0.38,
            model_name="NSL-KDD improved Random Forest",
            model_version="artifact-sha256",
        )
        self.session.add(duplicate_prediction)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

        duplicate_incident = NetworkIncident(
            dataset_id=dataset_id,
            flow_id=flow_id,
            prediction_id=prediction_id,
            incident_type="Predicted Network Intrusion",
            severity="high",
            risk_score=0.91,
            evidence="Duplicate incident must fail.",
            recommended_action="Review.",
        )
        self.session.add(duplicate_incident)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

        parent = self.session.get(NetworkDataset, dataset_id)
        self.session.delete(parent)
        self.session.commit()
        self.assertIsNone(self.session.get(NetworkDataset, dataset_id))
        self.assertIsNone(self.session.get(NetworkFlow, flow_id))
        self.assertIsNone(self.session.get(NetworkPrediction, prediction_id))
        self.assertIsNone(self.session.get(NetworkIncident, incident_id))
        self.assertEqual(
            self.session.query(NetworkFlow)
            .filter(NetworkFlow.dataset_id == dataset_id)
            .count(),
            0,
        )
        self.assertEqual(
            self.session.query(NetworkPrediction)
            .filter(NetworkPrediction.dataset_id == dataset_id)
            .count(),
            0,
        )
        self.assertEqual(
            self.session.query(NetworkIncident)
            .filter(NetworkIncident.dataset_id == dataset_id)
            .count(),
            0,
        )


if __name__ == "__main__":
    unittest.main()
