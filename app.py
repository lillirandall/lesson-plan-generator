from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from io import BytesIO
import os
import openai
import fitz  # PyMuPDF
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from docx import Document
import re

load_dotenv()
app = Flask(__name__)
CORS(app)

LABEL_KEYWORDS = {
    'date': ["date", "day"],
    'standards': ["standard", "standards"],
    'objectives': ["objective", "learning target"],
    'wida': ["wida"],
    'language_obj': ["language objective"],
    'materials': ["materials"],
    'vocabulary': ["vocabulary"],
    'assessment': ["assessment"],
    'success_criteria': ["success criteria"],
    'do_now': ["do now", "bell ringer"],
    'i_do': ["i do", "teacher modeling"],
    'we_do': ["we do", "guided practice"],
    'you_do_together': ["you do together", "collaborative"],
    'you_do_alone': ["you do alone", "independent"],
    'homework': ["homework", "extension activity"]
}

def generate_slps_content(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a lesson plan generator. Reply ONLY in this format: {{section_name}}: content"},
            {"role": "user", "content": f"Create a detailed lesson plan for: {prompt} using standard lesson plan sections."}
        ],
        temperature=0.3,
        max_tokens=2000
    )
    return response.choices[0].message.content

def parse_lesson_content(content):
    pattern = r'\{\{(.*?)\}\}:(.*?)(?=\n\{\{|\Z)'
    return {k.strip().lower(): v.strip() for k, v in re.findall(pattern, content, re.DOTALL)}

def fill_docx_by_heading(doc_stream, sections):
    doc = Document(doc_stream)
    for para in doc.paragraphs:
        text = para.text.strip().lower()
        for section, keywords in LABEL_KEYWORDS.items():
            if any(keyword in text for keyword in keywords) and section in sections:
                index = doc.paragraphs.index(para)
                doc.paragraphs.insert(index + 1, doc.add_paragraph(sections[section]))
                break
    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output

def fallback_pdf_writer(sections, width, height):
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(width, height))
    can.setFont("Helvetica", 10)
    y = height - 50
    for key, value in sections.items():
        lines = simpleSplit(f"{key.upper()}: {value}", "Helvetica", 10, width - 100)
        for line in lines:
            can.drawString(50, y, line)
            y -= 12
        y -= 8
        if y < 60:
            break
    can.save()
    packet.seek(0)
    return packet

def fill_pdf_static(pdf_stream, sections):
    pdf_stream.seek(0)
    reader = PyPDF2.PdfReader(pdf_stream)
    writer = PyPDF2.PdfWriter()

    base_page = reader.pages[0]
    width = float(base_page.mediabox.width)
    height = float(base_page.mediabox.height)

    overlay_stream = fallback_pdf_writer(sections, width, height)
    overlay_pdf = PyPDF2.PdfReader(overlay_stream)

    base_page.merge_page(overlay_pdf.pages[0])
    writer.add_page(base_page)

    for page in reader.pages[1:]:
        writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    try:
        content = generate_slps_content(prompt)
        sections = parse_lesson_content(content)

        if ext == ".pdf":
            filled = fill_pdf_static(file.stream, sections)
            return send_file(filled, mimetype="application/pdf", as_attachment=True, download_name="Lesson_Plan_Filled.pdf")

        elif ext == ".docx":
            output = fill_docx_by_heading(file.stream, sections)
            return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             as_attachment=True, download_name="Lesson_Plan_Filled.docx")

        else:
            return jsonify({"error": "Unsupported file type."}), 400

    except Exception as e:
        print("Internal Error:", str(e))
        return jsonify({"error": f"Lesson plan generation failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
