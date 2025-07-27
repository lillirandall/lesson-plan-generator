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
from typing import Dict, List

load_dotenv()
app = Flask(__name__)
CORS(app)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Universal Field Detection
def detect_template_fields(file_stream, filename: str) -> List[Dict]:
    """Detects fillable areas in ANY template using AI-assisted analysis"""
    if filename.lower().endswith('.pdf'):
        return analyze_pdf_fields(file_stream)
    elif filename.lower().endswith('.docx'):
        return analyze_docx_fields(file_stream)
    else:
        raise ValueError("Unsupported file type")

def analyze_pdf_fields(file_stream) -> List[Dict]:
    """PDF field detection that works with most layouts"""
    fields = []
    try:
        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                words = page.extract_words()
                
                # Find all potential field labels (text ending with :)
                labels = [w for w in words if re.search(r':\s*$', w['text'])]
                
                for label in labels:
                    fields.append({
                        'label': label['text'],
                        'x': label['x0'],
                        'y': page.height - label['top'],
                        'page': page.page_number
                    })
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
    return fields

def analyze_docx_fields(file_stream) -> List[Dict]:
    """DOCX field detection for any template"""
    fields = []
    try:
        doc = docx.Document(file_stream)
        for i, para in enumerate(doc.paragraphs):
            if re.search(r':\s*$', para.text):
                fields.append({
                    'label': para.text,
                    'paragraph_index': i
                })
    except Exception as e:
        print(f"DOCX Analysis Error: {e}")
    return fields

# Universal Content Generation
def generate_template_content(fields: List[Dict], prompt: str) -> Dict:
    """AI that adapts to any template structure"""
    field_list = "\n".join([f"{field['label']} [REPLACE THIS]" for field in fields])
    
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": f"""You are a template filling assistant. 
             Fill these fields exactly as they appear, preserving all formatting:
             {field_list}
             User Request: {prompt}"""},
            {"role": "user", "content": "Fill the template completely."}
        ],
        temperature=0.3
    )
    
    # Parse the AI response into field-value pairs
    filled_fields = {}
    for line in response.choices[0].message.content.split('\n'):
        if ':' in line:
            label, value = line.split(':', 1)
            filled_fields[label.strip()] = value.strip()
    
    return filled_fields

# Universal Output Generation
def create_filled_file(file_stream, filename: str, filled_fields: Dict):
    if filename.lower().endswith('.pdf'):
        return create_filled_pdf(file_stream, filled_fields)
    elif filename.lower().endswith('.docx'):
        return create_filled_docx(file_stream, filled_fields)

def create_filled_pdf(file_stream, filled_fields: Dict):
    """Handles any PDF layout by overlaying text at detected positions"""
    packet = BytesIO()
    can = canvas.Canvas(packet)
    
    with pdfplumber.open(file_stream) as pdf:
        for field in filled_fields:
            page = pdf.pages[field['page']-1]
            can.drawString(field['x'], field['y'], filled_fields[field['label']])
    
    can.save()
    packet.seek(0)
    return packet, "application/pdf"

def create_filled_docx(file_stream, filled_fields: Dict):
    """Handles any DOCX template by replacing text"""
    doc = docx.Document(file_stream)
    for para in doc.paragraphs:
        if para.text in filled_fields:
            para.text = filled_fields[para.text]
    
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
        # Universal processing flow
        fields = detect_template_fields(file.stream, file.filename)
        file.stream.seek(0)
        
        filled_fields = generate_template_content(fields, prompt)
        file.stream.seek(0)
        
        filled_file, mimetype = create_filled_file(file.stream, file.filename, filled_fields)
        
        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f"filled_{file.filename}"
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
