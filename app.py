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
    'date': "date",
    'standards': "standard",
    'objectives': "objective",
    'wida': "wida",
    'language_obj': "language objective",
    'materials': "materials",
    'vocabulary': "vocabulary",
    'assessment': "assessment",
    'success_criteria': "success criteria",
    'do_now': "do now",
    'i_do': "i do",
    'we_do': "we do",
    'you_do_together': "you do together",
    'you_do_alone': "you do alone",
    'homework': "homework"
}

def generate_slps_content(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": """You are a lesson plan assistant. Respond in this format:
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
{{homework}}:"""},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=2000
    )
    return response.choices[0].message.content

def parse_lesson_content(content):
    pattern = r'\{\{(.*?)\}\}:(.*?)(?=\n\{\{|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    return {k.strip().lower(): v.strip() for k, v in matches}

def detect_label_positions(pdf_stream, label_keywords):
    pdf_stream.seek(0)
    doc = fitz.open(stream=pdf_stream.read(), filetype="pdf")
    positions = {}
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks")
        for block in blocks:
            text = block[4].strip().lower()
            for key, label in label_keywords.items():
                if label in text and key not in positions:
                    x, y = block[0] + 100, block[1]
                    positions[key] = (x, y, page_num)
    return positions

def fill_pdf(pdf_stream, sections, coords, page_count):
    pdf_stream.seek(0)
    reader = PyPDF2.PdfReader(pdf_stream)
    writer = PyPDF2.PdfWriter()

    packets = [BytesIO() for _ in range(page_count)]
    canvases = []
    for i in range(page_count):
        page = reader.pages[i]
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        can = canvas.Canvas(packets[i], pagesize=(width, height))
        can.setFont("Helvetica", 9)
        canvases.append((can, width, height))

    if coords:
        for section, value in sections.items():
            if section in coords:
                x, y, page_num = coords[section]
                _, height = canvases[page_num][1], canvases[page_num][2]
                y_draw = height - y
                lines = simpleSplit(value, "Helvetica", 9, 400)
                for line in lines:
                    canvases[page_num][0].drawString(x, y_draw, line)
                    y_draw -= 12
    else:
        # fallback: generic vertical layout
        start_y = canvases[0][2] - 100
        x = 80
        for section, value in sections.items():
            lines = simpleSplit(f"{section.upper()}: {value}", "Helvetica", 9, 400)
            for line in lines:
                canvases[0][0].drawString(x, start_y, line)
                start_y -= 12
            start_y -= 8

    for i in range(page_count):
        canvases[i][0].save()
        packets[i].seek(0)
        overlay = PyPDF2.PdfReader(packets[i])
        base_page = reader.pages[i]
        base_page.merge_page(overlay.pages[0])
        writer.add_page(base_page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output

def fill_docx_template(doc_stream, sections):
    doc = Document(doc_stream)
    for para in doc.paragraphs:
        for key, value in sections.items():
            pattern = re.compile(rf'\{{\{{\s*{key}\s*\}}\}}', re.IGNORECASE)
            if pattern.search(para.text):
                for run in para.runs:
                    run.text = pattern.sub(value, run.text)
    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    ext = os.path.splitext(secure_filename(file.filename))[1].lower()

    try:
        content = generate_slps_content(f"Create a lesson plan for: {prompt}")
        sections = parse_lesson_content(content)

        if ext == ".pdf":
            file.stream.seek(0)
            coords = detect_label_positions(file.stream, LABEL_KEYWORDS)
            file.stream.seek(0)
            page_count = len(PyPDF2.PdfReader(file.stream).pages)
            file.stream.seek(0)
            filled = fill_pdf(file.stream, sections, coords, page_count)
            return send_file(filled, mimetype="application/pdf", as_attachment=True,
                             download_name="Filled_Lesson_Plan.pdf")

        elif ext == ".docx":
            output = fill_docx_template(file.stream, sections)
            return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             as_attachment=True, download_name="Filled_Lesson_Plan.docx")

        else:
            return jsonify({"error": "Unsupported file type."}), 400

    except Exception as e:
        print("Internal Error:", str(e))
        return jsonify({"error": f"Lesson plan generation failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

    'materials': (100, 615),
    'vocabulary': (320, 615),
    'assessment': (100, 580),
    'success_criteria': (320, 580),
    'do_now': (_
