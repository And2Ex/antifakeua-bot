from database.db import check_database_connection, init_db


def main() -> None:
    init_db()
    connection_info = check_database_connection()
    print("OK: connected to PostgreSQL.")
    print(f"Database: {connection_info['database_name']}")
    print(f"Server: {connection_info['version'].split(',')[0]}")


if __name__ == "__main__":
    main()
