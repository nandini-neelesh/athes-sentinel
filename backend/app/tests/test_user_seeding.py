"""Tests for environment-driven user provisioning (no hardcoded credentials)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.auth.service import (
    authenticate_user,
    create_demo_users,
    hash_password,
    seed_users,
)
from backend.app.database import models  # noqa: F401 - registers all tables
from backend.app.database.models import User
from backend.app.database.session import Base


SEED_ENV_KEYS = (
    "ATHES_ENV",
    "ATHES_SEED_DEMO_USERS",
    "ATHES_ADMIN_USERNAME",
    "ATHES_ADMIN_PASSWORD",
    "ATHES_ANALYST_USERNAME",
    "ATHES_ANALYST_PASSWORD",
)


class UserSeedingTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        self.db = sessionmaker(bind=engine)()
        self.addCleanup(self.db.close)

    def seed(self, **env):
        clean = {key: "" for key in SEED_ENV_KEYS}
        clean.update(env)

        with mock.patch.dict(os.environ, clean):
            seed_users(self.db)

    def usernames(self):
        return sorted(user.username for user in self.db.query(User).all())

    def test_development_seeds_demo_users(self):
        self.seed()

        self.assertEqual(self.usernames(), ["admin", "analyst"])

    def test_production_does_not_seed_demo_users(self):
        self.seed(ATHES_ENV="production")

        self.assertEqual(self.usernames(), [])

    def test_production_can_opt_in_to_demo_users(self):
        self.seed(ATHES_ENV="production", ATHES_SEED_DEMO_USERS="true")

        self.assertEqual(self.usernames(), ["admin", "analyst"])

    def test_production_creates_configured_admin(self):
        self.seed(
            ATHES_ENV="production",
            ATHES_ADMIN_USERNAME="nandini",
            ATHES_ADMIN_PASSWORD="a-strong-passphrase",
        )

        self.assertEqual(self.usernames(), ["nandini"])
        user = authenticate_user("nandini", "a-strong-passphrase", self.db)
        self.assertIsNotNone(user)
        self.assertEqual(user.role, "admin")

    def test_production_removes_leftover_default_demo_accounts(self):
        create_demo_users(self.db)

        self.seed(
            ATHES_ENV="production",
            ATHES_ADMIN_USERNAME="nandini",
            ATHES_ADMIN_PASSWORD="a-strong-passphrase",
        )

        self.assertEqual(self.usernames(), ["nandini"])

    def test_production_keeps_demo_account_whose_password_was_changed(self):
        self.db.add(
            User(
                username="admin",
                hashed_password=hash_password("not-the-default-1"),
                role="admin",
            )
        )
        self.db.commit()

        self.seed(ATHES_ENV="production")

        self.assertEqual(self.usernames(), ["admin"])
        self.assertIsNone(authenticate_user("admin", "admin123", self.db))

    def test_configured_admin_named_admin_gets_new_password(self):
        create_demo_users(self.db)

        self.seed(
            ATHES_ENV="production",
            ATHES_ADMIN_USERNAME="admin",
            ATHES_ADMIN_PASSWORD="a-strong-passphrase",
        )

        self.assertIsNone(authenticate_user("admin", "admin123", self.db))
        self.assertIsNotNone(
            authenticate_user("admin", "a-strong-passphrase", self.db)
        )

    def test_short_configured_password_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.seed(
                ATHES_ENV="production",
                ATHES_ADMIN_USERNAME="nandini",
                ATHES_ADMIN_PASSWORD="short",
            )

    def test_username_without_password_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.seed(ATHES_ENV="production", ATHES_ADMIN_USERNAME="nandini")


if __name__ == "__main__":
    unittest.main()
