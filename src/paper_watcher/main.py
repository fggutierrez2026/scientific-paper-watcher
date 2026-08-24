from paper_watcher.config import load_config

def ensure_directories() -> None:
    """
    Ensure that the necessary directories exist.
    """
    config = load_config()
    config.database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    config.report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

def main() -> None:
    """
    Main entry point for the application.
    """

    config = load_config()
    ensure_directories()

    print("Scientific Paper Watcher")
    print("-------------------------")
    print(f"Database Path: {config.database_path}")
    print(f"Report Directory: {config.report_dir}")
    print(f"Request timeout: {config.request_timeout} seconds")
    print(f"Max retries: {config.max_retries}")

if __name__ == "__main__":
    main()