"""CLI entry point — deprecated, use `autocomputer.cli:app` directly."""

def main() -> None:
    from autocomputer.cli import main as _main
    _main()
