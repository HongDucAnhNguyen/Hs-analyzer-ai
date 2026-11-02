import json

from elasticsearch import Elasticsearch, helpers


def index_to_es(es: Elasticsearch, index_name: str, data_file: str):
    index_name = index_name.lower()

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"🗑️ Delete: {index_name}")

    es.indices.create(
        index=index_name,
        body={
            "mappings": {
                "properties": {
                    "hs_code":   {"type": "keyword"},
                    "chapter":   {"type": "keyword"},
                    "content":   {"type": "text"},
                    "keywords":  {"type": "keyword"},
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer"},
                            "chapter_meta": {"type": "keyword"},
                            "file_name": {"type": "keyword"},
                            "file_path": {"type": "keyword"},
                            "title": {"type": "text", "analyzer": "standard"},
                        },
                    },
                }
            }
        },
    )
    print(f"✅ create new: {index_name}")

    with open(data_file, "r", encoding="utf-8") as f:
        chapters = json.load(f)

    actions = []
    for chapter in chapters:
        for entry in chapter.get("extract_hscode", []):
            actions.append({
                "_index": index_name,
                "_id": entry["hs_code"],
                "_source": entry,
            })

    if actions:
        helpers.bulk(es, actions)
        print(
            f"📥 index {len(actions)} documents into Elasticsearch index: {index_name}")


if __name__ == "__main__":
    es = Elasticsearch(
    "http://34.126.88.217:9200",
    basic_auth=("elasticsearch", "elasticsearch"),
    headers={
        "Accept": "application/vnd.elasticsearch+json; compatible-with=8",
        "Content-Type": "application/vnd.elasticsearch+json; compatible-with=8",
    },
)

    index_to_es(es, "hscode", "./hs_code.json")
