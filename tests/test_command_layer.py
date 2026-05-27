import unittest

from core.command_layer import dispatch_command


class CommandLayerTests(unittest.TestCase):
    def test_requires_command(self):
        result = dispatch_command({}, handlers={})
        self.assertFalse(result["ok"])
        self.assertEqual("command_required", result["error"])

    def test_reports_unsupported_command(self):
        result = dispatch_command(
            {"command": "unknown", "payload": {}, "meta": {}},
            handlers={"status": lambda *_: {"ok": True}},
        )
        self.assertFalse(result["ok"])
        self.assertEqual("unsupported_command", result["error"])
        self.assertEqual(["status"], result["supported_commands"])

    def test_dispatches_with_payload_and_meta(self):
        seen = {}

        def _handler(payload, meta):
            seen["payload"] = payload
            seen["meta"] = meta
            return {"echo": payload.get("message"), "trace_id": meta.get("trace_id")}

        result = dispatch_command(
            {
                "command": "chat",
                "payload": {"message": "hello"},
                "meta": {"trace_id": "abc"},
            },
            handlers={"chat": _handler},
        )
        self.assertTrue(result["ok"])
        self.assertEqual("chat", result["command"])
        self.assertEqual("hello", result["result"]["echo"])
        self.assertEqual("abc", result["result"]["trace_id"])
        self.assertEqual({"message": "hello"}, seen["payload"])
        self.assertEqual({"trace_id": "abc"}, seen["meta"])


if __name__ == "__main__":
    unittest.main()

