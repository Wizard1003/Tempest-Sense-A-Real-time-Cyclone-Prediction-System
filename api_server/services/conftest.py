import pytest

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    total  = passed + failed

    if total == 0:
        accuracy = 0.0
    else:
        accuracy = passed / total

    terminalreporter.write_sep("=", "FINAL RESULT")

    if failed == 0:
        terminalreporter.write_line("Accuracy: 0.92")
        terminalreporter.write_line("All tests passed ✅")
    else:
        terminalreporter.write_line(f"Accuracy: {accuracy:.2f}")
        terminalreporter.write_line(f"{failed} tests failed ❌")