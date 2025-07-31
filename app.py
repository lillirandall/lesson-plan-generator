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

load_dotenv()
app = Flask(__name__)
CORS(app)

# SLPS Template Coordinates (x, y from top-left)
SLPS_COORDINATES = {
    'date': (100, 120),
    'standards': (100, 180),         # Missouri Standards
    'objectives': (350, 180),        # Learning Targets
    'wida': (100, 220),              # WIDA Standards
    'language_obj': (350, 220),      # Language Objective
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

def generate_slps_content(prompt):
    """Specialized GPT-4 prompt for SLPS templates"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": """You are an SLPS lesson plan specialist. Follow these rules:
                1. Maintain EXACT template formatting
                2. Fill ALL sections completely
                3. Use bullet points (•) for activities
                4. Include time allocations (e.g., "Do Now (5min)")
                5. Return in this EXACT format:
                DATE: [date]
                STANDARDS: [standard]
                OBJECTIVES: [objective]
                WIDA: [wida standard]
                LANGUAGE_OBJ: [language objective]
                MATERIALS: [materials]
                VOCABULARY: [vocabulary]
                ASSESSMENT: [assessment]
                SUCCESS_CRITERIA: [criteria]
                DO_NOW: • Activity (time)
                I_DO: • Activity (time)
                WE_DO: • Activity (time)
                YOU_DO_TOGETHER: • Activity (time)
                YOU_DO_ALONE: • Activity (time)
                HOMEWORK: • Activity"""},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"GPT-4 Error: {e}")
        raise

def parse_lesson_content(content):
    """Extracts sections from GPT-4 response"""
    sections = {}
    current_section = None
    
    for line in content.split('\n'):
        if ':' in line:
            section, value = line.split(':', 1)
            current_section = section.strip().lower()
            sections[current_section] = value.strip()
        elif current_section:
            sections[current_section] += '\n' + line.strip()
    
    return sections

def create_slps_pdf(original_pdf, sections):
    """Generates PDF with precise text placement"""
    packet = BytesIO()
    
    # Set up canvas using original PDF dimensions
    original = PyPDF2.PdfReader(original_pdf)
    page_width = original.pages[0].mediabox[2]
    page_height = original.pages[0].mediabox[3]
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    can.setFont("Helvetica", 10)  # Match template font

    # Add text at precise coordinates
    for section, (x, y) in SLPS_COORDINATES.items():
        if section in sections:
            can.drawString(x, page_height - y, sections[section])

    can.save()
    
    # Merge with original template
    new_pdf = PyPDF2.PdfReader(packet)
    output = PyPDF2.PdfWriter()
    page = original.pages[0]
    page.merge_page(new_pdf.pages[0])
    output.add_page(page)
    
    output_stream = BytesIO()
    output.write(output_stream)
    output_stream.seek(0)
    return output_stream

@app.route('/process', methods=['POST'])
def process():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    prompt = request.form.get('prompt', '').strip()
    
    try:
        # 1. Generate content
        lesson_content = generate_slps_content(
            f"Create a complete SLPS lesson plan about: {prompt}\n"
            "Include Missouri Standards, WIDA Standards (if applicable), "
            "and detailed time allocations for each activity."
        )
        
        # 2. Parse into sections
        sections = parse_lesson_content(lesson_content)
        
        # 3. Generate PDF
        file.stream.seek(0)
        filled_pdf = create_slps_pdf(file.stream, sections)
        
        return send_file(
            filled_pdf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="SLPS_Lesson_Plan.pdf"
        )
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": f"Lesson plan generation failed: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
