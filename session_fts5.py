import argparse
import json
import os
import sqlite3
import sys

def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages USING fts5(
            step_index,
            role,
            content,
            tokenize = 'unicode61'
        );
    """)
    conn.commit()
    return conn

def index_jsonl(log_path: str, db_path: str):
    if not os.path.exists(log_path):
        print(f"Error: Log file not found: {log_path}", file=sys.stderr)
        return 0

    conn = init_db(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM messages;")

    count = 0
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                step = str(data.get("step_index", data.get("step", "")))
                role = data.get("source", data.get("role", "unknown"))
                content = data.get("content", "") or ""
                if content:
                    cur.execute("INSERT INTO messages (step_index, role, content) VALUES (?, ?, ?)", (step, role, content))
                    count += 1
            except Exception:
                continue

    conn.commit()
    conn.close()
    print(f"[FTS5] Successfully indexed {count} conversation steps into {db_path}")
    return count

def search_index(db_path: str, query: str, limit: int = 5):
    if not os.path.exists(db_path):
        print(f"Error: Index database not found: {db_path}", file=sys.stderr)
        return []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        sql = """
            SELECT step_index, role, snippet(messages, 2, '【', '】', '...', 15)
            FROM messages
            WHERE messages MATCH ?
            ORDER BY rank
            LIMIT ?;
        """
        rows = cur.execute(sql, (query, limit)).fetchall()
        return rows
    except Exception as e:
        print(f"Query error: {e}", file=sys.stderr)
        return []
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Agent Session SQLite FTS5 Full-Text Search Engine")
    parser.add_argument("--index", help="Path to conversation transcript.jsonl to index")
    parser.add_argument("--search", help="Search keyword or boolean FTS5 query")
    parser.add_argument("--db", default="session_fts5.db", help="Path to SQLite FTS5 database file")
    parser.add_argument("--limit", type=int, default=5, help="Maximum search results to return")

    args = parser.parse_args()

    if args.index:
        index_jsonl(args.index, args.db)

    if args.search:
        results = search_index(args.db, args.search, args.limit)
        print(f"\nSearch results for '{args.search}' (Total: {len(results)}):")
        print("=" * 60)
        for step, role, snippet in results:
            print(f"[Step {step}] ({role}):")
            print(f"  {snippet}\n")

if __name__ == "__main__":
    main()
