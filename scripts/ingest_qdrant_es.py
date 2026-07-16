import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


DATA_PATH = Path("/data/chunked_all_docs_structured_fixed.json")
QDRANT_URL = "http://qdrant:6333"
ELASTICSEARCH_URL = "http://elasticsearch:9200"
COLLECTION_NAME = "dense_structured_bge_m3_v1"
ES_INDEX = "bm25"
BATCH_SIZE = 32


def es_request(method: str, path: str, body=None, content_type="application/json"):
    data = None
    headers = {}
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            data = body.encode("utf-8")
        else:
            data = body
        headers["Content-Type"] = content_type
    req = urllib.request.Request(
        f"{ELASTICSEARCH_URL}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def iter_json_array(path: Path):
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        buf = ""
        eof = False
        while True:
            if not eof:
                chunk = f.read(1024 * 1024)
                if chunk:
                    buf += chunk
                else:
                    eof = True

            buf = buf.lstrip()
            if buf.startswith("["):
                buf = buf[1:]
                continue
            if buf.startswith(","):
                buf = buf[1:]
                continue
            if buf.startswith("]"):
                return
            if not buf and eof:
                return

            try:
                obj, idx = decoder.raw_decode(buf)
            except json.JSONDecodeError:
                if eof:
                    raise
                continue
            yield obj
            buf = buf[idx:]


def ensure_es():
    status, _ = es_request("HEAD", f"/{ES_INDEX}")
    if status == 200:
        es_request("DELETE", f"/{ES_INDEX}")
    status, body = es_request(
        "PUT",
        f"/{ES_INDEX}",
        {
            "mappings": {
            "properties": {
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "integer"},
                "date": {"type": "keyword"},
                "section_title": {"type": "keyword"},
                "source": {"type": "keyword"},
                "text": {"type": "text"},
            }
            }
        },
    )
    if status not in (200, 201):
        raise RuntimeError(f"Failed to create ES index: {status} {body[:500]!r}")


def bulk_es(actions):
    lines = []
    for action in actions:
        lines.append(json.dumps({"index": {"_index": ES_INDEX, "_id": action["_id"]}}, ensure_ascii=False))
        lines.append(json.dumps(action["_source"], ensure_ascii=False))
    body = "\n".join(lines) + "\n"
    status, resp = es_request(
        "POST", "/_bulk", body=body, content_type="application/x-ndjson"
    )
    if status not in (200, 201):
        raise RuntimeError(f"ES bulk failed: {status} {resp[:500]!r}")
    parsed = json.loads(resp)
    if parsed.get("errors"):
        raise RuntimeError(f"ES bulk item errors: {resp[:1000]!r}")


def flush_batch(model, qdrant, batch, start_id):
    texts = [f"passage: {item.get('text', '')}" for item in batch]
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=BATCH_SIZE)
    points = []
    es_actions = []
    for offset, (item, vector) in enumerate(zip(batch, vectors)):
        point_id = start_id + offset
        payload = {
            "doc_id": item.get("doc_id"),
            "chunk_id": item.get("chunk_id"),
            "date": item.get("date"),
            "section_title": item.get("section_title"),
            "source": item.get("source"),
            "text": item.get("text", ""),
        }
        points.append(
            PointStruct(id=point_id, vector=vector.tolist(), payload=payload)
        )
        es_actions.append(
            {
                "_id": f"{payload['doc_id']}||{payload['chunk_id']}",
                "_source": payload,
            }
        )
    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    bulk_es(es_actions)
    return len(batch)


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"Data file not found: {DATA_PATH}")

    qdrant = QdrantClient(url=QDRANT_URL, timeout=120)
    model = SentenceTransformer("BAAI/bge-m3")
    vector_size = model.get_sentence_embedding_dimension()

    ensure_es()
    qdrant.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    batch = []
    total = 0
    for item in iter_json_array(DATA_PATH):
        text = item.get("text")
        if not text:
            continue
        batch.append(item)
        if len(batch) >= BATCH_SIZE:
            total += flush_batch(model, qdrant, batch, total)
            print(f"indexed {total}", flush=True)
            batch = []

    if batch:
        total += flush_batch(model, qdrant, batch, total)
        print(f"indexed {total}", flush=True)

    es_request("POST", f"/{ES_INDEX}/_refresh")
    print(f"done {total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
