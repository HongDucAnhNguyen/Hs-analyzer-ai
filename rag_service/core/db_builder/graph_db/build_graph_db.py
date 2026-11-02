import json
from typing import Any, Optional
from neo4j import GraphDatabase

# ==========================
# Neo4j Connection
# ==========================
NEO4J_URI = "bolt://34.126.88.217:7687"   # change host if needed
NEO4J_USER = "neo4j"
NEO4J_PASS = "password"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))


# ==========================
# Utils
# ==========================
def to_int(x: Any) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


# ==========================
# Constraints / Cleanup
# ==========================
def ensure_constraints():
    with driver.session() as session:
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Chapter) REQUIRE c.id IS UNIQUE")
        session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (h:Hscode) REQUIRE h.hs_code IS UNIQUE")
    print("✅ Ensured constraints for Chapter.id and Hscode.hs_code")

def clear_graph():
    """Delete all nodes and relationships in the database."""
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    print("✅ Cleared the entire graph before rebuilding.")


# ==========================
# Create nodes & relationships
# ==========================
def create_chapter(tx, chapter_id):
    """Create or merge a Chapter node."""
    tx.run(
        """
        MERGE (c:Chapter {id:$id})
        """,
        id=chapter_id
    )


def create_hscode(
    tx,
    code: str,
    code_type: str,
    chapter_id: str,
    content: str,
    keywords,
    page: Optional[int],
    chapter_meta: Optional[str],
    file_name: Optional[str],
    file_path: Optional[str],
    title: Optional[str],
):
    """
    Tạo/MERGE nút :Hscode và gắn 1 dict metadata gồm 5 trường:
    page, chapter_meta, file_name, file_path, title.
    Đồng thời liên kết đến Chapter và liên kết subheading -> parent (4-digit) nếu là mã 6 số.
    """
    raw_code = code.replace(".", "")

    metadata = {
        "page": page,
        "chapter_meta": chapter_meta,
        "file_name": file_name,
        "file_path": file_path,
        "title": title,
    }

    # ✅ serialize sang chuỗi JSON
    metadata_json = json.dumps(metadata, ensure_ascii=False)

    tx.run(
        """
        MATCH (c:Chapter {id:$chapter_id})
        MERGE (h:Hscode {hs_code:$code})
        SET h.code_type = $code_type,
            h.content   = $content,
            h.keywords  = $keywords,
            h.metadata  = $metadata_json
        MERGE (c)-[:HAS_HSCODE]->(h)
        """,
        chapter_id=chapter_id,
        code=code,
        code_type=code_type,
        content=content,
        keywords=keywords,
        metadata_json=metadata_json,
    )
    # Nếu là subheading (6 digits), liên kết tới parent 4-digit
    if len(raw_code) == 6:
        tx.run(
            """
            MATCH (p:Hscode) WHERE replace(p.hs_code,".","") = $parent_code
            MATCH (s:Hscode {hs_code:$code})
            MERGE (p)-[:HAS_SUBHEADING]->(s)
            """,
            parent_code=raw_code[:4],
            code=code
        )

# ==========================
# Build the graph from JSON
# ==========================
def build_graph(data):
    """Build the Neo4j graph using the provided JSON data (list of chapters)."""
    with driver.session() as session:
        for chapter in data:
            chapter_id = chapter.get("chapter_number")
            if not chapter_id:
                continue
            session.execute_write(create_chapter, chapter_id)

            for item in chapter.get("extract_hscode", []) or []:
                hs_code = item.get("hs_code")
                if not hs_code:
                    continue

                session.execute_write(
                    create_hscode,
                    hs_code,
                    item.get("code_type", "hs-code_heading"),
                    chapter_id,
                    item.get("content", ""),
                    item.get("keywords", []),

                    # 5 metadata đã được bạn map sẵn vào hs_code.json
                    to_int(item.get("page")),
                    item.get("chapter"),
                    item.get("file_name"),
                    item.get("file_path"),
                    item.get("title"),
                )


# ==========================
# Main
# ==========================
if __name__ == "__main__":
    ensure_constraints()
    clear_graph()
    with open("./hs_code.json", "r", encoding="utf-8") as f:
        data = json.load(f)  

    build_graph(data)
    driver.close()

    print("✅ Graph build completed successfully.")
