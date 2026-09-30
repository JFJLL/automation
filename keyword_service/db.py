from core.database import KEYWORD_DB_PATH, get_keyword_db, run_migrations

DB_PATH = KEYWORD_DB_PATH

def get_db():
    return get_keyword_db()

def init_db():
    conn = get_db()
    run_migrations(conn, module="keyword")

if __name__ == "__main__":
    init_db()
    print("Keyword database initialized at", DB_PATH)

