#!/usr/bin/env python3
"""Security validation script for CI."""

import sys
sys.path.insert(0, "/mnt/ssd_trabajo/hermes-agent")

from api.bridge import _validate_meta_payload, _sanitize_input_text, _check_phone_rate_limit, _phone_hash
import asyncio


def main():
    # Test _validate_meta_payload
    valid = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"wa_id": "584123456789", "profile": {"name": "Test"}}],
                    "messages": [{"id": "msg123", "type": "text", "text": {"body": "hola"}}]
                }
            }]
        }]
    }
    assert _validate_meta_payload(valid) is True
    assert _validate_meta_payload({"entry": []}) is False

    # Test _sanitize_input_text
    assert _sanitize_input_text("hola mundo") == "hola mundo"
    assert _sanitize_input_text("hola\x00\x01mundo") == "holamundo"
    assert len(_sanitize_input_text("a" * 2500)) == 2012

    # Test _phone_hash
    h = _phone_hash("584123456789")
    assert len(h) == 32  # Truncated SHA256 (16 bytes = 32 hex chars)

    # Test rate limit
    async def test_rl():
        for i in range(35):
            if not await _check_phone_rate_limit("584123456789"):
                assert i == 30  # 31st request blocked
                break

    asyncio.run(test_rl())
    print("All security tests passed")


if __name__ == "__main__":
    main()