import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOCTOR = ROOT / "runtime" / "mcp-fleet-doctor.ps1"
MCP_DOCTOR = ROOT / "runtime" / "mcp-doctor.ps1"
IDLE_LAUNCHER = ROOT / "runtime" / "Start-WhiteStudioIdleWorker.ps1"


class McpFleetDoctorContractTests(unittest.TestCase):
    def test_deep_doctor_has_bounded_filmcraft_adapter_probe(self):
        source = DOCTOR.read_text(encoding="utf-8")
        self.assertIn("filmcraft_adapter_e2e", source)
        self.assertIn("local_stdio_adapter_e2e_pass", source)
        self.assertIn("filmcraftCheck", source)

    def test_deep_doctor_reports_idle_worker_readiness_separately(self):
        source = DOCTOR.read_text(encoding="utf-8")
        self.assertIn("idle_worker_check", source)
        self.assertIn("check_idle_worker_readiness.py", source)
        self.assertIn("readiness_report", source)

    def test_doctor_requires_host_tagged_protocol_audit(self):
        source = MCP_DOCTOR.read_text(encoding="utf-8")
        self.assertIn("host-tagged MCP protocol audit events", source)
        self.assertIn("mcp_protocol", source)
        self.assertIn("AllowDirtyRuntime", source)
        self.assertIn("candidate_dirty", source)

    def test_fleet_doctor_forwards_candidate_runtime_gate(self):
        source = DOCTOR.read_text(encoding="utf-8")
        self.assertIn("AllowDirtyRuntime", source)
        self.assertIn("doctorArgs", source)

    def test_fleet_doctor_consumes_host_protocol_audit(self):
        source = DOCTOR.read_text(encoding="utf-8")
        self.assertIn("Read-RecentMcpProtocolAudit", source)
        self.assertIn("server_protocol_audit", source)
        self.assertIn("verified_protocol_host_ids", source)
        self.assertIn("recent_protocol_audit_verified", source)

    def test_idle_launcher_exposes_heartbeat_liveness_states(self):
        source = IDLE_LAUNCHER.read_text(encoding="utf-8")
        self.assertIn("heartbeat_age_seconds", source)
        self.assertIn("heartbeat_fresh", source)
        self.assertIn("stale", source)
        self.assertIn("orphaned_heartbeat", source)

    def test_host_matrix_separates_configuration_from_current_tool_call(self):
        matrix = ROOT / "runtime" / "Check-McpHostMatrix.ps1"
        source = matrix.read_text(encoding="utf-8")
        self.assertIn("RequireCurrentToolCallEvidence", source)
        self.assertIn("current_tool_call_verified", source)
        self.assertIn("MCP_HOST_MATRIX_TOOL_CALL_UNVERIFIED", source)
        self.assertIn("configuration_only", source)
        self.assertIn("Check-CursorMcpHost.ps1", source)
        self.assertIn("Check-VSCodeMcpHost.ps1", source)
        self.assertIn("connection_evidence_present", source)
        self.assertIn("Read-RecentVerifiedHostIds", source)
        self.assertIn("verified_protocol_host_ids", source)


if __name__ == "__main__":
    unittest.main()
