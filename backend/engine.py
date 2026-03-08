import pandas as pd
from openai import OpenAI
from qdrant_client import QdrantClient
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    QDRANT_URL,
    QDRANT_API_KEY,
    ELASTICSEARCH_URL,
    ES_INDEX,
    COLLECTION_NAME,
    ALPHA,
)

RAG_SYSTEM_PROMPT = """
# Рөл және Мақсат
Сен — Қазақстан Республикасының заңнама нормаларына сәйкес ресми заңгерлік қорытындылар дайындайтын заңгер-көмекші чат-ботсың.
Сенің басты мақсатың: Өз бетіңнен ештеңе ойдан шығармау. Сен ТЕК берілген мәнмәтін (context) ішінен құқықтық нормаларды тауып, оларды белгіленген үлгі бойынша заңгерлік қорытынды ретінде ресімдейсің.

# Нұсқаулықтар
- ТЕК ҚАЗАҚ ТІЛІНДЕ жауап бер.
- Жауап беру стилі: Ресми, сыпайы және нақты.
- Тақырыпқа қатысы жоқ (құқықтық емес) сұрақтарға жауап БЕРМЕ.
- Жауап бермес бұрын ақпаратты мұқият зерделеп, талдау жүргіз.
- Егер мәнмәтінде жауап болмаса, "Берілген мәліметтерде бұл мәселені реттейтін нақты норма табылмады" деп ашық айт.

# Ойлау қадамдары (Reasoning steps)
1. Сұрақ пен оған тіркелген мәнмәтінді (контекст) мұқият оқып шық.
2. Сұраққа сәйкес келетін заңнамалық нормаларды мәнмәтін ішінен ізде.
3. Табылған нормаларды құрылымдық түрде, сауатты және ТЕК қазақ тілінде жүйеле.

# Жауап форматы (Міндетті шаблон)
Сенің жауабың келесі құрылымнан ауытқымауы тиіс:

---
📌 Жауап форматы:

Қайырлы күн!

Заңгерлік қызмет {сұрақтың қысқаша мәнін енгізу} мәселесіне қатысты келесіні хабарлайды:

{Нормативтік құқықтық актінің толық атауы, қабылданған күні мен нөмірі} сәйкес, {дәл қандай мәселе және қалай реттелетінін көрсет}.
Сілтеме жасап отырған баптан немесе тармақтан толық цитата келтір (өз сөзіңмен емес, заңның дәл мәтінін жаз).

Қолдану тәжірибесіне қатысты ескертулер болса — қосып жаз.
Егер мәселені шешудің балама жолдары болса — қысқаша сипатта.

Қорытындылай келе, қысқаша түйін мен ұсыныстар бер, мысалы:
«Осылайша, жеке басты куәландыратын құжатты рәсімдеу кезінде азамат есімнің жазылуын ұсынылған растаушы құжатқа сәйкес көрсетуге құқылы».

Құрметпен,
Орындаушы: Legal RAG Chatbot
---
"""

embed_model = SentenceTransformer("BAAI/bge-m3")
client = OpenAI(api_key=OPENAI_API_KEY)
q_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
es = Elasticsearch([ELASTICSEARCH_URL])


def retrieve_hybrid_context(question, top_k=10, alpha=None):
    alpha = alpha if alpha is not None else ALPHA
    sparse_body = {
        "size": top_k * 2,
        "_source": ["text", "doc_id", "chunk_id"],
        "query": {"match": {"text": {"query": question}}},
    }
    es_res = es.search(index=ES_INDEX, body=sparse_body)
    sparse_hits = [
        {
            "key": f"{h['_source'].get('doc_id')}||{h['_source'].get('chunk_id')}",
            "text": h["_source"].get("text"),
            "sparse_score": h["_score"],
        }
        for h in es_res.get("hits", {}).get("hits", [])
    ]

    query_vector = embed_model.encode(
        ["query: " + question], normalize_embeddings=True
    )[0].tolist()
    q_res = q_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k * 2,
    ).points
    dense_hits = [
        {
            "key": f"{hit.payload.get('doc_id')}||{hit.payload.get('chunk_id')}",
            "text": hit.payload.get("text"),
            "dense_score": hit.score,
        }
        for hit in q_res
    ]

    df_s, df_d = pd.DataFrame(sparse_hits), pd.DataFrame(dense_hits)
    if df_s.empty and df_d.empty:
        return ""
    df = pd.merge(df_s, df_d, on=["key", "text"], how="outer").fillna(0.0)

    for col in ["sparse_score", "dense_score"]:
        if df[col].max() > df[col].min():
            df[col + "_n"] = (df[col] - df[col].min()) / (
                df[col].max() - df[col].min() + 1e-9
            )
        else:
            df[col + "_n"] = 0.0

    df["final_score"] = (alpha * df["sparse_score_n"]) + (
        (1 - alpha) * df["dense_score_n"]
    )
    top_chunks = df.sort_values("final_score", ascending=False).head(top_k)

    return "\n\n---\n\n".join(top_chunks["text"].tolist())


def get_legal_answer(query: str, history: list[dict] | None = None):
    context = retrieve_hybrid_context(query)
    user_content = f"КОНТЕКСТ:\n{context}\n\nСҰРАҚ:\n{query}"

    messages = [{"role": "system", "content": RAG_SYSTEM_PROMPT}]
    if history:
        for msg in history[-10:]:  # last 10 turns
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content