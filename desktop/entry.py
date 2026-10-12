"""Entry point for python -m desktop.entry and bundled Windows AIWACK.exe."""
import sys


def self_test() -> int:
    """Real offline authentication, note persistence, and reopen using a disposable DB."""
    from pathlib import Path
    import tempfile
    from desktop.storage import AuthenticationError, LocalStore

    with tempfile.TemporaryDirectory(prefix="aiwack-exe-check-") as directory:
        path = Path(directory) / "test.sqlite3"
        instance = LocalStore(path)
        try:
            instance.read_note()
            return 1  # Fail closed without a session.
        except AuthenticationError:
            pass
        instance.setup_owner("exe_tester", "test-password-long-2026")
        instance.save_note("desktop-startup-ok")
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.read_note()
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_note() != "desktop-startup-ok":
            return 1
        if instance.health()["status"] != "ok":
            return 1
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    from desktop.app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
