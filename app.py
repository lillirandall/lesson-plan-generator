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

# Configure OpenAI - enforce GPT-4 usage
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("Missing OpenAI API key in .env file")

def analyze_complex_pdf(file_stream):
    """Specialized analyzer for education templates"""
    try:
        with pdfplumber.open(file_stream) as pdf:
            if not pdf.pages:
                return []
                
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            fields = []
            
            # Detect standard education template sections
            section_keywords = {
                'date': ['DATE', 'Date'],
                'standards': ['Missouri Learning Standard', 'Common Core'],
                'objectives': ['Learning Target', 'Objective'],
                'materials': ['Material', 'Resource'],
                'agenda': ['AGENDA', 'Lesson Sequence'],
                'assessment': ['Assessment', 'Exit Ticket']
            }
            
            for section, keywords in section_keywords.items():
                for kw in keywords:
                    if kw in text:
                        fields.append({
                            'section': section,
                            'label': kw,
                            'content': f"[{section.upper()}_CONTENT]"
                        })
            
            return fields
            
    except Exception as e:
        print(f"PDF Analysis Error: {e}")
        return []

def generate_with_gpt4(prompt, template_context):
    """Enforced GPT-4 generation with education-specific tuning"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # Explicitly use GPT-4
            messages=[
                {"role": "system", "content": f"""You are a lesson plan specialist. 
                Fill this template COMPLETELY and PROFESSIONALLY:
                {template_context}"""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,  # Lower for consistent formatting
            max_tokens=2000   # Allow longer responses
        )
        
        # Debug: Verify GPT-4 usage
        print(f"Model used: {response['model']}")  # Should show "gpt-4"
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"GPT-4 Error: {e}")
        raise

def create_filled_pdf(original_stream, filled_content):
    """PDF generation with layout preservation"""
    try:
        # Create original PDF background
        original_pdf = PyPDF2.PdfReader(original_stream)
        packet = BytesIO()
        
        # Set up canvas with original dimensions
        page_width = original_pdf.pages[0].mediabox[2]
        page_height = original_pdf.pages[0].mediabox[3]
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))
        
        # Configure professional educator font
        can.setFont("Helvetica", 10)
        
        # Position content for standard education templates
        positions = {
            'date': (100, page_height-100),
            'standards': (100, page_height-150),
            'objectives': (100, page_height-250),
            'materials': (100, page_height-350),
            'agenda': (100, page_height-450),
            'assessment': (100, page_height-550)
        }
        
        # Add filled content
        for section, content in filled_content.items():
            x, y = positions.get(section, (100, 100))
            can.drawString(x, y, content)
        
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

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    
    try:
        # Analyze template
        fields = analyze_complex_pdf(file.stream)
        if not fields:
            raise ValueError("Unrecognized template format")
        
        # Generate context for GPT-4
        template_context = "\n".join(
            [f"{field['label']}: {field['content']}" 
             for field in fields]
        )
        
        # Get AI-generated content (enforcing GPT-4)
        filled_text = generate_with_gpt4(prompt, template_context)
        
        # Parse filled content
        filled_content = {}
        for line in filled_text.split('\n'):
            if ':' in line:
                parts = line.split(':', 1)
                filled_content[parts[0].strip()] = parts[1].strip()
        
        # Generate output file
        file.stream.seek(0)
        if file.filename.lower().endswith('.pdf'):
            filled_file, mimetype = create_filled_pdf(file.stream, filled_content)
            download_name = "completed_lesson_plan.pdf"
        else:
            return jsonify({"error": "Only PDF templates currently supported"}), 400
        
        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
        
    except Exception as e:
        print(f"Processing Error: {str(e)}")
        return jsonify({"error": f"Lesson plan generation failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
