from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv
from io import BytesIO
import PyPDF2
from reportlab.pdfgen import canvas
import docx
import pdfplumber
import re

# Load environment variables
load_dotenv()
app = Flask(__name__)
CORS(app)

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("Missing OpenAI API key in .env file")

def analyze_pdf_fields(file_stream):
    """Safe PDF field detection that handles multiple template types"""
    fields = []
    try:
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                words = page.extract_words() or []
                
                # Detect label-value pairs
                for i, word in enumerate(words):
                    if isinstance(word, dict) and word.get('text', '').endswith(':'):
                        fields.append({
                            'label': word['text'],
                            'x': word['x0'],
                            'y': page.height - word['top'],
                            'page': page.page_number
                        })
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
    return fields

def analyze_docx_fields(file_stream):
    """DOCX field detection for any template"""
    fields = []
    try:
        doc = docx.Document(file_stream)
        for para in doc.paragraphs:
            if ':' in para.text:
                fields.append({
                    'label': para.text.split(':')[0] + ':',
                    'paragraph': para
                })
    except Exception as e:
        print(f"DOCX Analysis Error: {e}")
    return fields

def generate_template_content(fields, prompt):
    """AI that adapts to any template structure"""
    field_list = "\n".join([f"{field['label']} [REPLACE THIS]" for field in fields])
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"""Fill this template:
            {field_list}
            User Request: {prompt}"""},
            {"role": "user", "content": "Complete all fields exactly as shown."}
        ],
        temperature=0.3
    )
    
    # Parse AI response
    filled_fields = {}
    for line in response.choices[0].message.content.split('\n'):
        if ':' in line:
            parts = line.split(':', 1)
            filled_fields[parts[0].strip() + ':'] = parts[1].strip()
    
    return filled_fields

def create_filled_pdf(file_stream, filled_fields):
    """PDF filling with safe coordinate handling"""
    packet = BytesIO()
    can = canvas.Canvas(packet)
    
    with pdfplumber.open(file_stream) as pdf:
        for field in filled_fields:
            page = pdf.pages[0]  # First page only for simplicity
            can.drawString(
                float(field['x']), 
                float(field['y']), 
                filled_fields[field['label']]
            )
    
    can.save()
    packet.seek(0)
    return packet, "application/pdf"

def create_filled_docx(file_stream, filled_fields):
    """DOCX filling that preserves formatting"""
    doc = docx.Document(file_stream)
    for para in doc.paragraphs:
        if ':' in para.text:
            label = para.text.split(':')[0] + ':'
            if label in filled_fields:
                para.text = label + ' ' + filled_fields[label]
    
    output = BytesIO()
    doc.save(output)
    output.seek(0)
    return output, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    
    try:
        # Detect file type
        if file.filename.lower().endswith('.pdf'):
            fields = analyze_pdf_fields(file.stream)
            file.stream.seek(0)
            filled_fields = generate_template_content(fields, prompt)
            file.stream.seek(0)
            filled_file, mimetype = create_filled_pdf(file.stream, fields)
            download_name = "filled_lesson_plan.pdf"
        elif file.filename.lower().endswith('.docx'):
            fields = analyze_docx_fields(file.stream)
            file.stream.seek(0)
            filled_fields = generate_template_content(fields, prompt)
            file.stream.seek(0)
            filled_file, mimetype = create_filled_docx(file.stream, filled_fields)
            download_name = "filled_lesson_plan.docx"
        else:
            return jsonify({"error": "Unsupported file type (only PDF/DOCX)"}), 400

        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
