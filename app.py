from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from io import BytesIO
import os
import re
from difflib import SequenceMatcher
from docx import Document

app = Flask(__name__)
CORS(app)
load_dotenv()

# -------- Helpers --------
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def best_section_match(label, sections, threshold=0.5):
    best_key, best_score = None, threshold
    for key in sections:
        score = similar(label, key)
        if score > best_score:
            best_key = key
            best_score = score
    return best_key

def parse_lesson_content(text):
    pattern = r'\{\{(.*?)\}\}:(.*?)(?=\n\{\{|\Z)'
    return {k.strip().lower(): v.strip() for k, v in re.findall(pattern, text, re.DOTALL)}

def debug_fill_docx_with_docgrid_ai(doc_stream, ai_sections):
    doc = Document(doc_stream)

    print("=== STARTING DOCX DEBUG ===")
    print("Sections received from GPT:")
    for k, v in ai_sections.items():
        print(f"  - {k}: {v[:60]}...")

    for table_idx, table in enumerate(doc.tables):
        print(f"\n-- Table {table_idx} --")
        for row_idx, row in enumerate(table.rows):
            for cell_idx, cell in enumerate(row.cells):
                text = cell.text.strip()
                print(f"  Cell[{row_idx}][{cell_idx}] = '{text}'")
                match_key = best_section_match(text, ai_sections, threshold=0.5)
                if match_key:
                    print(f"    ↳ MATCH FOUND: {match_key}")
                    cell.text += "\n" + ai_sections[match_key]

    for i, para in enumerate(doc.paragraphs):
        ptext = para.text.strip()
        match_key = best_section_match(ptext, ai_sections, threshold=0.5)
        if match_key:
            print(f"\nMATCHING PARAGRAPH [{i}]: '{ptext}' → {match_key}")
            insert_text = ai_sections[match_key]
            if i + 1 < len(doc.paragraphs):
                doc.paragraphs[i + 1].text = insert_text
            else:
                doc.add_paragraph(insert_text)

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output

# -------- Route --------
@app.route('/process', methods=['POST'])
def process_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    ext = os.path.splitext(file.filename)[1].lower()

    # TEMP: Replace GPT with mock output
    gpt_output = """
    {{objectives}}: Students will be able to identify plant life cycles.
    {{materials}}: Chart paper, markers, seed packets.
    {{assessment}}: Students will draw and label a plant diagram.
    {{i do}}: Teacher models the diagram on board.
    {{we do}}: Class labels a sample diagram together.
    {{you do}}: Students draw their own.
    """
    ai_sections = parse_lesson_content(gpt_output)

    try:
        if ext == ".docx":
            filled = debug_fill_docx_with_docgrid_ai(file.stream, ai_sections)
            return send_file(filled,
                             mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             as_attachment=True,
                             download_name="DocGridAI_Debugged.docx")

        return jsonify({"error": "Unsupported file type"}), 400

    except Exception as e:
        print("DocGridAI Error:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
