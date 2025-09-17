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


def table_to_text(table):
    """검색된 테이블 데이터를 텍스트로 변환"""
    col_info = "\n".join([
        f"- {c['name']} ({c.get('type','')}, nullable={c.get('nullable')}, default={c.get('default')}, comment={c.get('comment')})"
        if isinstance(c, dict) else f"- {c}"
        for c in table.get("columns", [])
    ])
    return f"테이블명: {table.get('table_name','')}\n컬럼 정보:\n{col_info}\n설명: {table.get('schema_text','')}"


def get_embedding(text: str):
    """벡터 임베딩 생성"""
    resp = openai_client.embeddings.create(
        model=AZURE_DEPLOYMENT_MODEL,
        input=text
    )
    return resp.data[0].embedding


def generate_sql_from_rag(user_input: str, top_k: int = 3):
    """RAG 기반 SQL 생성 함수"""
    query_vector = get_embedding(user_input)
    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=top_k,
        fields="embedding",
        kind="vector",
        exhaustive=True
    )

    results = search_client.search(vector_queries=[vector_query])
    results_list = list(results)
    st.session_state.retrieved_tables = results_list  # 세션에 저장
    st.session_state.retrieved_context = "\n\n".join([table_to_text(doc) for doc in results_list])
    retrieved_context = "\n\n".join([table_to_text(doc) for doc in results_list])

    # 사이드바 테이블 정보 업데이트
    st.session_state.retrieved_context = retrieved_context

    response = openai_client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 SQL 쿼리 생성 전문가입니다. "
                    "사용자가 요청한 정보를 가장 정확하게 조회할 수 있는 쿼리를 작성하고, "
                    "필요하면 여러 테이블을 조인해서 결과를 반환하세요."
                )
            },
            {
                "role": "user",
                "content": (
                    f"사용자 요청: {user_input}\n\n"
                    f"테이블 구조:\n{retrieved_context}\n\n"
                    "지침:\n"
                    "- 요청한 컬럼이 있는 테이블을 우선 선택\n"
                    "- 필요한 경우 다른 관련 테이블과 조인\n"
                    "- 실제 테이블 이름과 컬럼명을 사용\n"
                    "- 쿼리를 삽입, 수정, 삭제할 때는 테이블의 조건에 맞춰서 생성\n"
                    "SQL 쿼리를 작성하세요:"
                )
            }
        ],
        temperature=0,
        top_p=1
    )
    return response.choices[0].message.content.strip()


def search_table_by_name(table_name_input):
    """
    세션에 저장된 retrieved_context(검색된 테이블 리스트)를 기반으로
    테이블명을 검색하고 컬럼/코멘트 정보를 반환
    """
    if "retrieved_context" not in st.session_state or not st.session_state.retrieved_context:
        return []

    # retrieved_context가 텍스트라면, 원래 테이블 리스트를 세션에 저장해두는 게 좋음
    tables = st.session_state.retrieved_tables  # 리스트 형태로 저장되어 있어야 함
    filtered = [t for t in tables if table_name_input.lower() in t.get("table_name", "").lower()]
    return filtered


# -------------------------------
# Streamlit 초기화
# -------------------------------
st.set_page_config(layout="wide")
st.title("🗨️ RAG 기반 SQL 생성기")

st.markdown(
    """
    <div style="
        background-color: #f0f0f0; 
        padding: 15px; 
        border-radius: 8px; 
        font-size: 0.9rem; 
        color: #555;
        line-height: 1.4;
    ">
    <strong>사용법 안내:</strong><br>
    - SQL 쿼리를 생성하고 싶으면 자연어로 요청을 입력하세요.<br>
    - 예시: <em>계약번호로 계약명 조회</em>, <em>진행 상태가 완료인 계약 조회</em><br>
    - 시스템이 가장 관련 있는 테이블을 찾아 적절한 SQL 쿼리를 생성합니다.
    </div>
    """,
    unsafe_allow_html=True
)


if "messages" not in st.session_state:
    st.session_state.messages = []
if "retrieved_context" not in st.session_state:
    st.session_state.retrieved_context = ""
if "retrieved_tables" not in st.session_state:
    st.session_state.retrieved_tables = []  


# -------------------------------
# 사이드바: 테이블 검색
# -------------------------------
st.sidebar.header("테이블 검색")

# 테이블명 입력
table_name_input = st.sidebar.text_input("조회할 테이블명 입력").replace(" ", "")

# 컬럼명 입력 (작게)
column_name_input = st.sidebar.text_input("조회할 컬럼명 입력", max_chars=30).replace(" ", "")

if table_name_input:
    try:
        table_docs = search_table_by_name(table_name_input)

        if table_docs:
            st.sidebar.markdown("### 검색 결과")

            for doc in table_docs:
                columns = doc.get("columns", [])
                comments = doc.get("column_comments", [])

                # 컬럼명 입력이 있으면 필터링
                if column_name_input:
                    filtered_columns = [
                        (col, comment) for col, comment in zip(columns, comments)
                        if column_name_input.lower() in col.lower()
                    ]
                else:
                    filtered_columns = list(zip(columns, comments))

                st.sidebar.markdown(f"**테이블명:** {doc['table_name']}")
                st.sidebar.markdown(f"**설명:** {doc.get('table_comment', '')}")

                if filtered_columns:
                    st.sidebar.markdown("**컬럼 정보:**")
                    table_data = [{"컬럼명": col, "코멘트": comment} for col, comment in filtered_columns]
                    st.sidebar.dataframe(table_data, height=min(400, 30*len(table_data)))
                else:
                    st.sidebar.info("검색된 컬럼이 없습니다.")
        else:
            st.sidebar.info("검색 결과가 없습니다.")

    except Exception as e:
        st.sidebar.error(f"테이블 조회 실패: {e}")
        

# -------------------------------
# 메인 UI: 채팅 SQL 생성
# -------------------------------
# 이전 대화 보여주기
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.code(msg["content"], language="sql")
        else:
            st.markdown(msg["content"])

# 사용자 입력
if prompt := st.chat_input("SQL 요청을 입력하세요 (예: 계약번호로 계약일자 검색)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 대기 UI
    with st.chat_message("assistant"):
        placeholder = st.empty()
        with placeholder.container():
            st.markdown(
                """
                <div style="
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    padding: 20px;
                    border-radius: 10px;
                    background-color: #f0f2f6;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                ">
                    <div class="loader" style="margin-bottom: 15px;"></div>
                    <p style="font-size:18px; color:#333;">쿼리 생성 중... 잠시만 기다려 주세요 🐱‍💻</p>
                </div>
                <style>
                    .loader {
                        border: 6px solid #f3f3f3;
                        border-top: 6px solid #3498db;
                        border-radius: 50%;
                        width: 50px;
                        height: 50px;
                        animation: spin 1s linear infinite;
                    }
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
                """,
                unsafe_allow_html=True
            )

    # SQL 생성
    sql = generate_sql_from_rag(prompt)

    # 대기 UI 제거 및 결과 표시
    placeholder.code(sql, language="sql")
    st.session_state.messages.append({"role": "assistant", "content": sql})