from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os
import openai
from io import BytesIO
from difflib import SequenceMatcher
from docx import Document
import fitz  # PyMuPDF
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import re

load_dotenv()
app = Flask(__name__)
CORS(app)

# ---------- Utilities ----------
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def best_section_match(label, sections, threshold=0.7):
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

# ---------- DOCX Handler ----------
def fill_docx_with_docgrid_ai(doc_stream, ai_sections):
    doc = Document(doc_stream)

    # Fill table cells
    for table in doc.tables:
        for row in table.rows:
            for i, cell in enumerate(row.cells):
                match_key = best_section_match(cell.text.strip(), ai_sections)
                if match_key and i + 1 < len(row.cells):
                    row.cells[i + 1].text = ai_sections[match_key]

    # Fill under headers
    for i, para in enumerate(doc.paragraphs):
        match_key = best_section_match(para.text.strip(), ai_sections)
        if match_key:
            insert_text = ai_sections[match_key]
            if i + 1 < len(doc.paragraphs):
                doc.paragraphs[i + 1].text = insert_text
            else:
                doc.add_paragraph(insert_text)

    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output

# ---------- PDF Handler ----------
def detect_pdf_label_positions(pdf_stream, ai_sections):
    pdf_stream.seek(0)
    doc = fitz.open(stream=pdf_stream.read(), filetype="pdf")
    label_positions = {}

    for page_num in range(len(doc)):
        for block in doc[page_num].get_text("blocks"):
            text = block[4].strip()
            match_key = best_section_match(text, ai_sections)
            if match_key and match_key not in label_positions:
                label_positions[match_key] = (block[0], block[1], page_num)

    return label_positions

def fill_pdf_by_label_match(pdf_stream, ai_sections, label_positions):
    pdf_stream.seek(0)
    reader = PyPDF2.PdfReader(pdf_stream)
    writer = PyPDF2.PdfWriter()

    for i in range(len(reader.pages)):
        base_page = reader.pages[i]
        width = float(base_page.mediabox.width)
        height = float(base_page.mediabox.height)

        packet = BytesIO()
        can = canvas.Canvas(packet, pagesize=(width, height))
        can.setFont("Helvetica", 9)

        for key, (x, y, pg) in label_positions.items():
            if pg != i:
                continue
            lines = simpleSplit(ai_sections[key], "Helvetica", 9, width - x - 50)
            y_draw = height - y - 15
            for line in lines:
                can.drawString(x + 10, y_draw, line)
                y_draw -= 12

        can.save()
        packet.seek(0)
        overlay = PyPDF2.PdfReader(packet)
        base_page.merge_page(overlay.pages[0])
        writer.add_page(base_page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output

# ---------- GPT Generator ----------
def generate_lesson_content(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a lesson plan generator. Format with {{section}}: content."},
            {"role": "user", "content": f"Create a full lesson plan for: {prompt}. Include objectives, standards, materials, vocabulary, I do, we do, you do together, assessment, reflection."}
        ],
        temperature=0.3,
        max_tokens=2000
    )
    return response.choices[0].message.content

# ---------- Flask Endpoint ----------
@app.route('/process', methods=['POST'])
def process_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    ext = os.path.splitext(file.filename)[1].lower()

    try:
        gpt_output = generate_lesson_content(prompt)
        ai_sections = parse_lesson_content(gpt_output)

        if ext == ".docx":
            filled = fill_docx_with_docgrid_ai(file.stream, ai_sections)
            return send_file(filled, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             as_attachment=True, download_name="DocGridAI_Filled_Lesson.docx")

        elif ext == ".pdf":
            file.stream.seek(0)
            positions = detect_pdf_label_positions(file.stream, ai_sections)
            file.stream.seek(0)
            filled = fill_pdf_by_label_match(file.stream, ai_sections, positions)
            return send_file(filled, mimetype="application/pdf", as_attachment=True,
                             download_name="DocGridAI_Filled_Lesson.pdf")

        else:
            return jsonify({"error": "Unsupported file type"}), 400

    except Exception as e:
        print("DocGridAI Error:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
