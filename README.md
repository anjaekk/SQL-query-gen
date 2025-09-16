# SQL-query-gen
# 🗨️ RAG 기반 SQL 쿼리 생성기
**Azure Cognitive Search**와 **Azure OpenAI**를 활용하여  
자연어 요청을 SQL 쿼리로 변환해주는 RAG 기반 SQL Query Generator입니다.  
Azure Web App을 통해 배포했으며, Streamlit을 통해 웹 UI로 손쉽게 테스트할 수 있습니다.
</br>

## 📌 주요 기능
- **자연어 → SQL 쿼리 변환**  
  사용자가 입력한 요청을 이해하고 적절한 SQL 쿼리를 생성
- **RAG 기반 검색**  
  Azure Cognitive Search를 이용해 사전에 업로드한 테이블 스키마를 검색하여 정확한 쿼리를 생성
- **Streamlit 웹 UI 지원**  
  대화형 화면에서 바로 SQL 생성 결과를 확인 가능
- **대화 세션 기억**  
  이전 대화 맥락을 반영하여 쿼리를 점점 더 개선


## 📌 작업 내용

1. **DB에서 DDL 스키마 정보 추출**  
   - 데이터베이스 테이블, 컬럼, 데이터 타입, 제약조건 등 메타데이터를 DDL 형태로 추출  
   - COLUMN COMMENTS도 함께 추출해 컬럼 의미 확보

2. **스키마 정보를 JSON으로 변환**  
   - 추출한 DDL을 Python 스크립트로 파싱하여 JSON 포맷으로 변환  
   - 각 테이블별로 `table_name`, `columns`, `data_type`, `description` 필드를 포함  
   - 예시:
     ```json
     {
       "table_name": "테이블명",
       "columns": [
         {"name": "CNTR_NO", "type": "VARCHAR(20)", "description": "계약번호"},
         {"name": "CNTR_DATE", "type": "DATE", "description": "계약일"}
       ]
     }
     ```

3. **임베딩 생성 및 Azure Cognitive Search 업로드**  
   - Azure OpenAI `text-embedding-3-large` 모델을 사용하여 테이블 스키마를 벡터로 변환  
   - 생성한 Azure Cognitive Search 인덱스에 `schema_text` 필드와 함께 저장  
   - 벡터 검색이 가능하도록 인덱스 필드 차원(dimension)을 임베딩 모델 크기(3072)로 맞춤

4. **사용자 요청 → 벡터 검색 → 컨텍스트 생성**  
   - 사용자가 자연어로 요청 입력  
   - 입력 문장을 임베딩 후 Azure Cognitive Search에서 가장 유사한 테이블 스키마 검색  
   - 검색된 스키마를 LLM 컨텍스트로 전달

5. **LLM 기반 SQL 쿼리 생성**  
   - Azure OpenAI `gpt-4o-mini` 모델 사용  
   - RAG 결과 + 사용자 요청을 기반으로 SQL 쿼리 생성  
   - Streamlit UI에 SQL 결과 출력

6. **쿼리 실행 및 검증**  
   - 생성된 SQL을 테스트 DB에 실행하여 실제 결과 검증  
   - 쿼리의 정확성과 실행 가능 여부를 평가
