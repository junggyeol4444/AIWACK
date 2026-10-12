"""Entry point for python -m desktop.entry and the bundled AIWACK.exe."""
import sys


def self_test() -> int:
    """Real SQLite write/read/reopen without altering a user's data directory."""
    from pathlib import Path
    import tempfile
    from desktop.storage import LocalStore

    with tempfile.TemporaryDirectory(prefix="aiwack-exe-check-") as directory:
        path = Path(directory) / "test.sqlite3"
        LocalStore(path).save_note("desktop-startup-ok")
        if LocalStore(path).read_note() != "desktop-startup-ok":
            return 1
        if LocalStore(path).health()["status"] != "ok":
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
