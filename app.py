from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv
from io import BytesIO
import PyPDF2
from reportlab.pdfgen import canvas
import pdfplumber

load_dotenv()
app = Flask(__name__)
CORS(app)

# SLPS Template Coordinates (x, y from top-left)
SLPS_COORDINATES = {
    'date': (100, 120),
    'missouri_standards': (100, 180),
    'learning_targets': (350, 180),
    'wida_standards': (100, 220),
    'language_objective': (350, 220),
    'materials': (100, 260),
    'vocabulary': (350, 260),
    'assessment': (100, 300),
    'criteria': (350, 300),
    'do_now': (100, 370),
    'i_do': (100, 420),
    'we_do': (100, 470),
    'you_do_together': (100, 520),
    'you_do_alone': (100, 570),
    'homework': (100, 620)
}

def generate_slps_lesson(prompt):
    """Specialized GPT-4 prompt for SLPS templates"""
    return openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": """You are an SLPS lesson plan expert. Follow these rules:
            1. Maintain EXACT template formatting including:
               - Section headers
               - Bullet points (●)
               - Table structures
            2. Fill ALL sections completely
            3. Use professional educator language
            4. Include time allocations (e.g., "Do Now (15min)")"""},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=2000
    ).choices[0].message.content

def create_filled_pdf(original_pdf_path, content):
    """Precise PDF filling for SLPS templates"""
    # Create original PDF background
    original = PyPDF2.PdfReader(original_pdf_path)
    packet = BytesIO()
    
    # Set up canvas with original dimensions
    page_width = original.pages[0].mediabox[2]
    page_height = original.pages[0].mediabox[3]
    can = canvas.Canvas(packet, pagesize=(page_width, page_height))
    can.setFont("Helvetica", 10)  # Match template font

    # Add all content at precise positions
    for section, (x, y) in SLPS_COORDINATES.items():
        if section in content:
            can.drawString(x, page_height - y, content[section])  # Convert to PDF coordinates

    can.save()
    
    # Merge with original
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
        # 1. Generate complete lesson plan content
        full_prompt = f"""Create a complete SLPS lesson plan:
        {prompt}
        Include:
        - Missouri Learning Standards
        - WIDA Standards if applicable
        - Detailed agenda with time allocations
        - Assessment methods"""
        
        lesson_content = generate_slps_lesson(full_prompt)
        
        # 2. Parse into sections
        content_sections = {}
        current_section = None
        for line in lesson_content.split('\n'):
            if ':' in line:
                current_section = line.split(':')[0].strip().lower()
                content_sections[current_section] = line
            elif current_section:
                content_sections[current_section] += '\n' + line
        
        # 3. Generate filled PDF
        file.stream.seek(0)
        filled_pdf, _ = create_filled_pdf(file.stream, content_sections)
        
        return send_file(
            filled_pdf,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="SLPS_Lesson_Plan.pdf"
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
