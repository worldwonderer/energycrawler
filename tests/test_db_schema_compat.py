# -*- coding: utf-8 -*-
"""
Compatibility tests for lightweight DB schema upgrades.
"""

from sqlalchemy import create_engine, text

from database.db_session import _ensure_twitter_tweet_schema


def test_ensure_twitter_tweet_schema_adds_missing_columns(tmp_path):
    db_path = tmp_path / "compat.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE twitter_tweet (
                    id INTEGER PRIMARY KEY,
                    tweet_id VARCHAR(255)
                )
                """
            )
        )
        _ensure_twitter_tweet_schema(conn)

        columns = {
            row[1]  # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
            for row in conn.execute(text("PRAGMA table_info(twitter_tweet)")).fetchall()
        }

    assert {"urls", "user_mentions", "media_detail"}.issubset(columns)


def test_ensure_twitter_tweet_schema_is_idempotent(tmp_path):
    db_path = tmp_path / "compat-idempotent.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE twitter_tweet (
                    id INTEGER PRIMARY KEY,
                    tweet_id VARCHAR(255)
                )
                """
            )
        )
        _ensure_twitter_tweet_schema(conn)
        _ensure_twitter_tweet_schema(conn)

        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(twitter_tweet)")).fetchall()
        }

    assert {"urls", "user_mentions", "media_detail"}.issubset(columns)
