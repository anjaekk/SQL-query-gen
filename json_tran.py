import re
import json
from pathlib import Path


def parse_all_tables(ddl_text: str):
    tables = []
    # CREATE TABLE 구문 기준으로 분리
    create_table_blocks = re.split(r"(?=CREATE\s+TABLE)", ddl_text, flags=re.IGNORECASE)
    for block in create_table_blocks:
        block = block.strip()
        if not block:
            continue
        if not block.upper().startswith("CREATE TABLE"):
            continue

        table_info = {}

        # 테이블명 추출
        table_match = re.search(r'CREATE\s+TABLE\s+"?([\w]+)"?\."?([\w]+)"?', block, re.IGNORECASE)
        if table_match:
            schema, table = table_match.groups()
            table_info["schema"] = schema
            table_info["table_name"] = table
        else:
            table_info["schema"] = None
            table_info["table_name"] = "UNKNOWN"

        # 테이블 코멘트
        table_comment_match = re.search(
            rf"COMMENT\s+ON\s+TABLE\s+{table_info['schema']}\.{table_info['table_name']}\s+IS\s+'([^']+)'",
            ddl_text,
            re.IGNORECASE,
        )
        table_info["table_comment"] = table_comment_match.group(1) if table_comment_match else None

        # 컬럼 섹션
        column_section_match = re.search(r"\(([\s\S]+?)\)\s*(SEGMENT|PCTFREE|TABLESPACE|;)", block)
        columns = []
        if column_section_match:
            columns_raw = column_section_match.group(1).splitlines()
            for line in columns_raw:
                line = line.strip().rstrip(",")
                if not line or line.upper().startswith(("CONSTRAINT", "PRIMARY KEY", "FOREIGN KEY")):
                    continue
                col_match = re.match(r'"?([\w]+)"?\s+([\w()]+)(.*)', line)
                if col_match:
                    col_name, col_type, rest = col_match.groups()
                    col_info = {
                        "name": col_name,
                        "type": col_type,
                        "nullable": "NOT NULL" not in rest.upper(),
                        "default": None,
                        "comment": None,
                    }
                    default_match = re.search(r"DEFAULT\s+([^ ,]+)", rest, re.IGNORECASE)
                    if default_match:
                        col_info["default"] = default_match.group(1)
                    columns.append(col_info)

        # 컬럼 코멘트
        for match in re.finditer(
            rf"COMMENT\s+ON\s+COLUMN\s+{table_info['schema']}\.{table_info['table_name']}\.(\w+)\s+IS\s+'([^']+)'",
            ddl_text,
            re.IGNORECASE,
        ):
            col, comment = match.groups()
            for c in columns:
                if c["name"].upper() == col.upper():
                    c["comment"] = comment

        table_info["columns"] = columns

        # PK
        pk_match = re.search(r"PRIMARY KEY\s*\(([^)]+)\)", block, re.IGNORECASE)
        if pk_match:
            pk_cols = [c.strip().strip('"').upper() for c in pk_match.group(1).split(",")]
            table_info["primary_key"] = pk_cols
        else:
            table_info["primary_key"] = []

        # 인덱스
        index_matches = re.findall(
            rf'CREATE\s+(?:UNIQUE\s+)?INDEX\s+"?{table_info["schema"]}"?\."?([\w]+)"?\s+ON\s+"?{table_info["schema"]}"?\."?{table_info["table_name"]}"?\s*\(([^)]+)\)',
            ddl_text,
            re.IGNORECASE,
        )
        indexes = []
        for idx_name, idx_cols in index_matches:
            idx_columns = [c.strip().strip('"') for c in idx_cols.split(",")]
            indexes.append({"name": idx_name, "columns": idx_columns})
        table_info["indexes"] = indexes

        tables.append(table_info)

    return tables


def ddl_folder_to_json(folder: str, output_file: str):
    ddl_files = list(Path(folder).glob("*.sql"))
    if not ddl_files:
        print(f"❌ {folder} 에 .sql 파일 없음")
        return

    all_tables = []
    for ddl_file in ddl_files:
        text = ddl_file.read_text(encoding="utf-8")
        parsed_tables = parse_all_tables(text)
        all_tables.extend(parsed_tables)
        print(f"✅ {ddl_file.name} → {len(parsed_tables)}개 테이블 변환")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_tables, f, ensure_ascii=False, indent=2)

    print(f"🎉 JSON 생성 완료 → {output_file}")


# 사용 예시
ddl_folder_to_json(r"C:\Users\User\anjaekk\MVP", r"C:\Users\User\anjaekk\MVP\schema2.json")