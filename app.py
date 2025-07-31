from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from io import BytesIO
import openai
import fitz  # PyMuPDF
import PyPDF2
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
import os
import re

load_dotenv()
app = Flask(__name__)
CORS(app)

# Keywords expected in lesson plan templates
LABEL_KEYWORDS = {
    'date': "daily lesson plan date",
    'standards': "missouri learning standard",
    'objectives': "learning targets",
    'wida': "wida standard",
    'language_obj': "language objective",
    'materials': "materials",
    'vocabulary': "vocabulary",
    'assessment': "lesson assessment",
    'success_criteria': "criteria for success",
    'do_now': "do now",
    'i_do': "i do",
    'we_do': "we do",
    'you_do_together': "you do together",
    'you_do_alone': "you do alone",
    'homework': "homework"
}

def generate_slps_content(prompt):
    """Generate structured SLPS lesson plan from GPT"""
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
    """Parse GPT output into section dictionary"""
    pattern = r'\{\{(.*?)\}\}:(.*?)(?=\n\{\{|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    return {k.strip().lower(): v.strip() for k, v in matches}

def detect_label_positions(pdf_stream, label_keywords):
    """Use PyMuPDF to detect positions of known labels in PDF"""
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
                    x, y = block[0] + 100, block[1]  # draw slightly to the right of label
                    positions[key] = (x, y)

    return positions

def fill_pdf(pdf_stream, sections, coords):
    """Draw AI-generated content at detected label positions"""
    pdf_stream.seek(0)
    reader = PyPDF2.PdfReader(pdf_stream)
    writer = PyPDF2.PdfWriter()
    page = reader.pages[0]

    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)

    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    can.setFont("Helvetica", 9)

    for section, (x, y) in coords.items():
        if section in sections:
            y = page_height - y  # convert PyMuPDF to ReportLab coords
            lines = simpleSplit(sections[section], "Helvetica", 9, 400)
            for line in lines:
                can.drawString(x, y, line)
                y -= 12

    can.save()
    packet.seek(0)

    overlay = PyPDF2.PdfReader(packet)
    page.merge_page(overlay.pages[0])
    writer.add_page(page)

    output_stream = BytesIO()
    writer.write(output_stream)
    output_stream.seek(0)
    return output_stream

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    filename = secure_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()

    try:
        # Step 1: generate AI lesson content
        content = generate_slps_content(
            f"Create a full SLPS-style lesson plan about: {prompt} using curly brace labels."
        )
        sections = parse_lesson_content(content)

        # Step 2: only support PDF for now
        if ext != ".pdf":
            return jsonify({"error": "Only PDF files are currently supported."}), 400

        # Step 3: detect label positions
        coords = detect_label_positions(file.stream, LABEL_KEYWORDS)
        if not coords:
            return jsonify({"error": "No recognizable labels found in the PDF."}), 400

        # Step 4: overlay AI content at matched positions
        file.stream.seek(0)
        filled = fill_pdf(file.stream, sections, coords)

        return send_file(filled, mimetype="application/pdf", as_attachment=True,
                         download_name="Filled_Lesson_Plan.pdf")

    except Exception as e:
        print("Internal Error:", str(e))
        return jsonify({"error": f"Lesson plan generation failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
