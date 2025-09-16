import os
from dotenv import load_dotenv
from openai import AzureOpenAI

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential

import streamlit as st


load_dotenv()
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_DEPLOYMENT_MODEL = os.getenv("OPENAI_EMBEDDING_DEPLOYMENT_NAME")

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_API_KEY = os.getenv("AZURE_SEARCH_KEY")
AZURE_INDEX_NAME = os.getenv("INDEX_NAME")


openai_client = AzureOpenAI(
    api_version="2024-12-01-preview",
    api_key=AZURE_OPENAI_KEY, 
    azure_endpoint=AZURE_OPENAI_ENDPOINT)


search_client = SearchClient(
    endpoint=AZURE_SEARCH_ENDPOINT,
    index_name=AZURE_INDEX_NAME,
    credential=AzureKeyCredential(AZURE_SEARCH_API_KEY)
)

# -------------------------------
# 벡터 임베딩 생성 함수
# -------------------------------
def get_embedding(text: str):
    resp = openai_client.embeddings.create(
        model=AZURE_DEPLOYMENT_MODEL,
        input=text
    )
    return resp.data[0].embedding

# -------------------------------
# RAG 기반 SQL 생성 함수
# -------------------------------
def generate_sql_from_rag(user_input: str, top_k: int = 3) -> str:
    # 1. 쿼리 임베딩 생성
    query_vector = get_embedding(user_input)
    
    # 2. Azure Search 벡터 검색
    vector_query = VectorizedQuery(
            vector=query_vector,
            k_nearest_neighbors=5,
            fields="embedding",
            kind="vector",
            exhaustive=True
        )
    
    results = search_client.search(vector_queries=[vector_query])
    
    # 3. 검색된 테이블 구조 합치기
    retrieved_context = " ".join([doc["schema_text"] for doc in results])

    # 4. LLM에 SQL 생성 요청
    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "당신은 SQL 쿼리 생성 전문가입니다."},
            {"role": "user", "content": f"사용자 요청: {user_input}\n테이블 구조:\n{retrieved_context}\nSQL 쿼리:"}
        ],
        temperature=0,
        top_p=1,
        max_tokens=300
    )
    sql_query = response.choices[0].message.content
    return sql_query.strip()



# -------------------------------
# Streamlit Chat UI
# -------------------------------
st.title("🗨️ RAG 기반 SQL 생성기")

# 세션 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 이전 대화 보여주기
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.code(msg["content"], language="sql")
        else:
            st.markdown(msg["content"])

# 사용자 입력 (채팅 입력창)
if prompt := st.chat_input("SQL 요청을 입력하세요 (예: 계약번호로 계약일자 검색)"):
    # 사용자 메시지 추가
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 대기 UI 자리 표시자 생성
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown(
            """
            <div style="text-align:center; padding: 20px;">
                <img src="https://i.gifer.com/YCZH.gif" width="200">  <!-- 크기 키움 -->
                <p style="font-size:18px;">쿼리 생성 중... 잠시만 기다려 주세요 🐱‍💻</p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # 실제 쿼리 생성
    sql = generate_sql_from_rag(prompt)

    # 대기 UI 제거하고 최종 SQL 표시
    placeholder.code(sql, language="sql")

    # 세션에 최종 SQL 업데이트
    st.session_state.messages.append({"role": "assistant", "content": sql})