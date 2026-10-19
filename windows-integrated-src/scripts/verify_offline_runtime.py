"""Check the actual standalone desktop entry and native GUI with network sockets blocked.

This is a regression smoke check for offline compatibility, not an OS firewall.
It does NOT build Windows executables; run that separately on Windows.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BLOCKER = '''"""Network-disabled Python subprocess: blocks outbound socket calls."""
import socket

def no_connection(*args, **kwargs):
    raise OSError("Offline verification: network calls are blocked")

socket.socket.connect = no_connection
socket.socket.connect_ex = no_connection
socket.socket.sendto = no_connection
socket.socket.sendall = no_connection
socket.create_connection = no_connection
socket.getaddrinfo = no_connection
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwack-offline-check-") as tmp:
        blocker = Path(tmp) / "sitecustomize.py"
        blocker.write_text(BLOCKER, encoding="utf-8")
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [tmp, str(ROOT), env.get("PYTHONPATH", "")]))
        env["AIWACK_DATA_DIR"] = str(Path(tmp) / "data")
        commands = [[sys.executable, "-m", "desktop.entry", "--self-test"]]
        xvfb = shutil.which("xvfb-run")
        if xvfb:
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.desktop_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage29_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage30_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage31_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage32_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage33_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage34_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage35_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage42_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage43_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage44_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage45_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage46_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage47_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage48_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage49_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage50_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage51_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage52_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage53_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_offline_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_local_import_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_audit_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_links_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_trace_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_evidence_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_exports_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_verification_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_drift_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_followups_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_followup_notes_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_followup_recheck_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_followup_domains_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_url_preflight_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_preflight_export_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_source_overlap_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_file_custody_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_preview_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_manifest_builder_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_manifest_stability_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_windows_names_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_duplicate_json_keys_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_provenance_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_context_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_custody_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_url_review_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_link_preview_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_source_hints_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_navigation_directives_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_active_targets_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_form_controls_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_passive_resources_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_responsive_images_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_usage_hints_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_css_references_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_bundle_receipt_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage54_receipt_reverification_gui_smoke"])
        if xvfb:
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage55_offline_browser_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage56_code_authoring_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage57_restricted_code_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage58_media_adapters_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage59_offline_service_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage60_tool_audit_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage61_business_portfolio_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage62_business_discovery_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage63_market_evidence_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage64_financial_feasibility_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage65_chief_business_decisions_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage66_business_projects_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage67_product_catalog_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage68_product_production_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage69_release_review_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage70_service_operations_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage71_sales_channel_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage72_listing_prices_gui_smoke"])
            commands.append([xvfb, "-a", sys.executable, "-m", "scripts.stage73_simulated_orders_gui_smoke"])
        # Optional verification batches for constrained CI/console runtimes.
        # Defaults to the entire suite; slicing is only a test-runner feature.
        start = int(os.environ.get('AIWACK_OFFLINE_START', '0'))
        end = int(os.environ.get('AIWACK_OFFLINE_END', str(len(commands))))
        if not (0 <= start <= end <= len(commands)):
            raise ValueError('잘못된 오프라인 검증 범위')
        print(f'Offline checks {start}:{end} of {len(commands)}', flush=True)
        commands = commands[start:end]
        for cmd in commands:
            result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=100)
            if result.returncode:
                raise RuntimeError(
                    f"Offline desktop execution failed: {cmd!r} (exit {result.returncode})\n"
                    f"stdout: {result.stdout[-1500:]}\nstderr: {result.stderr[-2000:]}"
                )
            print("PASS offline sockets blocked:", " ".join(cmd), flush=True)
        if not xvfb:
            print("NOTE: native GUI check skipped because xvfb-run was not available")
    print("PASS: desktop tests completed without a network connection")


if __name__ == "__main__":
    main()
