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

# Load environment variables
load_dotenv()
app = Flask(__name__)
CORS(app)

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("Missing OpenAI API key in .env file")

def analyze_pdf_fields(file_stream):
    """Detects fillable areas in PDF templates"""
    fields = []
    try:
        with pdfplumber.open(file_stream) as pdf:
            if not pdf.pages:
                return fields
                
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            
            # Find all field labels (text ending with :)
            for line in text.split('\n'):
                if ':' in line:
                    label = line.split(':')[0] + ':'
                    fields.append({
                        'label': label,
                        'original_text': line,
                        'page': 0,
                        'x': 50,  # Default positions
                        'y': 700  # Will be adjusted per field
                    })
                    
            # Adjust y positions based on line numbers
            for i, field in enumerate(fields):
                field['y'] = 700 - (i * 20)  # 20pt vertical spacing
                
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
    return fields

def analyze_docx_fields(file_stream):
    """Detects fillable areas in DOCX templates"""
    fields = []
    try:
        doc = docx.Document(file_stream)
        for para in doc.paragraphs:
            if ':' in para.text:
                label = para.text.split(':')[0] + ':'
                fields.append({
                    'label': label,
                    'paragraph': para,
                    'original_text': para.text
                })
    except Exception as e:
        print(f"DOCX Analysis Error: {e}")
    return fields

def generate_template_content(fields, prompt):
    """Generates AI content that matches template structure"""
    if not fields:
        return {}
        
    try:
        # Create example of current template
        template_example = "\n".join([field['original_text'] for field in fields])
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": f"""You are filling out a lesson plan template. 
                Maintain the EXACT format shown below:
                {template_example}
                User Request: {prompt}"""},
                {"role": "user", "content": "Fill in all fields while preserving the original format exactly."}
            ],
            temperature=0.2  # Low for consistent formatting
        )
        
        # Parse response while maintaining structure
        filled_fields = {}
        for line in response.choices[0].message.content.split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                filled_fields[parts[0].strip() + ':'] = parts[1].strip()
        
        return filled_fields
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return {}

def create_filled_pdf(file_stream, fields, filled_fields):
    """Generates PDF with original template as background + new text"""
    try:
        # Create original PDF background
        original_pdf = PyPDF2.PdfReader(file_stream)
        packet = BytesIO()
        
        # Get page size from original
        page_width = original_pdf.pages[0].mediabox[2]
        page_height = original_pdf.pages[0].mediabox[3]
        
        # Create canvas with same dimensions
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))
        
        # Add all filled text (using Helvetica font)
        can.setFont("Helvetica", 10)
        for field in fields:
            if field['label'] in filled_fields:
                can.drawString(
                    field['x'],
                    field['y'],
                    filled_fields[field['label']]
                )
        
        can.save()
        
        # Merge with original
        new_pdf = PyPDF2.PdfReader(packet)
        output_pdf = PyPDF2.PdfWriter()
        page = original_pdf.pages[0]
        page.merge_page(new_pdf.pages[0])
        output_pdf.add_page(page)
        
        output_stream = BytesIO()
        output_pdf.write(output_stream)
        output_stream.seek(0)
        return output_stream, "application/pdf"
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        raise

def create_filled_docx(file_stream, filled_fields):
    """Generates filled DOCX while preserving formatting"""
    try:
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
