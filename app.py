from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from io import BytesIO
from docx import Document
import PyPDF2
from reportlab.pdfgen import canvas
import openai
import os
import re

load_dotenv()
app = Flask(__name__)
CORS(app)

# Coordinates for known SLPS static PDF templates
STATIC_COORDINATES = {
    'date': (100, 120),
    'standards': (100, 180),
    'objectives': (350, 180),
    'wida': (100, 220),
    'language_obj': (350, 220),
    'materials': (100, 260),
    'vocabulary': (350, 260),
    'assessment': (100, 300),
    'success_criteria': (350, 300),
    'do_now': (100, 370),
    'i_do': (100, 420),
    'we_do': (100, 470),
    'you_do_together': (100, 520),
    'you_do_alone': (100, 570),
    'homework': (100, 620)
}

# Generate lesson content using GPT
def generate_slps_content(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": """You are a lesson plan assistant. Respond ONLY in this format with curly-brace placeholders:
{{date}}:
{{standards}}:
{{objectives}}:
{{wida}}:
{{language_obj}}:
{{materials}}:
{{vocabulary}}:
{{assessment}}:
{{success_criteria}}:
{{do_now}}:
{{i_do}}:
{{we_do}}:
{{you_do_together}}:
{{you_do_alone}}:
{{homework}}:"""
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=2500
    )
    return response.choices[0].message.content

# Extract curly-brace placeholders from AI response
def parse_lesson_content(content):
    pattern = r'\{\{(.*?)\}\}:(.*?)(?=\n\{\{|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    return {k.strip().lower(): v.strip() for k, v in matches}

# Extract placeholders from DOCX
def extract_placeholders_docx(doc):
    placeholders = set()
    for para in doc.paragraphs:
        matches = re.findall(r'\{\{(.*?)\}\}', para.text)
        for match in matches:
            placeholders.add(match.strip().lower())
    return placeholders

# Extract placeholders from PDF text
def extract_placeholders_pdf(pdf_stream):
    text = ""
    reader = PyPDF2.PdfReader(pdf_stream)
    for page in reader.pages:
        try:
            text += page.extract_text()
        except:
            continue
    return set(re.findall(r'\{\{(.*?)\}\}', text.lower()))

# Fill a Word doc using placeholders
def fill_docx_template(doc_stream, sections):
    doc = Document(doc_stream)
    for para in doc.paragraphs:
        for key in sections:
            placeholder = f"{{{{{key}}}}}"
            if placeholder in para.text:
                for run in para.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, sections[key])
    output_stream = BytesIO()
    doc.save(output_stream)
    output_stream.seek(0)
    return output_stream

# Fill a PDF using text overlays based on detected placeholders
def fill_pdf_with_placeholders(pdf_stream, sections):
    reader = PyPDF2.PdfReader(pdf_stream)
    page = reader.pages[0]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)

    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    can.setFont("Helvetica", 10)

    y = page_height - 100
    for key, val in sections.items():
        can.drawString(50, y, f"{key.upper()}: {val[:90]}")
        y -= 40
        if y < 100:
            break

    can.save()
    packet.seek(0)

    overlay = PyPDF2.PdfReader(packet)
    writer = PyPDF2.PdfWriter()
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    output_stream = BytesIO()
    writer.write(output_stream)
    output_stream.seek(0)
    return output_stream

# Fill PDF using hardcoded coordinates for static layouts
def fill_pdf_with_coordinates(pdf_stream, sections):
    reader = PyPDF2.PdfReader(pdf_stream)
    page = reader.pages[0]
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)

    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    can.setFont("Helvetica", 10)

    for section, (x, y) in STATIC_COORDINATES.items():
        if section in sections:
            text = can.beginText(x, page_height - y)
            for line in sections[section].split('\n'):
                text.textLine(line.strip())
            can.drawText(text)

    can.save()
    packet.seek(0)

    overlay = PyPDF2.PdfReader(packet)
    writer = PyPDF2.PdfWriter()
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    output_stream = BytesIO()
    writer.write(output_stream)
    output_stream.seek(0)
    return output_stream

# Main API route
@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    try:
        # Generate AI content
        lesson_text = generate_slps_content(
            f"Create a full SLPS-style lesson plan about: {prompt}. Use curly-brace labels like {{objectives}}."
        )
        sections = parse_lesson_content(lesson_text)

        file.stream.seek(0)
        if ext == ".docx":
            doc = Document(file)
            placeholders = extract_placeholders_docx(doc)
            filtered = {k: v for k, v in sections.items() if k in placeholders}
            output_stream = fill_docx_template(file.stream, filtered)
            return send_file(output_stream, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             as_attachment=True, download_name="Filled_Lesson_Plan.docx")

        elif ext == ".pdf":
            placeholders = extract_placeholders_pdf(file.stream)
            file.stream.seek(0)
            if placeholders:
                filtered = {k: v for k, v in sections.items() if k in placeholders}
                output_stream = fill_pdf_with_placeholders(file.stream, filtered)
            else:
                output_stream = fill_pdf_with_coordinates(file.stream, sections)

            return send_file(output_stream, mimetype="application/pdf",
                             as_attachment=True, download_name="Filled_Lesson_Plan.pdf")
        else:
            return jsonify({"error": "Unsupported file type"}), 400

    except Exception as e:
        print(f"Internal Error: {str(e)}")
        return jsonify({"error": f"Lesson plan generation failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

