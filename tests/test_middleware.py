"""The middleware, exercised through real requests."""

from __future__ import annotations

import logging

import pytest
from django.test import Client, override_settings
from tests.testapp.models import Author

from nplus1_guard.middleware import HEADER_NAME, NPlusOneDetected

pytestmark = pytest.mark.django_db


def settings_for(**overrides: object) -> dict[str, object]:
    return {"ENABLED": True, "THRESHOLD": 3, **overrides}


class TestDetection:
    def test_a_naive_view_is_flagged(
        self, client: Client, library: list[Author], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            response = client.get("/naive/")
        assert response.status_code == 200
        assert "10x on" in caplog.text

    def test_an_optimized_view_is_silent(
        self, client: Client, library: list[Author], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            response = client.get("/optimized/")
        assert response.status_code == 200
        assert caplog.text == ""

    def test_a_view_that_queries_nothing_is_silent(
        self, client: Client, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            client.get("/health/")
        assert caplog.text == ""

    def test_the_response_is_not_altered(
        self, client: Client, library: list[Author]
    ) -> None:
        naive = client.get("/naive/")
        optimized = client.get("/optimized/")
        assert naive.content == optimized.content


class TestHeader:
    def test_the_query_count_is_reported_in_a_header(
        self, client: Client, library: list[Author]
    ) -> None:
        assert client.get("/naive/")[HEADER_NAME] == "11"
        assert client.get("/optimized/")[HEADER_NAME] == "1"

    @override_settings(NPLUS1_GUARD={"ENABLED": True, "HEADER": False})
    def test_the_header_can_be_turned_off(
        self, client: Client, library: list[Author]
    ) -> None:
        assert HEADER_NAME not in client.get("/naive/")


class TestRaising:
    @override_settings(NPLUS1_GUARD={"ENABLED": True, "THRESHOLD": 3, "RAISE": True})
    def test_it_can_fail_loudly_instead_of_logging(
        self, client: Client, library: list[Author]
    ) -> None:
        with pytest.raises(NPlusOneDetected) as excinfo:
            client.get("/naive/")
        assert excinfo.value.path == "/naive/"
        assert excinfo.value.report.duplicates[0].count == 10

    @override_settings(NPLUS1_GUARD={"ENABLED": True, "THRESHOLD": 3, "RAISE": True})
    def test_a_clean_view_still_passes(
        self, client: Client, library: list[Author]
    ) -> None:
        assert client.get("/optimized/").status_code == 200


class TestSwitches:
    @override_settings(NPLUS1_GUARD={"ENABLED": False})
    def test_disabled_means_completely_out_of_the_way(
        self, client: Client, library: list[Author], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            response = client.get("/naive/")
        assert caplog.text == ""
        assert HEADER_NAME not in response

    @override_settings(
        NPLUS1_GUARD={"ENABLED": True, "THRESHOLD": 3, "IGNORE_PATHS": ["^/naive/"]}
    )
    def test_a_path_can_be_excused(
        self, client: Client, library: list[Author], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            client.get("/naive/")
        assert caplog.text == ""

    @override_settings(
        NPLUS1_GUARD={
            "ENABLED": True,
            "THRESHOLD": 3,
            "IGNORE_TABLES": ["testapp_publisher"],
        }
    )
    def test_a_table_can_be_excused(
        self, client: Client, library: list[Author], caplog: pytest.LogCaptureFixture
    ) -> None:
        """Some lookups are genuinely per-row and not worth hearing about."""
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            client.get("/naive/")
        assert caplog.text == ""

    @override_settings(NPLUS1_GUARD={"ENABLED": True, "THRESHOLD": 100})
    def test_a_high_threshold_forgives_everything(
        self, client: Client, library: list[Author], caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING, logger="nplus1_guard"):
            client.get("/naive/")
        assert caplog.text == ""


class TestDefaults:
    @override_settings(DEBUG=False, NPLUS1_GUARD={})
    def test_it_is_off_when_debug_is_off(
        self, client: Client, library: list[Author]
    ) -> None:
        """A detector that runs in production is a detector that slows it down."""
        assert HEADER_NAME not in client.get("/naive/")

    @override_settings(DEBUG=True, NPLUS1_GUARD={})
    def test_it_is_on_when_debug_is_on(
        self, client: Client, library: list[Author]
    ) -> None:
        assert HEADER_NAME in client.get("/naive/")
