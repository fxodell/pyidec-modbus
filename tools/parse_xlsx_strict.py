#!/usr/bin/env python3
"""
Parse IDEC FC6A Modbus address map from 'strict' OOXML xlsx that openpyxl can't read.
Reads sheet XML directly to extract operand/address pairs.
"""

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

# Modbus reference ranges -> (table, 0-based offset)
def ref_to_table_offset(ref: int) -> tuple[str, int] | None:
    ref = int(ref)
    if 1 <= ref <= 99_999:
        return "coil", ref - 1
    if 100_001 <= ref <= 199_999:
        return "discrete_input", ref - 100_001
    if 300_001 <= ref <= 399_999:
        return "input_register", ref - 300_001
    if 400_001 <= ref <= 499_999:
        return "holding_register", ref - 400_001
    return None

OPERAND_RE = re.compile(r'^([DMIOCQRTS])(\d+)(\.(?:C|CV|PV))?$', re.IGNORECASE)
ADDRESS_RE = re.compile(r'^\d{5,6}$')

def get_col(ref: str) -> str:
    """Extract column letters from cell reference like 'A1' -> 'A'."""
    return ''.join(c for c in ref if c.isalpha())

def find_v_text(cell) -> str:
    """Find the <v> element text in a cell."""
    for child in cell:
        if child.tag.endswith('}v') or child.tag == 'v':
            return child.text or ''
    return ''

def find_cells(row):
    """Find all <c> elements in a row."""
    return [c for c in row.iter() if c.tag.endswith('}c') or c.tag == 'c']

def find_rows(root):
    """Find all <row> elements."""
    return [r for r in root.iter() if r.tag.endswith('}row') or r.tag == 'row']

def parse_sheet(sheet_xml: bytes, strings: list[str], sheet_name: str) -> list[dict]:
    """Parse a single sheet and return operand entries."""
    entries = []
    root = ET.fromstring(sheet_xml)
    
    operand_col = None
    address_col = None
    
    rows = find_rows(root)
    if not rows:
        return entries
    
    # Check first row for headers
    first_row = rows[0]
    for cell in find_cells(first_row):
        ref = cell.get('r', '')
        col = get_col(ref)
        t = cell.get('t')
        val = find_v_text(cell)
        if t == 's' and val:
            try:
                val = strings[int(val)]
            except (ValueError, IndexError):
                pass
        val_upper = (val or '').upper()
        
        if 'OPERAND' in val_upper or 'FC5A' in val_upper or 'FC6A' in val_upper:
            operand_col = col
        elif 'MODBUS' in val_upper and 'ADDRESS' in val_upper:
            address_col = col
    
    if operand_col is None:
        operand_col = 'A'
    if address_col is None:
        address_col = 'B'
    
    # Parse data rows
    for row in rows[1:]:
        row_data = {}
        for cell in find_cells(row):
            ref = cell.get('r', '')
            col = get_col(ref)
            t = cell.get('t')
            val = find_v_text(cell)
            if t == 's' and val:
                try:
                    val = strings[int(val)]
                except (ValueError, IndexError):
                    pass
            row_data[col] = val
        
        operand = row_data.get(operand_col, '').strip().upper()
        address = row_data.get(address_col, '').strip()
        
        if not operand or not address:
            continue
        
        m = OPERAND_RE.match(operand)
        if not m:
            continue
        
        if not ADDRESS_RE.match(address):
            continue
        
        ref = int(address)
        result = ref_to_table_offset(ref)
        if result is None:
            continue
        
        table, offset = result
        
        letter = m.group(1).upper()
        num = int(m.group(2))
        suffix = (m.group(3) or "").upper()
        
        if letter in ('T', 'C') and suffix:
            op = f"{letter}{num:04d}{suffix}"
        else:
            op = f"{letter}{num:04d}"
        
        width = 1 if table in ("coil", "discrete_input") else 16
        entries.append({
            "operand": op,
            "table": table,
            "offset": offset,
            "width": width,
            "meta": {"sheet": sheet_name},
        })
    
    return entries

def parse_timer_counter_sheet(sheet_xml: bytes, strings: list[str], sheet_name: str, prefix: str) -> list[dict]:
    """Parse Timer/Counter sheet with 3 blocks: Contact (.C), Current Value (.CV), Preset (.PV)."""
    entries = []
    root = ET.fromstring(sheet_xml)
    rows = find_rows(root)
    if not rows:
        return entries
    
    # Timer/Counter sheets have columns: A,B (.C), E,F (.CV), I,J (.PV)
    # Row 1 = section headers, Row 2 = column headers, data starts at row 3
    blocks = [
        ('A', 'B', '.C', 'discrete_input'),
        ('E', 'F', '.CV', 'input_register'),
        ('I', 'J', '.PV', 'holding_register'),
    ]
    
    for row in rows[2:]:  # Skip row 1 (section headers) and row 2 (column headers)
        row_data = {}
        for cell in find_cells(row):
            ref = cell.get('r', '')
            col = get_col(ref)
            t = cell.get('t')
            val = find_v_text(cell)
            if t == 's' and val:
                try:
                    val = strings[int(val)]
                except (ValueError, IndexError):
                    pass
            row_data[col] = val
        
        for op_col, addr_col, suffix, table in blocks:
            operand = row_data.get(op_col, '').strip().upper()
            address = row_data.get(addr_col, '').strip()
            
            if not operand or not address or not operand.startswith(prefix):
                continue
            
            m = OPERAND_RE.match(operand)
            if not m:
                continue
            
            if not ADDRESS_RE.match(address):
                continue
            
            ref = int(address)
            result = ref_to_table_offset(ref)
            if result is None:
                continue
            
            _, offset = result
            
            letter = m.group(1).upper()
            num = int(m.group(2))
            op = f"{letter}{num:04d}{suffix}"
            
            width = 1 if table == "discrete_input" else 16
            entries.append({
                "operand": op,
                "table": table,
                "offset": offset,
                "width": width,
                "meta": {"sheet": sheet_name},
            })
    
    return entries

def parse_xlsx(xlsx_path: str) -> list[dict]:
    """Parse all sheets and return combined operand entries."""
    entries = []
    seen = set()
    
    OOXML_NS = '{http://purl.oclc.org/ooxml/spreadsheetml/main}'
    OOXML_REL = '{http://purl.oclc.org/ooxml/officeDocument/relationships}'
    
    with zipfile.ZipFile(xlsx_path, 'r') as z:
        # Read shared strings
        ss_xml = z.read('xl/sharedStrings.xml')
        ss_root = ET.fromstring(ss_xml)
        strings = [t.text for t in ss_root.iter() if t.tag.endswith('}t') or t.tag == 't']
        
        # Read workbook to get sheet names
        wb_xml = z.read('xl/workbook.xml')
        wb_root = ET.fromstring(wb_xml)
        sheet_names = {}
        for elem in wb_root.iter():
            if elem.tag == f'{OOXML_NS}sheet':
                rid = elem.get(f'{OOXML_REL}id')
                name = elem.get('name')
                if rid and name:
                    sheet_names[rid] = name
        
        # Read relationships
        rels_xml = z.read('xl/_rels/workbook.xml.rels')
        rels_root = ET.fromstring(rels_xml)
        rid_to_file = {}
        for rel in rels_root.iter():
            if 'Relationship' in rel.tag:
                rid = rel.get('Id')
                target = rel.get('Target')
                if target and 'worksheets/' in target:
                    rid_to_file[rid] = target.split('/')[-1]
        
        print(f"  Found {len(sheet_names)} sheets, {len(strings)} shared strings")
        
        for rid, sheet_name in sheet_names.items():
            if rid not in rid_to_file:
                continue
            
            sheet_file = 'xl/worksheets/' + rid_to_file[rid]
            try:
                sheet_xml = z.read(sheet_file)
            except KeyError:
                continue
            
            print(f"  Processing sheet: {sheet_name}")
            
            if 'Timer' in sheet_name:
                sheet_entries = parse_timer_counter_sheet(sheet_xml, strings, sheet_name, 'T')
            elif 'Counter' in sheet_name:
                sheet_entries = parse_timer_counter_sheet(sheet_xml, strings, sheet_name, 'C')
            else:
                sheet_entries = parse_sheet(sheet_xml, strings, sheet_name)
            
            for e in sheet_entries:
                if e['operand'] not in seen:
                    seen.add(e['operand'])
                    entries.append(e)
            
            print(f"    -> {len(sheet_entries)} entries ({len(seen)} unique total)")
    
    return entries

def main():
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "data/FC6A_ModbusSlave_AddressMap_Xml.xlsx"
    if not Path(xlsx_path).exists():
        print(f"File not found: {xlsx_path}")
        return 1
    
    print(f"Parsing {xlsx_path}...")
    entries = parse_xlsx(xlsx_path)
    print(f"Found {len(entries)} unique operands")
    
    entries.sort(key=lambda e: e["operand"])
    
    out_path = Path(__file__).parent.parent / "src" / "pyidec_modbus" / "data" / "fc6a_tagmap.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w") as f:
        json.dump(entries, f, indent=2)
    
    print(f"Wrote {len(entries)} entries to {out_path}")
    
    tables = {}
    for e in entries:
        tables[e["table"]] = tables.get(e["table"], 0) + 1
    for t, c in sorted(tables.items()):
        print(f"  {t}: {c}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
