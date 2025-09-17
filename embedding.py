import os
import json
import time
from dotenv import load_dotenv
from openai import AzureOpenAI

from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError, ClientAuthenticationError
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents import SearchClient
from azure.search.documents.indexes.models import (
    SimpleField,
    ComplexField,
    SearchIndex,
    SearchFieldDataType,
    SearchableField,
    SearchField,
    VectorSearch,
    VectorSearchProfile,
    HnswAlgorithmConfiguration,
    ExhaustiveKnnAlgorithmConfiguration
)

load_dotenv()
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_MODEL = os.getenv("OPENAI_EMBEDDING_DEPLOYMENT_NAME")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_INDEX_NAME = os.getenv("INDEX_NAME")
VECTOR_SEARCH_PROFILE = os.getenv("VECTOR_SEARCH_PROFILE")

SCHEMA_JSON_PATH = r"C:\Users\User\anjaekk\MVP\schema2.json"


openai_client = AzureOpenAI(
    api_version="2024-12-01-preview",
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_key=AZURE_OPENAI_KEY
)


search_credential = AzureKeyCredential(AZURE_SEARCH_API_KEY)
search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_INDEX_NAME,
    credential=search_credential
)
index_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=search_credential)


# -------------------------------
# Azure Search 인덱스 생성 (벡터 포함)
# -------------------------------
fields = [
    SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
    SearchableField(name="table_name", type=SearchFieldDataType.String, filterable=True, sortable=True),
    SearchableField(name="table_comment", type=SearchFieldDataType.String),
    SearchField(name="columns", type=SearchFieldDataType.Collection(SearchFieldDataType.String), searchable=True),
    SearchField(name="column_comments", type=SearchFieldDataType.Collection(SearchFieldDataType.String), searchable=True),
    SearchableField(name="schema_text", type=SearchFieldDataType.String),
    SearchField(
        name="embedding",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True,
        vector_search_dimensions=3072,
        vector_search_profile_name=VECTOR_SEARCH_PROFILE
    )
]

vector_search = VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(name="my-hnsw-vector-config", kind="hnsw"),
        ExhaustiveKnnAlgorithmConfiguration(name="my-eknn-vector-config", kind="exhaustiveKnn")
    ],
    profiles=[
        VectorSearchProfile(name=VECTOR_SEARCH_PROFILE, algorithm_configuration_name="my-hnsw-vector-config")
    ]
)

index = SearchIndex(name=AZURE_INDEX_NAME, fields=fields, vector_search=vector_search)
try:
    index_client.create_or_update_index(index)
    print(f"✅ Index '{AZURE_INDEX_NAME}' created or updated.")
except Exception as e:
    print(f"⚠️ Index creation skipped or failed: {e}")


# -------------------------------
# JSON 읽기
# -------------------------------
with open(SCHEMA_JSON_PATH, "r", encoding="utf-8") as f:
    tables = json.load(f)

documents = []
for table in tables:
    schema = table.get("schema", "")
    table_name = table.get("table_name", "")
    table_comment = table.get("table_comment", "") or ""

    # 컬럼 메타데이터 생성
    column_lines = []
    column_comments = []
    for col in table.get("columns", []):
        col_name = col.get("name", "")
        col_type = col.get("type", "")
        nullable = "NOT NULL" if col.get("nullable") is False else "NULL"
        default = f"DEFAULT {col.get('default')}" if col.get("default") else ""
        comment = col.get("comment") or ""

        column_lines.append(f"- {col_name} {col_type} {nullable} {default} -- {comment}")
        if comment:
            column_comments.append(comment)

    # PK/인덱스 문자열
    pk_str = ", ".join(table.get("primary_key", []))
    index_lines = []
    for idx in table.get("indexes", []):
        idx_cols = ", ".join(idx.get("columns", []))
        index_lines.append(f"- {idx.get('name')} ({idx_cols})")

    # schema_text 구성
    schema_text = f"""
        Schema: {schema}
        Table: {table_name}
        Comment: {table_comment}

        Columns:
        {chr(10).join(column_lines)}

        Primary Key:
        {pk_str if pk_str else "(없음)"}

        Indexes:
        {chr(10).join(index_lines) if index_lines else "(없음)"}
    """.strip()

    # 임베딩 생성
    try:
        emb_response = openai_client.embeddings.create(
            model=AZURE_DEPLOYMENT_MODEL,
            input=schema_text
        )
        vector = emb_response.data[0].embedding
    except Exception as e:
        print(f"❌ Embedding failed for {schema}.{table_name}: {e}")
        continue

    # 문서 생성
    doc = {
        "id": f"{schema}_{table_name}",
        "table_name": table_name,
        "table_comment": table_comment,
        "columns": [c.get("name", "") for c in table.get("columns", [])],
        "column_comments": column_comments,
        "schema_text": schema_text,
        "embedding": vector
    }
    documents.append(doc)


# -------------------------------
# 업로드
# -------------------------------
def chunk_list(lst, chunk_size=50):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

for batch in chunk_list(documents, 50):
    try:
        result = search_client.upload_documents(documents=batch)
        for r in result:
            if not r.succeeded:
                print(f"❌ Failed: {r.key}, Error: {r.error_message}")
        print(f"✅ Uploaded batch of {len(batch)} documents.")
        time.sleep(1)
    except Exception as e:
        print(f"❌ Batch upload failed: {e}")