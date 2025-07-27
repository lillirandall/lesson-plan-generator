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
    """Safe PDF field detection with robust error handling"""
    fields = []
    try:
        with pdfplumber.open(file_stream) as pdf:
            if not pdf.pages:
                return fields
                
            first_page = pdf.pages[0]
            words = first_page.extract_words() or []
            
            for word in words:
                if isinstance(word, dict):
                    text = word.get('text', '')
                    if isinstance(text, str) and text.endswith(':'):
                        fields.append({
                            'label': text,
                            'x': float(word.get('x0', 0)),
                            'y': float(first_page.height - word.get('top', 0)),
                            'page': 0
                        })
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
    return fields

def analyze_docx_fields(file_stream):
    """Safe DOCX field detection"""
    fields = []
    try:
        doc = docx.Document(file_stream)
        for para in doc.paragraphs:
            if ':' in para.text:
                label = para.text.split(':', 1)[0] + ':'
                fields.append({
                    'label': label,
                    'text': para.text
                })
    except Exception as e:
        print(f"DOCX Analysis Error: {e}")
    return fields

def generate_template_content(fields, prompt):
    """AI content generation with robust error handling"""
    if not fields:
        return {}
        
    try:
        field_prompt = "\n".join([f"{field['label']} [REPLACE THIS]" for field in fields])
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""Fill these template fields exactly:
                {field_prompt}
                User Request: {prompt}"""},
                {"role": "user", "content": "Fill all fields maintaining original format"}
            ],
            temperature=0.3
        )
        
        filled_fields = {}
        if response.choices:
            for line in response.choices[0].message.content.split('\n'):
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        filled_fields[parts[0].strip() + ':'] = parts[1].strip()
        
        return filled_fields
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return {}

def create_filled_pdf(file_stream, fields, filled_fields):
    """PDF generation with coordinate safety checks"""
    try:
        packet = BytesIO()
        can = canvas.Canvas(packet)
        
        with pdfplumber.open(file_stream) as pdf:
            if pdf.pages:
                for field in fields:
                    if field['label'] in filled_fields:
                        can.drawString(
                            field['x'],
                            field['y'],
                            filled_fields[field['label']]
                        )
        
        can.save()
        packet.seek(0)
        return packet, "application/pdf"
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        raise

def create_filled_docx(file_stream, filled_fields):
    """DOCX generation with paragraph safety checks"""
    try:
        doc = docx.Document(file_stream)
        for para in doc.paragraphs:
            if ':' in para.text:
                label = para.text.split(':', 1)[0] + ':'
                if label in filled_fields:
                    para.text = label + ' ' + filled_fields[label]
        
        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    except Exception as e:
        print(f"DOCX Generation Error: {e}")
        raise

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    
    try:
        # Get file extension safely
        filename = file.filename or ''
        file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
        
        if file_ext == 'pdf':
            fields = analyze_pdf_fields(file.stream)
            file.stream.seek(0)
            filled_fields = generate_template_content(fields, prompt)
            if not filled_fields:
                raise ValueError("Failed to generate content for PDF")
            file.stream.seek(0)
            filled_file, mimetype = create_filled_pdf(file.stream, fields, filled_fields)
            download_name = "filled_lesson_plan.pdf"
        elif file_ext == 'docx':
            fields = analyze_docx_fields(file.stream)
            file.stream.seek(0)
            filled_fields = generate_template_content(fields, prompt)
            if not filled_fields:
                raise ValueError("Failed to generate content for DOCX")
            file.stream.seek(0)
            filled_file, mimetype = create_filled_docx(file.stream, filled_fields)
            download_name = "filled_lesson_plan.docx"
        else:
            return jsonify({"error": "Unsupported file type (only PDF/DOCX allowed)"}), 400

        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        print(f"Processing Error: {str(e)}")
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
