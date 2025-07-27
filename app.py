from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv
from io import BytesIO
import PyPDF2
from reportlab.pdfgen import canvas
import pdfplumber
import re

# Load environment variables
load_dotenv()
app = Flask(__name__)
CORS(app)

# Configure OpenAI with GPT-4 enforcement
openai.api_key = os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    raise ValueError("OpenAI API key missing in .env file")

# SLPS Template Coordinates (pixels from top-left)
SLPS_TEMPLATE_LAYOUT = {
    'date': {'x': 100, 'y': 120},
    'standards': {'x': 100, 'y': 180},
    'objectives': {'x': 100, 'y': 250},
    'wida_standards': {'x': 100, 'y': 320},
    'materials': {'x': 100, 'y': 390},
    'vocabulary': {'x': 100, 'y': 460},
    'assessment': {'x': 100, 'y': 530},
    'agenda': {'x': 100, 'y': 600}
}

def analyze_slps_pdf(file_stream):
    """Specialized analyzer for SLPS templates with precise coordinates"""
    try:
        with pdfplumber.open(file_stream) as pdf:
            if not pdf.pages:
                return []
                
            first_page = pdf.pages[0]
            fields = []
            
            # Use predefined coordinates for SLPS template
            for section, coords in SLPS_TEMPLATE_LAYOUT.items():
                fields.append({
                    'section': section,
                    'x': coords['x'],
                    'y': first_page.height - coords['y']  # Convert to PDF coordinate system
                })
            
            return fields
            
    except Exception as e:
        print(f"SLPS PDF Analysis Error: {e}")
        return []

def generate_slps_content(prompt):
    """GPT-4 prompt engineered specifically for SLPS templates"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """You are an SLPS lesson plan specialist. Follow these rules:
                1. Maintain EXACT template formatting including:
                   - Section headers (e.g., "DAILY LESSON AGENDA")
                   - Bullet points (•)
                   - Time allocations (e.g., "Do Now (15min)")
                2. Use professional educator language
                3. Align with Missouri Learning Standards"""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        
        # Debug: Verify GPT-4 usage
        print(f"Model used: {response['model']}")
        
        return response.choices[0].message.content
        
    except Exception as e:
        print(f"GPT-4 Generation Error: {e}")
        raise

def create_filled_slps_pdf(original_stream, content):
    """PDF generator optimized for SLPS templates"""
    try:
        # Load original template as background
        original_pdf = PyPDF2.PdfReader(original_stream)
        packet = BytesIO()
        
        # Set canvas to match template size
        page_width = original_pdf.pages[0].mediabox[2]
        page_height = original_pdf.pages[0].mediabox[3]
        can = canvas.Canvas(packet, pagesize=(page_width, page_height))
        
        # Configure professional educator styling
        can.setFont("Helvetica", 10)
        
        # Parse and position content
        for line in content.split('\n'):
            if ':' in line:
                section = line.split(':')[0].strip().lower()
                if section in SLPS_TEMPLATE_LAYOUT:
                    coords = SLPS_TEMPLATE_LAYOUT[section]
                    can.drawString(coords['x'], page_height - coords['y'], line)
        
        can.save()
        
        # Merge with original template
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
        # 1. Analyze template structure
        fields = analyze_slps_pdf(file.stream)
        if not fields:
            raise ValueError("This doesn't appear to be an SLPS template")
        
        # 2. Generate content
        full_prompt = f"""Create a complete SLPS lesson plan using this template.
        Requirements:
        - {prompt}
        - Fill ALL sections
        - Include time allocations
        - Align with Missouri Standards"""
        
        filled_content = generate_slps_content(full_prompt)
        
        # 3. Generate PDF
        file.stream.seek(0)
        filled_file, mimetype = create_filled_slps_pdf(file.stream, filled_content)
        
        return send_file(
            filled_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name="SLPS_Lesson_Plan.pdf"
        )
        
    except Exception as e:
        print(f"Processing Error: {str(e)}")
        return jsonify({"error": f"Failed to generate lesson plan: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
