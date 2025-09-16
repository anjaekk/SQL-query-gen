import os
import json
import re
from collections import defaultdict


# -------------------------------
# DDL을 JSON으로 변환
# -------------------------------
def parse_ddl(sql_text):
    tables = defaultdict(lambda: {
        "columns": [],
        "column_comments": [],
        "table_comment": "",
        "schema_text": ""
    })

    # --- CREATE TABLE 블록 추출 ---
    create_table_blocks = re.findall(
        r'CREATE TABLE\s+"?[\w]+"?\."?([\w]+)"?\s*\((.*?)\)\s*(?:SEGMENT|PCTFREE|TABLESPACE|;)',
        sql_text, re.S | re.I
    )

    for table_name, columns_block in create_table_blocks:
        column_lines = [line.strip() for line in columns_block.splitlines() if line.strip()]
        for col in column_lines:
            if col.upper().startswith(("CONSTRAINT", "PRIMARY", "FOREIGN")):
                continue
            match = re.match(r'"?([\w]+)"?\s+([A-Z0-9\(\)\s,_]+)', col, re.I)
            if match:
                col_name = match.group(1)
                col_type = match.group(2).strip().rstrip(",")
                tables[table_name]["columns"].append(col_name)
                tables[table_name]["column_comments"].append("")  # 나중에 채움

    # --- COMMENT ON TABLE ---
    table_comments = re.findall(
        r'COMMENT ON TABLE\s+[\w]+\."?([\w]+)"?\s+IS\s+\'([^\']*)\'',
        sql_text, re.I
    )
    for table_name, comment in table_comments:
        tables[table_name]["table_comment"] = comment

    # --- COMMENT ON COLUMN ---
    column_comments = re.findall(
        r'COMMENT ON COLUMN\s+[\w]+\."?([\w]+)"?\."?([\w]+)"?\s+IS\s+\'([^\']*)\'',
        sql_text, re.I
    )
    for table_name, column_name, comment in column_comments:
        if table_name in tables:
            try:
                idx = tables[table_name]["columns"].index(column_name)
                tables[table_name]["column_comments"][idx] = comment
            except ValueError:
                pass

    # --- schema_text 생성 ---
    for table_name, meta in tables.items():
        text = f"Table: {table_name}\n{meta['table_comment']}\n"
        for col_name, col_comment in zip(meta["columns"], meta["column_comments"]):
            text += f"- {col_name} : {col_comment}\n"
        tables[table_name]["schema_text"] = text

    return tables


def ddl_to_json(sql_file, json_file):
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_text = f.read()
    schema = parse_ddl(sql_text)

    # Azure Search 업로드용 JSON 리스트 형태로 변환
    json_list = []
    for table_name, meta in schema.items():
        json_list.append({
            "id": table_name,
            "table_name": table_name,
            "table_comment": meta["table_comment"],
            "columns": meta["columns"],
            "column_comments": meta["column_comments"],
            "schema_text": meta["schema_text"]
        })

    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(json_list, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON 변환 완료: {json_file}")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sql_path = os.path.join(script_dir, r"C:\Users\User\anjaekk\MVP\schema.sql")
    json_path = os.path.join(script_dir, r"C:\Users\User\anjaekk\MVP\schema.json")
    print(f"📂 읽는 파일: {sql_path}")
    ddl_to_json(sql_path, json_path)