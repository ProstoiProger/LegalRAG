
import json, sys, urllib.error, urllib.request, time, os
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer

DATA_PATH = Path('/data/chunked_all_docs_structured_fixed.json')
QDRANT_URL='http://qdrant:6333'
ELASTICSEARCH_URL='http://elasticsearch:9200'
COLLECTION_NAME='dense_structured_bge_m3_v1'
ES_INDEX='bm25'
BATCH_SIZE=4
MAX_ITEMS=int(os.environ.get('MAX_ITEMS','0') or '0')

def log(msg): print(time.strftime('%H:%M:%S'), msg, flush=True)

def es_request(method,path,body=None,content_type='application/json'):
    data=None; headers={}
    if body is not None:
        data=(json.dumps(body,ensure_ascii=False).encode() if isinstance(body,(dict,list)) else (body.encode() if isinstance(body,str) else body))
        headers['Content-Type']=content_type
    req=urllib.request.Request(f'{ELASTICSEARCH_URL}{path}',data=data,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,timeout=120) as resp: return resp.status, resp.read()
    except urllib.error.HTTPError as exc: return exc.code, exc.read()

def iter_json_array(path):
    decoder=json.JSONDecoder()
    with path.open('r',encoding='utf-8') as f:
        buf=''; eof=False; nread=0
        while True:
            if not eof:
                chunk=f.read(1024*1024)
                if chunk:
                    buf += chunk; nread += len(chunk)
                else: eof=True
            buf=buf.lstrip()
            if buf.startswith('['): buf=buf[1:]; continue
            if buf.startswith(','): buf=buf[1:]; continue
            if buf.startswith(']') or (not buf and eof): return
            try:
                obj,idx=decoder.raw_decode(buf)
            except json.JSONDecodeError:
                if eof: raise
                if len(buf) > 50*1024*1024:
                    raise RuntimeError(f'JSON object too large/incomplete, buffer={len(buf)}, read={nread}')
                continue
            yield obj
            buf=buf[idx:]

def ensure_es():
    log('ensure ES index')
    status,_=es_request('HEAD',f'/{ES_INDEX}')
    if status==200: es_request('DELETE',f'/{ES_INDEX}')
    status,body=es_request('PUT',f'/{ES_INDEX}',{'mappings':{'properties':{'doc_id':{'type':'keyword'},'chunk_id':{'type':'integer'},'date':{'type':'keyword'},'section_title':{'type':'keyword'},'source':{'type':'keyword'},'text':{'type':'text'}}}})
    if status not in (200,201): raise RuntimeError(f'ES create failed {status} {body[:300]!r}')

def bulk_es(actions):
    lines=[]
    for a in actions:
        lines.append(json.dumps({'index':{'_index':ES_INDEX,'_id':a['_id']}},ensure_ascii=False))
        lines.append(json.dumps(a['_source'],ensure_ascii=False))
    status,resp=es_request('POST','/_bulk',body='\n'.join(lines)+'\n',content_type='application/x-ndjson')
    if status not in (200,201): raise RuntimeError(f'ES bulk failed {status} {resp[:300]!r}')
    parsed=json.loads(resp)
    if parsed.get('errors'): raise RuntimeError(f'ES bulk item errors {resp[:500]!r}')

def flush(model,q,batch,start_id):
    log(f'encode batch start start_id={start_id} size={len(batch)}')
    texts=[f"passage: {it.get('text','')}" for it in batch]
    vectors=model.encode(texts,normalize_embeddings=True,batch_size=len(batch),show_progress_bar=False)
    log(f'encode batch done start_id={start_id}')
    pts=[]; acts=[]
    for off,(item,vec) in enumerate(zip(batch,vectors)):
        pid=start_id+off
        payload={k:item.get(k) for k in ('doc_id','chunk_id','date','section_title','source')}
        payload['text']=item.get('text','')
        pts.append(PointStruct(id=pid,vector=vec.tolist(),payload=payload))
        acts.append({'_id': str(pid), '_source': payload})
    q.upsert(collection_name=COLLECTION_NAME,points=pts)
    bulk_es(acts)
    return len(batch)

def main():
    log(f'start file_exists={DATA_PATH.exists()} size={DATA_PATH.stat().st_size if DATA_PATH.exists() else None}')
    log('connect qdrant')
    q=QdrantClient(url=QDRANT_URL,timeout=120,check_compatibility=False)
    log('load model start')
    model=SentenceTransformer('BAAI/bge-m3')
    model.max_seq_length=1024
    log(f'load model done dim={model.get_sentence_embedding_dimension()}')
    ensure_es()
    log('recreate qdrant collection')
    q.recreate_collection(collection_name=COLLECTION_NAME,vectors_config=VectorParams(size=model.get_sentence_embedding_dimension(),distance=Distance.COSINE))
    log('iterate json start')
    batch=[]; total=0; seen=0
    for item in iter_json_array(DATA_PATH):
        seen += 1
        if seen <= 3: log(f'first_items_seen={seen} keys={sorted(item.keys()) if isinstance(item,dict) else type(item).__name__}')
        if not isinstance(item,dict) or not item.get('text'): continue
        batch.append(item)
        if len(batch)>=BATCH_SIZE:
            total += flush(model,q,batch,total); batch=[]
            log(f'indexed {total} seen {seen}')
            if MAX_ITEMS and total>=MAX_ITEMS: break
    if batch and not (MAX_ITEMS and total>=MAX_ITEMS):
        total += flush(model,q,batch,total); log(f'indexed {total} seen {seen}')
    es_request('POST',f'/{ES_INDEX}/_refresh')
    log(f'done {total} seen {seen}')
if __name__=='__main__': main()
