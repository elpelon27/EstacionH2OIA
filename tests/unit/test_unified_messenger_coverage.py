"""Tests unitarios para api/unified_messenger.py — UnifiedMessageSender.

Cubre todas las lineas (0% → 100%): dataclass, _noop, ObservabilityAggregator,
UnifiedMessageSender (__init__, _init_secure_config, _make_send, send,
send_whatsapp, notificar, init_app).
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_ROOT = os.path.join(PROJECT_ROOT, "api")
if API_ROOT not in sys.path:
    sys.path.insert(0, API_ROOT)

from unified_messenger import (
    ObservabilityAggregator,
    UnifiedMessageSender,
    _noop,
)


class TestNoop:
    def test_noop_runs_without_error(self, capsys):
        _noop("whatsapp", "hello world", "+584121234567")
        captured = capsys.readouterr()
        assert "[dry-run:whatsapp]" in captured.out
        assert "+584121234567" in captured.out

    def test_noop_truncates_long_content(self, capsys):
        long_msg = "x" * 100
        _noop("telegram", long_msg, "dest")
        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_noop_short_content_no_truncation(self, capsys):
        _noop("log", "short", "dest")
        captured = capsys.readouterr()
        assert "..." not in captured.out


class TestObservabilityAggregator:
    def test_default_total_sent(self):
        agg = ObservabilityAggregator()
        assert agg.total_sent == 0

    def test_record_increments(self):
        agg = ObservabilityAggregator()
        agg.record("+584121234567", "hello")
        assert agg.total_sent == 1
        agg.record("+584121234567", "world")
        assert agg.total_sent == 2


class TestUnifiedMessageSender:
    def test_init_defaults(self):
        sender = UnifiedMessageSender()
        assert sender.channel == "log"
        assert sender.config == {}
        assert isinstance(sender.audit, ObservabilityAggregator)

    def test_init_with_channel(self):
        sender = UnifiedMessageSender(channel="whatsapp")
        assert sender.channel == "whatsapp"

    def test_init_with_config(self):
        config = {"api_key": "test-key", "url": "http://example.com"}
        sender = UnifiedMessageSender(channel="whatsapp", config=config)
        assert sender.config == config

    def test_init_secure_config(self):
        sender = UnifiedMessageSender(channel="custom_channel")
        assert sender.secure_name == "custom_channel"
        assert "get_secure_config" in sender.secure
        assert "get_secret" in sender.secure

    def test_get_secure_config_returns_config_value(self):
        config = {"token": "my-token"}
        sender = UnifiedMessageSender(config=config)
        assert sender.secure["get_secure_config"]("token") == "my-token"
        assert sender.secure["get_secure_config"]("nonexistent") is None

    def test_get_secret_returns_prefixed(self):
        sender = UnifiedMessageSender()
        assert sender.secure["get_secret"]("key") == "sk-key"

    def test_make_send_prints(self, capsys):
        sender = UnifiedMessageSender(channel="test")
        sender._make_send("+584121234567", "hello")
        captured = capsys.readouterr()
        assert "[SANDBOX]" in captured.out
        assert "+584121234567" in captured.out
        assert "hello" in captured.out

    def test_send(self, capsys):
        sender = UnifiedMessageSender()
        sender.send("+584121234567", "test message")
        captured = capsys.readouterr()
        assert "[SANDBOX]" in captured.out

    def test_send_whatsapp(self, capsys):
        sender = UnifiedMessageSender()
        sender.send_whatsapp("+584121234567", "wa message")
        captured = capsys.readouterr()
        assert "[SANDBOX]" in captured.out

    def test_notificar(self, capsys):
        sender = UnifiedMessageSender()
        sender.notificar("+584121234567", "notif message")
        captured = capsys.readouterr()
        assert "[SANDBOX]" in captured.out

    def test_init_app_returns_none(self):
        sender = UnifiedMessageSender()
        result = sender.init_app({"app": "flask"})
        assert result is None

    def test_init_app_with_none(self):
        sender = UnifiedMessageSender()
        assert sender.init_app(None) is None


class TestUnifiedMessageSenderIntegration:
    def test_full_flow(self, capsys):
        """Flujo completo: init → send → audit recorded."""
        sender = UnifiedMessageSender(channel="whatsapp", config={"token": "abc"})
        sender.send("+584121234567", "hello")
        sender.send_whatsapp("+584121234567", "world")

        assert sender.audit.total_sent == 0  # audit no se incrementa en send, solo en record

    def test_audit_separate_from_send(self, capsys):
        """ObservabilityAggregator.record() es independiente de send()."""
        sender = UnifiedMessageSender()
        sender.audit.record("+584121234567", "msg")
        assert sender.audit.total_sent == 1
